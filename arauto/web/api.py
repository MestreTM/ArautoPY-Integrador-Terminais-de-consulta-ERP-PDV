"""API de integração — porta 5589.

Feita para outros sistemas: PDV, e-commerce, app de conferência de gôndola,
etiquetadora. Devolve JSON, documenta-se sozinha em /docs e mantém um endpoint
`/barcode` compatível com o TC Server antigo, para que integrações existentes
continuem funcionando sem alteração.
"""

from __future__ import annotations

import html
import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ..core.models import Product
from ..core.service import QueryService
from ..core.settings import APP_VERSION, get_settings

log = logging.getLogger("arauto.api")


class ProdutoIn(BaseModel):
    codigo_barras: str = Field(..., min_length=1, max_length=20)
    descricao: str = Field("", max_length=200)
    preco1: str = ""
    preco2: str = ""


class ConsultaLote(BaseModel):
    codigos: list[str] = Field(..., min_length=1, max_length=500)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def create_api(service: QueryService) -> FastAPI:
    settings = get_settings()
    api_key = settings.get("API_KEY")

    app = FastAPI(
        title="ArautoPY — API de consulta de preços",
        version=APP_VERSION,
        description=(
            "Consulta de preços por código de barras, com suporte a códigos de "
            "balança (EAN-13 por peso). Use `/api/v1/consulta/{codigo}` para o "
            "caso simples e `/api/v1/consulta` para lotes."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.service = service

    origins = [o.strip() for o in settings.get("API_CORS_ORIGINS").split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def require_key(x_api_key: str = Header(default="")) -> None:
        if api_key and x_api_key != api_key:
            raise HTTPException(status_code=401, detail="Chave de API inválida ou ausente")

    guard = [Depends(require_key)] if api_key else []

    # ----------------------------------------------------------- diagnóstico
    @app.get("/api/v1/saude", tags=["diagnóstico"], summary="Verifica se o serviço responde")
    def saude() -> dict:
        return {"ok": True, "versao": APP_VERSION, "produtos": service.repo.count()}

    @app.get("/api/v1/status", tags=["diagnóstico"], dependencies=guard,
             summary="Estado do servidor, da base e dos terminais")
    def status() -> dict:
        return service.status()

    @app.get("/api/v1/estatisticas", tags=["diagnóstico"], dependencies=guard,
             summary="Resumo das consultas do período")
    def estatisticas(dias: int = Query(7, ge=1, le=365)) -> dict:
        return service.querylog.stats(days=dias)

    @app.get("/api/v1/consultas", tags=["diagnóstico"], dependencies=guard,
             summary="Últimas consultas registradas")
    def consultas(limite: int = Query(50, ge=1, le=500)) -> list[dict]:
        return service.querylog.recent(limit=limite)

    @app.post("/api/v1/recarregar", tags=["diagnóstico"], dependencies=guard,
              summary="Força a recarga da base de produtos")
    def recarregar() -> dict:
        total = service.reload()
        return {"ok": True, "produtos": total}

    # -------------------------------------------------------------- consulta
    @app.get("/api/v1/consulta/{codigo}", tags=["consulta"], dependencies=guard,
             summary="Consulta um código de barras")
    def consulta(codigo: str, request: Request) -> JSONResponse:
        result = service.query(codigo, origin=client_ip(request), channel="api")
        return JSONResponse(result.to_dict(), status_code=200 if result.found else 404)

    @app.post("/api/v1/consulta", tags=["consulta"], dependencies=guard,
              summary="Consulta vários códigos de uma vez")
    def consulta_lote(corpo: ConsultaLote, request: Request) -> dict:
        origin = client_ip(request)
        resultados = [
            service.query(c, origin=origin, channel="api-lote").to_dict()
            for c in corpo.codigos
        ]
        return {
            "total": len(resultados),
            "encontrados": sum(1 for r in resultados if r["encontrado"]),
            "resultados": resultados,
        }

    # -------------------------------------------------------------- produtos
    @app.get("/api/v1/produtos", tags=["produtos"], dependencies=guard,
             summary="Lista ou busca produtos")
    def listar(
        q: str = Query("", description="Busca por código ou descrição"),
        limite: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict:
        itens = service.repo.search(q, limit=limite, offset=offset)
        return {
            "total": service.repo.count(),
            "limite": limite,
            "offset": offset,
            "itens": [p.to_dict() for p in itens],
        }

    @app.get("/api/v1/produtos/{codigo}", tags=["produtos"], dependencies=guard,
             summary="Busca um produto pelo código exato")
    def obter(codigo: str) -> dict:
        produto = service.repo.get(codigo)
        if produto is None:
            raise HTTPException(status_code=404, detail="Produto não cadastrado")
        return produto.to_dict()

    @app.put("/api/v1/produtos/{codigo}", tags=["produtos"], dependencies=guard,
             summary="Cria ou atualiza um produto")
    def gravar(codigo: str, corpo: ProdutoIn) -> dict:
        if service.repo.read_only:
            raise HTTPException(
                status_code=409,
                detail="A base atual é somente leitura. Grave no sistema de origem "
                       "ou mude DB_MODE para INTERNAL.",
            )
        produto = Product(
            barcode=codigo.strip(),
            description=corpo.descricao,
            price1=corpo.preco1,
            price2=corpo.preco2,
        )
        try:
            service.repo.save(produto)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return produto.to_dict()

    @app.delete("/api/v1/produtos/{codigo}", tags=["produtos"], dependencies=guard,
                summary="Remove um produto")
    def remover(codigo: str) -> dict:
        if service.repo.read_only:
            raise HTTPException(status_code=409, detail="A base atual é somente leitura")
        if not service.repo.delete(codigo):
            raise HTTPException(status_code=404, detail="Produto não cadastrado")
        return {"ok": True, "codigo_barras": codigo}

    # ----------------------------------------------- compatibilidade legada
    @app.get("/barcode", tags=["compatibilidade"], response_class=HTMLResponse,
             summary="Endpoint compatível com o TC Server Java (GET /barcode?param=)")
    def barcode_legado(param: str = "", request: Request = None) -> HTMLResponse:
        origin = client_ip(request) if request else ""
        result = service.query(param, origin=origin, channel="legado")
        esc = html.escape
        if not result.found:
            body = (
                f"Consulta de Barcode:<br/>O produto \"{esc(result.barcode)}\" "
                f"nao foi encontrado<br/>"
            )
            return HTMLResponse(f"<html><body>{body}</body></html>", status_code=404)
        linhas = [
            "Consulta de Barcode:<br/>",
            f"Codigo de barras: {esc(result.barcode)}<br/>",
            f"Descricao: {esc(result.description)}<br/>",
        ]
        if result.price1:
            linhas += [f"Label1: {esc(result.label1)}<br/>",
                       f"Preco1: {esc(result.price1)}<br/>"]
        if result.price2:
            linhas += [f"Label2: {esc(result.label2)}<br/>",
                       f"Preco2: {esc(result.price2)}<br/>"]
        return HTMLResponse(f"<html><body>{''.join(linhas)}</body></html>")

    @app.get("/", include_in_schema=False)
    def raiz() -> PlainTextResponse:
        return PlainTextResponse(
            f"ArautoPY {APP_VERSION} — API de consulta de preços\n"
            f"Documentação interativa: /docs\n"
        )

    return app



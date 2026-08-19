"""WebViewer — porta 6689.

O modo novo: um terminal de consulta que roda no navegador. Serve para tablet
preso na gôndola, totem com tela sensível ao toque, ou o celular do repositor.

Fala direto com o QueryService, sem passar pela API, para que o WebViewer
continue funcionando mesmo se a porta 5589 estiver desligada.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Body, FastAPI, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..core import applog, configform
from ..core import layout as layout_mod
from ..protocol.monitor import MONITOR
from ..protocol import sniffer
from ..core import scalelabel
from ..core.models import display_price, parse_price
from ..core.service import QueryService, carregar_mascara
from ..core import product_image
from ..core import runtime
from ..core.settings import APP_DIR, APP_VERSION, get_settings, resource_root
from .. import plugins as plugins_mod
from ..plugins.markdown_lite import para_html as markdown_para_html
from ..data.repositories import (
    listar_colunas_sql,
    listar_tabelas_sql,
    testar_conexao_sql,
)

log = logging.getLogger("arauto.viewer")

BASE_DIR = resource_root() / "web"
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def create_viewer(service: QueryService) -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="ArautoPY — WebViewer", version=APP_VERSION,
                  docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    def ui_context(pagina: str = "") -> dict:
        return {
            "pagina": pagina,
            "versao": APP_VERSION,
            "loja": settings.store_name,
            "rotulo1": settings.get("LABEL1"),
            "rotulo2": settings.get("LABEL2"),
            "nao_encontrado": settings.get("LABEL_NOT_FOUND"),
            "reset_segundos": settings.get_int("IDLE_RESET_SECONDS", 12),
            "abas_plugins": [
                {"id": a.id, "rotulo": a.rotulo, "href": a.href}
                for a in plugins_mod.abas_ativas()
            ],
        }

    @app.get("/", response_class=HTMLResponse, summary="Terminal de consulta")
    def kiosk(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "kiosk.html", ui_context("kiosk"))

    @app.get("/painel", response_class=HTMLResponse, summary="Painel do operador")
    def painel(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "painel.html", ui_context("painel"))

    # --------------------------------------------------------- endpoints ui
    @app.get("/consulta/{codigo}")
    def consulta(codigo: str, request: Request) -> JSONResponse:
        result = service.query(codigo, origin=client_ip(request), channel="webviewer")
        return JSONResponse(result.to_dict(), status_code=200 if result.found else 404)

    @app.get("/api/status")
    def status() -> dict:
        return service.status()

    @app.get("/api/estatisticas")
    def estatisticas(dias: int = 7) -> dict:
        return service.querylog.stats(days=dias)

    @app.get("/api/consultas")
    def consultas(limite: int = 40) -> list[dict]:
        return service.querylog.recent(limit=limite)

    @app.get("/api/produtos")
    def produtos(q: str = "", limite: int = 40) -> dict:
        itens = service.repo.search(q, limit=limite)
        return {"total": service.repo.count(), "itens": [p.to_dict() for p in itens]}

    # ------------------------------------------------------------ configuração
    @app.get("/config", response_class=HTMLResponse, summary="Tela de configuração")
    def tela_config(request: Request) -> HTMLResponse:
        contexto = ui_context("config")
        from ..core import autostart as _autostart
        contexto["autostart"] = _autostart.status()
        contexto["grupos"] = configform.com_valores(settings)
        contexto["caminho_config"] = str(settings.path)
        contexto["mascara"] = service.mascara.resumo()
        contexto["marcadores"] = scalelabel.DESCRICAO_MARCADORES
        contexto["prontas"] = configform.MASCARAS_PRONTAS
        contexto["balanca_ativa"] = settings.get_bool("SCALE_ENABLED", True)
        contexto["product_image_pack_url"] = settings.get("PRODUCT_IMAGE_PACK_URL") or ""
        contexto["presets_base"] = configform.PRESETS_BASE
        return TEMPLATES.TemplateResponse(request, "config.html", contexto)

    @app.get("/api/config")
    def ler_config() -> dict:
        return {
            "arquivo": str(settings.path),
            "grupos": configform.com_valores(settings),
        }

    @app.put("/api/config")
    def gravar_config(corpo: dict = Body(...)) -> JSONResponse:
        entrada = {str(k): str(v) for k, v in (corpo.get("config") or {}).items()}
        permitidas = configform.chaves_permitidas()

        recusadas = set(entrada) - permitidas
        if recusadas:
            return JSONResponse(
                {"detail": "Chaves não editáveis pela tela: " + ", ".join(sorted(recusadas))},
                status_code=400,
            )

        erros = configform.validar_conjunto(entrada)
        if erros:
            return JSONResponse({"detail": " · ".join(erros)}, status_code=422)

        alterados = {k for k, v in entrada.items() if settings.get(k) != v}
        for chave, valor in entrada.items():
            settings.set(chave, valor)

        if "SCALE_MASK" in alterados or "SCALE_ENABLED" in alterados:
            service.mascara = carregar_mascara(settings)
            log.info("Máscara de balança agora é %s", service.mascara.texto)

        log.info("Configuração alterada pela web: %s",
                 ", ".join(sorted(alterados)) or "nenhuma chave")

        aplicado: list[str] = []
        erros_aplicacao: list[str] = []

        if configform.precisa_recarregar_base(alterados):
            r = runtime.aplicar_base_produtos()
            if r.get("ok"):
                aplicado.append(
                    f"Base {r.get('modo')} recarregada ({r.get('produtos', 0)} produtos)"
                )
            else:
                erros_aplicacao.append(r.get("detail") or "Falha ao recarregar base")

        if configform.precisa_recarregar_terminais(alterados):
            r = runtime.reiniciar_terminais()
            if r.get("ok"):
                aplicado.extend(r.get("detalhes") or ["Terminais reaplicados"])
            else:
                erros_aplicacao.append(r.get("detail") or "Falha ao reiniciar terminais")

        reinicio = configform.precisa_reiniciar(alterados)
        return JSONResponse({
            "ok": True,
            "alterados": sorted(alterados),
            "reinicio_necessario": reinicio,
            "aplicado_em_quente": aplicado,
            "erros_aplicacao": erros_aplicacao,
        })

    @app.post("/api/recarregar")
    def recarregar() -> dict:
        total = service.reload()
        log.info("Base recarregada pela web: %d produto(s)", total)
        return {"ok": True, "produtos": total}

    @app.get("/api/balanca/simular")
    def simular_etiqueta(codigo: str = Query(...), mascara: str = Query("")) -> dict:
        """Decompõe um código segundo a máscara, sem gravar nada.

        Conferir aqui antes de salvar evita o pior erro possível: ler um total
        como se fosse peso faz o terminal cobrar o valor errado.
        """
        alvo = scalelabel.Mascara(mascara) if mascara else service.mascara
        erros = alvo.validar()
        if erros:
            return {"ok": False, "motivo": " · ".join(erros)}

        codigo = (codigo or "").strip()
        leitura = scalelabel.ler(codigo, alvo)
        if leitura is None:
            if not codigo.isdigit():
                motivo = "O código precisa ter apenas dígitos."
            elif len(codigo) != alvo.comprimento:
                motivo = (f"A máscara espera {alvo.comprimento} dígitos; "
                          f"este código tem {len(codigo)}.")
            else:
                fixos = [f"posição {i + 1} = {c}"
                         for i, c in enumerate(alvo.texto) if c.isdigit()]
                motivo = ("Não casa com os valores fixos da máscara ("
                          + ", ".join(fixos) + "). Seria consultado direto na base.")
            return {"ok": False, "motivo": motivo}

        simbolo = settings.currency_symbol
        produto = service.buscar_candidatos(leitura.candidatos)

        resposta = {
            "ok": True,
            "codigo": leitura.codigo_lido,
            "mascara": alvo.texto,
            "tipo": leitura.tipo,
            "descricao_tipo": alvo.descricao_tipo,
            "codigo_produto": leitura.codigo_produto,
            "dv_confere": leitura.dv_confere,
            "candidatos": leitura.candidatos,
            "encontrado": produto is not None,
        }
        if leitura.peso is not None:
            resposta["peso"] = float(leitura.peso)
        if leitura.total is not None:
            resposta["total"] = display_price(str(leitura.total), simbolo)

        if produto is not None:
            final = scalelabel.aplicar(produto, leitura, simbolo)
            resposta["codigo_cadastro"] = produto.barcode
            resposta["descricao"] = produto.description
            resposta["preco_unitario"] = display_price(produto.price1, simbolo)
            resposta["preco_final"] = final.price1
            if final.weight is not None:
                resposta["peso_final"] = float(final.weight)
                resposta["peso_estimado"] = leitura.tipo == "total"
        return resposta

    # -------------------------------------------------------------------- logs
    @app.get("/diagnostico", response_class=HTMLResponse, summary="Logs e monitor")
    def tela_diagnostico(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request, "diagnostico.html", ui_context("diagnostico")
        )

    @app.get("/logs", response_class=HTMLResponse, summary="Atalho: diagnóstico → logs")
    def tela_logs(request: Request) -> HTMLResponse:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/diagnostico#logs", status_code=302)

    @app.get("/monitor", response_class=HTMLResponse, summary="Atalho: diagnóstico → monitor")
    def tela_monitor_redirect(request: Request) -> HTMLResponse:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/diagnostico#monitor", status_code=302)

    @app.get("/api/logs")
    def ler_logs(
        desde: int = Query(0, ge=0),
        nivel: str = Query("INFO"),
        origem: str = Query(""),
        busca: str = Query(""),
        limite: int = Query(300, ge=1, le=2000),
    ) -> dict:
        return {
            "linhas": applog.BUFFER.linhas(
                desde=desde, nivel_minimo=nivel, origem=origem,
                busca=busca, limite=limite,
            ),
            "resumo": applog.BUFFER.resumo(),
        }

    @app.get("/api/logs/origens")
    def origens_log() -> list[str]:
        return applog.BUFFER.origens()

    @app.get("/api/logs/arquivo")
    def baixar_log() -> FileResponse:
        caminho = applog.caminho_arquivo(APP_DIR)
        if not caminho.exists():
            return JSONResponse({"detail": "Arquivo de log ainda não foi criado"},
                                status_code=404)
        return FileResponse(caminho, filename=caminho.name, media_type="text/plain")

    # ------------------------------------------------------------------ layout
    @app.get("/layout", response_class=HTMLResponse, summary="Editor de layout")
    def tela_layout(request: Request) -> HTMLResponse:
        contexto = ui_context("layout")
        contexto["elementos"] = layout_mod.ELEMENTOS
        return TEMPLATES.TemplateResponse(request, "layout.html", contexto)

    @app.get("/api/layout")
    def ler_layouts() -> dict:
        """Layouts de todos os modelos, marcando quais estão conectados agora."""
        conectados: dict[int, list[str]] = {}
        for conexao in service.terminals.values():
            tipo = getattr(conexao, "tipo", None)
            if tipo:
                conectados.setdefault(tipo, []).append(conexao.address)

        itens = layout_mod.get_layouts().todos()
        for item in itens:
            item["conectados"] = conectados.get(item["modelo"], [])
        return {
            "modelos": itens,
            "elementos": [{"chave": c, "rotulo": r} for c, r in layout_mod.ELEMENTOS],
            "cores": [{"nome": n, "codigo": c} for n, c in layout_mod.CORES.items()],
            "cor_sem_fundo": layout_mod.COR_SEM_FUNDO,
            # o editor usa exatamente a mesma conta de quebra que o servidor
            "fator_caractere": layout_mod.FATOR_LARGURA_CARACTERE,
            "entrelinha": layout_mod.ENTRELINHA,
        }

    @app.put("/api/layout/{modelo}")
    def gravar_layout(modelo: int, corpo: dict = Body(...)) -> JSONResponse:
        try:
            salvo = layout_mod.get_layouts().gravar(modelo, corpo)
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)
        log.info("Layout do modelo %s (%s) alterado pela web", modelo, salvo.nome)
        return JSONResponse({"ok": True, "layout": salvo.to_dict()})

    @app.post("/api/layout/{modelo}/restaurar")
    def restaurar_layout(modelo: int) -> JSONResponse:
        if modelo not in layout_mod.MODELOS:
            return JSONResponse({"detail": "Modelo desconhecido"}, status_code=404)
        salvo = layout_mod.get_layouts().restaurar(modelo)
        log.info("Layout do modelo %s restaurado ao padrão", modelo)
        return JSONResponse({"ok": True, "layout": salvo.to_dict()})

    @app.get("/api/layout/previa")
    def previa_layout(codigo: str = Query("7896080900001")) -> dict:
        """Dados reais de uma consulta, para a simulação usar conteúdo de verdade."""
        resultado = service.query(codigo, origin="previa", channel="previa")
        return {
            "codigo": resultado.barcode,
            "encontrado": resultado.found,
            "textos": {
                "codigo": resultado.barcode,
                "descricao": resultado.description,
                "rotulo1": resultado.label1 if resultado.price1 else "",
                "preco1": resultado.preco1 if hasattr(resultado, "preco1") else resultado.price1,
                "rotulo2": resultado.label2 if resultado.price2 else "",
                "preco2": resultado.price2,
                "nao_achado": resultado.label_not_found,
            },
        }

    # ----------------------------------------------------------------- monitor
    @app.get("/monitor", response_class=HTMLResponse, summary="Tráfego cru dos terminais")
    def tela_monitor(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "monitor.html", ui_context("monitor"))

    @app.get("/api/monitor")
    def ler_monitor(desde: int = Query(0, ge=0), protocolo: str = Query(""),
                    peer: str = Query(""), limite: int = Query(200, ge=1, le=400)) -> dict:
        return {
            "eventos": MONITOR.eventos(desde=desde, protocolo=protocolo,
                                       peer=peer, limite=limite),
            "resumo": MONITOR.resumo(),
        }

    @app.get("/api/monitor/peers")
    def monitor_peers() -> list[str]:
        return MONITOR.peers()

    @app.post("/api/monitor/limpar")
    def monitor_limpar() -> dict:
        MONITOR.limpar()
        return {"ok": True}

    @app.get("/api/monitor/captura")
    def monitor_captura(peer: str = Query("")):
        from fastapi.responses import Response
        dados = MONITOR.tudo_cru(peer)
        nome = f"captura-{peer.replace(':', '_') or 'tudo'}.bin"
        return Response(dados, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.get("/api/monitor/analise")
    def monitor_analise(peer: str = Query("")) -> dict:
        """Roda as hipóteses de enquadramento sobre o que o terminal mandou."""
        alvo = peer or MONITOR.sessao_principal()
        dados = MONITOR.tudo_cru(alvo)
        if not dados:
            return {"bytes": 0, "peer": "", "hipoteses": [], "conclusao": "",
                    "sessoes": MONITOR.sessoes_resumo()}
        resultados = sniffer.analisar(dados)
        melhor = resultados[0]
        conclusao = (
            f"CONCLUSÃO: o enquadramento é {melhor.hipotese.nome} — "
            f"{melhor.hipotese.descricao}"
            if melhor.completo else
            "CONCLUSÃO: nenhuma hipótese conhecida explica a captura por completo. "
            "Baixe a captura e envie para análise."
        )
        return {
            "bytes": len(dados),
            "peer": alvo,
            "sessoes": MONITOR.sessoes_resumo(),
            "hipoteses": [{
                "nome": r.hipotese.nome,
                "descricao": r.hipotese.descricao,
                "pontuacao": round(r.pontuacao * 100, 1),
                "quadros": r.quadros,
                "ids": r.ids[:10],
                "completo": r.completo,
            } for r in resultados],
            "conclusao": conclusao,
        }

    @app.get("/api/consultas/csv")
    def exportar_consultas() -> FileResponse:
        caminho = service.querylog.export_csv()
        return FileResponse(caminho, filename=caminho.name, media_type="text/csv")

    @app.get("/api/imagens/status")
    def api_imagens_status() -> dict:
        return product_image.status_pacote()

    @app.post("/api/imagens/baixar-pacote")
    def api_imagens_baixar() -> dict:
        """Baixa o ZIP do GitHub: sobrescreve só {ean}.jpg presentes no pacote."""
        product_image.baixar_pacote_em_background()
        return {
            "ok": True,
            "detail": "Download iniciado. Arquivos com o mesmo EAN serão atualizados; os demais locais permanecem.",
        }

    @app.post("/api/imagens/limpar")
    def api_imagens_limpar() -> dict:
        return product_image.limpar_banco_imagens()

    @app.post("/api/imagens/apagar")
    async def api_imagens_apagar(request: Request) -> JSONResponse:
        try:
            corpo = await request.json()
        except Exception:
            corpo = {}
        codigo = str(corpo.get("ean") or corpo.get("codigo") or "").strip()
        r = product_image.apagar_imagem_ean(codigo)
        return JSONResponse(r, status_code=200 if r.get("ok") else 404)


    @app.post("/api/config/testar-sql")
    def api_testar_sql(corpo: dict = Body(default={})) -> JSONResponse:
        """Testa URL/tabela/colunas sem gravar a configuração."""
        url = str(corpo.get("DB_URL") or corpo.get("url") or "").strip()
        table = str(corpo.get("DB_PRODUCT_TABLE_NAME") or corpo.get("table") or "").strip()
        cols = {
            "barcode": str(corpo.get("DB_COL_BARCODE") or "").strip(),
            "description": str(corpo.get("DB_COL_DESCRIPITION") or "").strip(),
            "price1": str(corpo.get("DB_COL_PRICE1") or "").strip(),
            "price2": str(corpo.get("DB_COL_PRICE2") or "").strip(),
        }
        # Se o cliente não mandou campos, usa o que está salvo
        if not url:
            url = settings.get("DB_URL") or ""
        if not table:
            table = settings.get("DB_PRODUCT_TABLE_NAME") or ""
        if not cols["barcode"]:
            cols = {
                "barcode": settings.get("DB_COL_BARCODE") or "",
                "description": settings.get("DB_COL_DESCRIPITION") or "",
                "price1": settings.get("DB_COL_PRICE1") or "",
                "price2": settings.get("DB_COL_PRICE2") or "",
            }
        resultado = testar_conexao_sql(url, table=table, cols=cols)
        # Sempre 200: o front lê resultado.ok (evita throw do helper json)
        return JSONResponse(resultado)


    @app.post("/api/config/listar-tabelas")
    def api_listar_tabelas(corpo: dict = Body(default={})) -> JSONResponse:
        url = str(corpo.get("DB_URL") or corpo.get("url") or settings.get("DB_URL") or "").strip()
        return JSONResponse(listar_tabelas_sql(url))

    @app.post("/api/config/listar-colunas")
    def api_listar_colunas(corpo: dict = Body(default={})) -> JSONResponse:
        url = str(corpo.get("DB_URL") or corpo.get("url") or settings.get("DB_URL") or "").strip()
        table = str(corpo.get("tabela") or corpo.get("table") or "").strip()
        return JSONResponse(listar_colunas_sql(url, table))


    # -------------------------------------------------------------- plugins
    try:
        plugins_mod.carregar_todos(app, service)
    except Exception:
        log.exception("Falha ao carregar plugins")


    # -------------------------------------------------------------- autostart
    @app.get("/api/autostart")
    def api_autostart_status() -> dict:
        from ..core import autostart
        return autostart.status()

    @app.post("/api/autostart")
    def api_autostart_set(corpo: dict = Body(...)) -> dict:
        from ..core import autostart
        bruto = corpo.get("ativo")
        if isinstance(bruto, str):
            ativo = bruto.strip().lower() in ("1", "true", "yes", "sim", "on")
        else:
            ativo = bool(bruto)
        r = autostart.habilitar() if ativo else autostart.desabilitar()
        st = autostart.status()
        r["status"] = st
        return r


    # --------------------------------------------------------------- update
    @app.get("/api/update")
    def api_update_status() -> dict:
        from ..core import updater
        return updater.status()

    @app.post("/api/update/verificar")
    def api_update_verificar() -> dict:
        from ..core import updater
        return updater.verificar()

    @app.get("/api/update/changelog")
    def api_update_changelog() -> dict:
        from ..core import updater
        return updater.changelog()

    @app.post("/api/update/aplicar")
    def api_update_aplicar(corpo: dict = Body(default={})) -> dict:
        from ..core import updater
        url = (corpo or {}).get("url") if isinstance(corpo, dict) else None
        return updater.aplicar(url=url)


    @app.get("/plugins", response_class=HTMLResponse, summary="Gerenciador de plugins")
    def tela_plugins(request: Request) -> HTMLResponse:
        ctx = ui_context("plugins")
        ctx["pasta"] = str(plugins_mod.pasta_plugins())
        return TEMPLATES.TemplateResponse(request, "plugins.html", ctx)

    @app.get("/plugins/docs", response_class=HTMLResponse, summary="Documentação de plugins")
    def tela_plugins_docs(request: Request) -> HTMLResponse:
        path = plugins_mod.documentacao_path()
        md = ""
        if path.is_file():
            md = path.read_text(encoding="utf-8", errors="replace")
        else:
            md = "# Documentação não encontrada\n\nArquivo esperado: `docs/plugins.md`."
        ctx = ui_context("plugins")
        ctx["html"] = markdown_para_html(md)
        return TEMPLATES.TemplateResponse(request, "plugins_docs.html", ctx)

    @app.get("/api/plugins")
    def api_plugins() -> dict:
        return {
            "pasta": str(plugins_mod.pasta_plugins()),
            "plugins": [
                {
                    "id": p.id,
                    "nome": p.nome,
                    "versao": p.versao,
                    "descricao": p.descricao,
                    "autor": p.autor,
                    "caminho": p.caminho,
                    "habilitado": p.habilitado,
                    "padrao": bool(getattr(p, "padrao", False) or plugins_mod.eh_padrao(p.id)),
                    "erro": p.erro,
                    "abas": [{"id": a.id, "rotulo": a.rotulo, "href": a.href} for a in p.abas],
                }
                for p in plugins_mod.listar()
            ],
        }

    @app.get("/api/plugins/docs")
    def api_plugins_docs() -> dict:
        path = plugins_mod.documentacao_path()
        texto = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        return {"path": str(path), "markdown": texto}

    @app.post("/api/plugins/{plugin_id}/habilitar")
    def api_plugin_on(plugin_id: str) -> dict:
        plugins_mod.definir_habilitado(plugin_id, True)
        r = plugins_mod.recarregar_plugin(plugin_id)
        if not r.get("ok"):
            r = plugins_mod.recarregar_plugins()
        return {"ok": True, "id": plugin_id, "habilitado": True,
                "detail": r.get("detail") or "Plugin ativado.",
                "reload": r}

    @app.post("/api/plugins/{plugin_id}/desabilitar")
    def api_plugin_off(plugin_id: str) -> dict:
        plugins_mod.definir_habilitado(plugin_id, False)
        r = plugins_mod.recarregar_plugins()
        return {"ok": True, "id": plugin_id, "habilitado": False,
                "detail": r.get("detail") or "Plugin desativado e módulos recarregados.",
                "reload": r}

    @app.post("/api/plugins/recarregar")
    def api_plugins_recarregar() -> dict:
        return plugins_mod.recarregar_plugins()

    @app.post("/api/plugins/instalar")
    async def api_plugin_instalar(
        arquivo: UploadFile = File(...),
        atualizar: bool = Query(False),
    ) -> JSONResponse:
        dados = await arquivo.read()
        r = plugins_mod.instalar_de_zip(dados, atualizar=atualizar)
        if r.get("ok") and r.get("id"):
            rr = plugins_mod.recarregar_plugin(str(r["id"]))
            if not rr.get("ok"):
                rr = plugins_mod.recarregar_plugins()
            r["reload"] = rr
            r["detail"] = rr.get("detail") or r.get("detail")
        return JSONResponse(r, status_code=200 if r.get("ok") else 400)

    @app.post("/api/plugins/{plugin_id}/desinstalar")
    def api_plugin_desinstalar(plugin_id: str) -> JSONResponse:
        r = plugins_mod.desinstalar(plugin_id)
        if r.get("ok"):
            rr = plugins_mod.recarregar_plugins()
            r["reload"] = rr
            r["detail"] = "Plugin removido e módulos recarregados."
        return JSONResponse(r, status_code=200 if r.get("ok") else 404)

    @app.get("/api/plugins/exemplo.zip")
    def api_plugin_exemplo_zip():
        from fastapi.responses import FileResponse
        caminho = plugins_mod.caminho_exemplo_zip()
        if not caminho or not caminho.is_file():
            return JSONResponse({"detail": "Exemplo não encontrado."}, status_code=404)
        return FileResponse(
            caminho,
            media_type="application/zip",
            filename="plugins-exemplos.zip",
        )


    return app



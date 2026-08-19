"""Plugin: gerenciador de midia TC-506 Mídia (SC504)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

log = logging.getLogger("arauto.plugin.midia")
_DIR = Path(__file__).resolve().parent

def _page() -> str:
    return (_DIR / "page.html").read_text(encoding="utf-8")

def _conn(peer: str):
    from arauto.core import runtime
    return runtime.conexao_sc504(peer)

def setup(ctx):
    ctx.adicionar_aba("midia-tc506", "Midia TC-506M", "/plugins/midia-tc506/", ordem=40)

    @ctx.app.get("/plugins/midia-tc506/", response_class=HTMLResponse)
    def pagina(request: Request):
        scripts = '<script src="/plugins/midia-tc506/static/app.js"></script>'
        return ctx.render(
            request,
            titulo="Mídia TC-506M",
            conteudo=_page(),
            pagina="midia-tc506",
            scripts=scripts,
        )

    @ctx.app.get("/plugins/midia-tc506/static/app.js")
    def static_js():
        return FileResponse(_DIR / "app.js", media_type="application/javascript")

    @ctx.app.get("/plugins/midia-tc506/api/peers")
    def api_peers():
        from arauto.core import runtime
        return {
            "peers": [
                {"peer": p["peer"], "model": p.get("modelo") or ""}
                for p in runtime.peers_sc504()
            ]
        }

    @ctx.app.get("/plugins/midia-tc506/api/listar")
    def api_listar(peer: str = ""):
        conn = _conn(peer)
        if not conn:
            return JSONResponse({"ok": False, "detail": "Terminal nao conectado. Confira SC504 e se o aparelho esta linkado ao ArautoPY."}, status_code=404)
        try:
            estado = conn.ler_estado_midia()
            if estado.erro:
                return JSONResponse({"ok": False, "detail": estado.erro}, status_code=502)
            return {
                "ok": True,
                "arquivos": [
                    {
                        "slot": i.get("chave"),
                        "nome": i.get("arquivo"),
                        "path": i.get("caminho"),
                        "storage": i.get("destino"),
                        "tipo": i.get("tipo"),
                    }
                    for i in estado.inventario
                ],
                "sequencia": [s.to_dict() for s in estado.playlist],
                "sensor": [s.to_dict() for s in estado.sensor],
                "modelo": estado.modelo,
            }
        except Exception as exc:
            log.exception("listar midia")
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)


    @ctx.app.get("/plugins/midia-tc506/api/baixar")
    def api_baixar(peer: str = "", path: str = ""):
        """Baixa um arquivo que está gravado no terminal (IDvRecvFile)."""
        from fastapi.responses import Response
        from pathlib import PurePosixPath

        conn = _conn(peer)
        if not conn:
            return JSONResponse({"ok": False, "detail": "Terminal nao conectado."}, status_code=404)
        path = (path or "").strip().replace('\\', "/")
        if not path or ".." in path.split("/"):
            return JSONResponse({"ok": False, "detail": "Path invalido."}, status_code=400)
        try:
            dados = conn.receber_arquivo(path)
        except Exception as exc:
            log.exception("baixar midia")
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)
        if dados is None:
            return JSONResponse(
                {"ok": False, "detail": "Terminal nao devolveu o arquivo (status != 1 ou timeout)."},
                status_code=502,
            )
        nome = PurePosixPath(path).name or "midia.bin"
        # content-type generico; o browser usa o nome do arquivo
        return Response(
            content=dados,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{nome}"',
                "Content-Length": str(len(dados)),
            },
        )

    @ctx.app.post("/plugins/midia-tc506/api/upload")
    async def api_upload(peer: str = Form(...), arquivo: UploadFile = File(...)):
        from arauto.protocol import sc504_media as media
        conn = _conn(peer)
        if not conn:
            return JSONResponse({"ok": False, "detail": "Terminal nao conectado."}, status_code=404)
        nome = media.nome_seguro(Path(arquivo.filename or "media.bin").name)
        path = "INT_MEM/" + nome
        data = await arquivo.read()
        if not data:
            return JSONResponse({"ok": False, "detail": "Arquivo vazio."}, status_code=400)
        if not conn.enviar_arquivo(path, data):
            return JSONResponse({"ok": False, "detail": "Terminal nao confirmou o envio."}, status_code=502)
        try:
            raw = conn.receber_arquivo(media.ARQ_INVENTARIO) or b"[INT_MEM]\n"
            itens = media.analisar_inventario(raw.decode(media.CHARSET, errors="replace"))
            if not any(i.get("arquivo") == nome and i.get("destino") == "INT_MEM" for i in itens):
                n = len([i for i in itens if i.get("destino") == "INT_MEM"]) + 1
                itens.append({
                    "chave": "media%d" % n,
                    "arquivo": nome,
                    "destino": "INT_MEM",
                    "caminho": "INT_MEM/" + nome,
                    "tipo": media.tipo_da_extensao(nome),
                })
            texto = media.montar_inventario(itens)
            conn.enviar_arquivo(media.ARQ_INVENTARIO, texto.encode(media.CHARSET, errors="replace"))
            conn.atualizar_midias()
        except Exception:
            log.exception("all_medias apos upload")
        return {"ok": True, "path": path, "bytes": len(data)}

    @ctx.app.post("/plugins/midia-tc506/api/apagar")
    def api_apagar(corpo: dict):
        from arauto.protocol import sc504_media as media
        peer = str(corpo.get("peer") or "")
        path = str(corpo.get("path") or "")
        conn = _conn(peer)
        if not conn:
            return JSONResponse({"ok": False, "detail": "Terminal nao conectado."}, status_code=404)
        if not path:
            return JSONResponse({"ok": False, "detail": "Path vazio."}, status_code=400)
        if not conn.apagar_arquivo(path):
            return JSONResponse({"ok": False, "detail": "Apagar nao confirmado."}, status_code=502)
        try:
            nome = path.split("/")[-1]
            raw = conn.receber_arquivo(media.ARQ_INVENTARIO) or b""
            itens = [
                i for i in media.analisar_inventario(raw.decode(media.CHARSET, errors="replace"))
                if i.get("arquivo") != nome
            ]
            for i, it in enumerate(itens, 1):
                it["chave"] = "media%d" % i
            conn.enviar_arquivo(
                media.ARQ_INVENTARIO,
                media.montar_inventario(itens).encode(media.CHARSET, errors="replace"),
            )
            conn.atualizar_midias()
        except Exception:
            log.exception("all_medias apos delete")
        return {"ok": True, "path": path}

    @ctx.app.post("/plugins/midia-tc506/api/sequencia")
    def api_sequencia(corpo: dict):
        from arauto.protocol import sc504_media as media
        peer = str(corpo.get("peer") or "")
        itens_in = corpo.get("itens") or []
        conn = _conn(peer)
        if not conn:
            return JSONResponse({"ok": False, "detail": "Terminal nao conectado."}, status_code=404)
        seq = []
        for i in itens_in:
            caminho = str(i.get("path") or i.get("caminho") or "")
            if not caminho:
                continue
            seq.append(media.ItemPlaylist(
                caminho=caminho,
                tempo=int(i.get("tempo") or 5),
                vezes=int(i.get("vezes") or i.get("loops") or 1),
                imagem_fundo=str(i.get("imagem_fundo") or ""),
            ))
        texto = media.montar_playlist(seq)
        if not conn.enviar_arquivo(media.ARQ_PLAYLIST, texto.encode(media.CHARSET, errors="replace")):
            return JSONResponse({"ok": False, "detail": "Falha ao gravar medias.conf."}, status_code=502)
        conn.atualizar_midias()
        return {"ok": True, "itens": len(seq)}



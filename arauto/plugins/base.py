"""API pública para plugins do ArautoPY."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# request tipado de forma frouxa para não exigir FastAPI no import


@dataclass
class PluginTab:
    """Aba extra no cabeçalho da administração."""
    id: str
    rotulo: str
    href: str
    ordem: int = 100


@dataclass
class PluginInfo:
    id: str
    nome: str
    versao: str = "0.1.0"
    descricao: str = ""
    autor: str = ""
    caminho: str = ""
    habilitado: bool = True
    padrao: bool = False
    erro: str | None = None
    abas: list[PluginTab] = field(default_factory=list)


class Plugin:
    """Base opcional. Qualquer módulo com ``setup(ctx)`` também funciona.

    Exemplo mínimo::

        def setup(ctx):
            ctx.adicionar_aba("hello", "Olá", "/plugins/hello/")

            @ctx.app.get("/plugins/hello/")
            def pagina():
                return {"ok": True}
    """

    id: str = "plugin"
    nome: str = "Plugin"
    versao: str = "0.1.0"
    descricao: str = ""
    autor: str = ""

    def setup(self, ctx: "PluginContext") -> None:
        raise NotImplementedError


class PluginContext:
    """Ferramentas oferecidas ao plugin no momento do carregamento."""

    def __init__(self, app, service, plugin_id: str) -> None:
        self.app = app
        self.service = service
        self.plugin_id = plugin_id
        self._abas: list[PluginTab] = []
        self._hooks_query: list[Callable] = []


    def render(
        self,
        request,
        *,
        titulo: str,
        conteudo: str,
        pagina: str | None = None,
        scripts: str = "",
    ):
        """Renderiza conteúdo dentro do cabeçalho universal (base.html).

        Use isto em rotas de página do plugin em vez de devolver HTML completo
        com ``<header>`` próprio — as abas do sistema e dos outros plugins
        aparecem automaticamente.
        """
        from fastapi.templating import Jinja2Templates
        from fastapi.responses import HTMLResponse
        from ..core.settings import APP_VERSION, get_settings, resource_root
        from ..core import runtime
        from . import manager as plugins_manager

        settings = get_settings()
        templates = Jinja2Templates(directory=str(resource_root() / "web" / "templates"))
        pagina_id = pagina or self.plugin_id
        ctx = {
            "request": request,
            "pagina": pagina_id,
            "titulo": titulo,
            "conteudo": conteudo or "",
            "scripts": scripts or "",
            "versao": APP_VERSION,
            "loja": settings.store_name,
            "abas_plugins": [
                {"id": a.id, "rotulo": a.rotulo, "href": a.href}
                for a in plugins_manager.abas_ativas()
            ],
        }
        return templates.TemplateResponse(request, "plugin_host.html", ctx)

    def adicionar_aba(self, id: str, rotulo: str, href: str, ordem: int = 100) -> None:
        self._abas.append(PluginTab(id=id, rotulo=rotulo, href=href, ordem=ordem))

    def peers_sc504(self) -> list:
        """Terminais SC504 conectados agora (peer + modelo)."""
        from ..core import runtime
        return runtime.peers_sc504()

    def conexao_sc504(self, peer: str):
        """Objeto de conexão SC504 vivo, ou None.

        Permite ao plugin chamar ``receber_arquivo``, ``enviar_arquivo``,
        ``apagar_arquivo``, ``atualizar_midias`` na sessão já aberta.
        """
        from ..core import runtime
        return runtime.conexao_sc504(peer)

    def ao_consultar(self, fn: Callable) -> Callable:
        """Registra callback ``fn(resultado, origem, canal)`` após cada consulta."""
        self._hooks_query.append(fn)
        return fn

    def registrar_tcp(
        self,
        host: str,
        port: int,
        handler,
        *,
        nome: str | None = None,
    ):
        """Sobe um servidor TCP em thread daemon.

        ``handler(conn, addr)`` é chamado a cada cliente. O plugin é responsável
        pelo protocolo (ler/escrever bytes). Retorna a thread iniciada.

        Exemplo::

            def handle(conn, addr):
                data = conn.recv(1024)
                conn.sendall(b"ok")
                conn.close()

            ctx.registrar_tcp("0.0.0.0", 9100, handle, nome="meu-tcp")
        """
        import socket
        import threading

        nome = nome or f"plugin-tcp-{self.plugin_id}-{port}"

        def _serve() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                sock.listen(32)
            except OSError:
                sock.close()
                raise
            while True:
                try:
                    client, address = sock.accept()
                except OSError:
                    break
                threading.Thread(
                    target=handler, args=(client, address),
                    name=f"{nome}-cli", daemon=True,
                ).start()

        t = threading.Thread(target=_serve, name=nome, daemon=True)
        t.start()
        return t



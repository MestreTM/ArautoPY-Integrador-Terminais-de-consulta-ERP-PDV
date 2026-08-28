#!/usr/bin/env python3
"""ArautoPY — Servidor de integração.

Ponto de entrada.

Modos:
    webviewer   terminal de consulta no navegador (padrão: 6689)
    api         API de integração para outros sistemas (padrão: 5589)
    sc501       servidor TCP dos terminais Gertec (padrão: 6500)
    todos       sobe os três (padrão)

Exemplos:
    python run.py
    python run.py --modo webviewer --porta-webviewer 6689
    python run.py --importar produtos.txt
    python run.py --config
    python run.py --sniffer 16510
    python run.py --proxy 16510 --destino 127.0.0.1:1597
    python run.py --analisar ~/.arauto/capturas/sessao-*.jsonl
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

import uvicorn

from arauto.core import applog
from arauto.core.service import QueryService
from arauto.core import runtime as arauto_runtime
from arauto.core.settings import (APP_DIR, APP_VERSION, AVISOS_INICIALIZACAO,
                                 CONFIG_FILE, get_settings)
from arauto.data.repositories import InternalRepository
from arauto.protocol.sc501 import Sc501Server
from arauto.protocol.sc504 import Sc504Server
from arauto.protocol import proxy, sniffer
from arauto.web.api import create_api
from arauto.web.viewer import create_viewer

log = logging.getLogger("arauto")

# Capturas ao lado do run.py, para quem está depurando achar sem procurar.
PASTA_CAPTURAS = Path(__file__).resolve().parent / "capturas"


def _tem_console() -> bool:
    """False no .exe gerado com --noconsole (sem prompt)."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return sys.stdout is not None and hasattr(sys.stdout, "isatty")
    return sys.stdout is not None and hasattr(sys.stdout, "write")


def _garantir_stdio() -> None:
    """No .exe --noconsole o Windows deixa stdout/stderr em None.

    O formatter do uvicorn chama ``stream.isatty()`` e quebra com
    ``AttributeError: 'NoneType' object has no attribute 'isatty'``.
    Redirecionamos para um sink descartável com isatty=False.
    """
    import io

    class _NullIO(io.TextIOBase):
        def write(self, s):  # noqa: ANN001
            return len(s) if isinstance(s, str) else 0

        def flush(self) -> None:
            return None

        def isatty(self) -> bool:
            return False

        @property
        def encoding(self) -> str:
            return "utf-8"

    if sys.stdout is None:
        sys.stdout = _NullIO()
    if sys.stderr is None:
        sys.stderr = _NullIO()


def dizer(*args, **kwargs) -> None:
    """print que não quebra quando não há console."""
    if not _tem_console():
        return
    try:
        print(*args, **kwargs)
    except Exception:
        pass

BANNER = r"""
    _                    _        ____  __   __
   / \   _ __ __ _ _   _| |_ ___ |  _ \ \ \ / /
  / _ \ | '__/ _` | | | | __/ _ \| |_) | \ V /
 / ___ \| | | (_| | |_| | || (_) |  __/   | |
/_/   \_\_|  \__,_|\__,_|\__\___/|_|      |_|   {versao}

  Servidor de integracao para terminais de consulta e automacao de varejo
"""


# Logging mínimo do uvicorn — sem ColorFormatter (não chama isatty).
# No .exe --noconsole o DefaultFormatter do uvicorn quebra em stream.isatty().
_UVICORN_LOG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"()": "logging.Formatter", "fmt": "%(levelname)s:     %(message)s"},
        "access": {"()": "logging.Formatter", "fmt": "%(message)s"},
    },
    "handlers": {
        "default": {"formatter": "default", "class": "logging.NullHandler"},
        "access": {"formatter": "access", "class": "logging.NullHandler"},
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "WARNING", "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": "WARNING", "propagate": False},
    },
}


class UvicornThread(threading.Thread):
    """Roda um app ASGI numa thread para que os três modos convivam."""

    def __init__(self, app, host: str, port: int, name: str) -> None:
        super().__init__(name=name, daemon=True)
        config = uvicorn.Config(
            app, host=host, port=port, log_level="warning",
            access_log=False, log_config=_UVICORN_LOG,
        )
        self.server = uvicorn.Server(config)
        self.server.install_signal_handlers = lambda: None  # o processo pai cuida
        self.label = name
        self.host = host
        self.port = port

    def run(self) -> None:
        try:
            self.server.run()
        except OSError as exc:
            from arauto.core.netutil import log_falha_porta
            log_falha_porta(log, self.label, self.port, exc, host=self.host)
        except Exception:
            log.exception("O servidor %s parou", self.label)

    def stop(self) -> None:
        self.server.should_exit = True


def configurar_log(verboso: bool) -> None:
    """Console, arquivo rotativo em ~/.arauto e buffer para a tela /logs."""
    applog.configurar(APP_DIR, verboso)


def mostrar_config() -> None:
    settings = get_settings()
    print(f"\nArquivo de configuração: {CONFIG_FILE}")
    print(f"Diretório da aplicação:  {APP_DIR}\n")
    for chave, valor in sorted(settings.as_dict().items()):
        if "PASSWORD" in chave or "API_KEY" in chave:
            valor = "•" * len(valor) if valor else "(vazio)"
        print(f"  {chave:<28} {valor}")
    print()


def importar_arquivo(caminho: Path) -> None:
    if not caminho.exists():
        print(f"Arquivo não encontrado: {caminho}", file=sys.stderr)
        raise SystemExit(2)
    repo = InternalRepository()
    total = repo.import_pipe_file(caminho)
    repo.close()
    print(f"{total} produtos importados para a base interna.")


def main() -> int:
    _garantir_stdio()
    settings = get_settings()

    parser = argparse.ArgumentParser(
        prog="arautopy",
        description="ArautoPY — Servidor de integração (consulta de preços e terminais).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--modo", default="todos",
                        choices=["todos", "webviewer", "api", "sc501", "sc504"],
                        help="qual serviço subir (padrão: todos)")
    parser.add_argument("--host", default=settings.get("BIND_HOST"),
                        help="endereço de escuta (padrão: %(default)s)")
    parser.add_argument("--porta-webviewer", type=int,
                        default=settings.get_int("PORT_WEBVIEWER"),
                        help="porta do WebViewer (padrão: %(default)s)")
    parser.add_argument("--porta-api", type=int, default=settings.get_int("PORT_API"),
                        help="porta da API (padrão: %(default)s)")
    parser.add_argument("--porta-sc501", type=int, default=settings.get_int("LAST_PORT_501"),
                        help="porta do protocolo SC501 (padrão: %(default)s)")
    parser.add_argument("--porta-sc504", type=int, default=settings.get_int("LAST_PORT_504"),
                        help="porta do protocolo SC504 (padrão: %(default)s)")
    parser.add_argument("--importar", metavar="ARQUIVO", type=Path,
                        help="importa um arquivo codigo|descricao|preco1|preco2 e sai")
    parser.add_argument("--proxy", type=int, metavar="PORTA",
                        help="intermedia terminal e TC Server original, gravando "
                             "a conversa dos dois lados para depuração")
    parser.add_argument("--destino", default="127.0.0.1:1597", metavar="HOST:PORTA",
                        help="onde o TC Server original escuta (padrão: %(default)s)")
    parser.add_argument("--silencioso", action="store_true",
                        help="com --proxy, não imprime o hexdump ao vivo")
    parser.add_argument("--analisar", metavar="ARQUIVO", type=Path,
                        help="lê um .jsonl gravado pelo --proxy e imprime a conversa")
    parser.add_argument("--sniffer", type=int, metavar="PORTA",
                        help="escuta a porta e despeja em hexadecimal tudo que o "
                             "terminal enviar, indicando o enquadramento provável")
    parser.add_argument("--passivo", action="store_true",
                        help="SC504 só escuta, não envia nada — para descobrir o "
                             "que o terminal manda espontaneamente")
    parser.add_argument("--debug-protocolo", action="store_true",
                        help="despeja em /logs os bytes trocados com os terminais")
    parser.add_argument("--config", action="store_true",
                        help="mostra a configuração atual e sai")
    parser.add_argument("-v", "--verboso", action="store_true", help="log detalhado")
    parser.add_argument("--tray", action="store_true",
                        help="ícone na bandeja + notificação (Windows; usado no logon)")
    parser.add_argument("--version", action="version", version=f"ArautoPY {APP_VERSION}")
    args = parser.parse_args()

    configurar_log(args.verboso)

    if args.config:
        mostrar_config()
        return 0

    if args.analisar:
        if not args.analisar.exists() and (PASTA_CAPTURAS / args.analisar.name).exists():
            args.analisar = PASTA_CAPTURAS / args.analisar.name
        if not args.analisar.exists():
            print(f"Arquivo não encontrado: {args.analisar}", file=sys.stderr)
            return 2
        print(proxy.analisar_arquivo(args.analisar))
        return 0

    if args.proxy:
        proxy.rodar(args.proxy, args.destino, host=args.host,
                    pasta=PASTA_CAPTURAS, silencioso=args.silencioso)
        return 0

    if args.sniffer:
        sniffer.rodar(args.sniffer, host=args.host, destino_dir=PASTA_CAPTURAS)
        return 0

    if args.importar:
        importar_arquivo(args.importar)
        return 0

    dizer(BANNER.format(versao=APP_VERSION))

    atalho = None
    if args.modo in ("todos", "webviewer"):
        try:
            from arauto.core import localurl as _localurl
            hostname = _localurl.hostname_efetivo(settings.get("LOCAL_HOSTNAME"))
            atalho = {
                "hostname": hostname,
                "url": _localurl.url_painel(hostname, args.porta_webviewer),
            }
        except Exception:
            log.debug("Atalho local não aplicado", exc_info=True)

    # A migração de dados acontece na importação de settings, antes de existir
    # logging; só agora dá para contar o que houve.
    for aviso in AVISOS_INICIALIZACAO:
        log.info(aviso)

    try:
        from arauto.core import autostart as _autostart
        _autostart.aplicar_se_configurado()
    except Exception:
        log.debug("Autostart: não foi possível reaplicar", exc_info=True)

    try:
        from arauto.core import updater as _updater
        _updater.verificar_em_background()
    except Exception:
        log.debug("Update check: não iniciado", exc_info=True)

    service = QueryService(settings)

    # Pacote de imagens EAN: baixa em background se ainda não houver base local.
    try:
        from arauto.core import product_image
        st = product_image.status_pacote()
        if not st.get("baixado") or st.get("ultimo_erro"):
            product_image.baixar_pacote_em_background()
            log.info("Download do pacote de imagens EAN iniciado em segundo plano")
        else:
            log.info(
                "Base de imagens local ok (%s arquivos em %s)",
                st.get("arquivos_locais") or st.get("arquivos") or 0,
                st.get("pasta"),
            )
    except Exception:
        log.exception("Falha ao iniciar download do pacote de imagens")

    base = service.repo.status()
    log.info("Base %s carregada com %s produto(s)", base["modo"], base["produtos"])

    threads: list = []
    sc501: Sc501Server | None = None
    sc504: Sc504Server | None = None

    # Aviso antecipado se a porta já estiver ocupada (mensagem clara, sem stack).
    from arauto.core.netutil import mensagem_falha_porta, testar_bind

    def _avisar_porta(servico: str, porta: int) -> bool:
        err = testar_bind(args.host, porta)
        if err is None:
            return True
        msg = mensagem_falha_porta(servico, porta, err, host=args.host)
        log.error("%s", msg)
        dizer(f"AVISO: {msg}")
        return False

    if args.modo in ("todos", "sc501") and settings.get_bool("AUTO_INIT_501", True):
        if _avisar_porta("SC501", args.porta_sc501):
            sc501 = Sc501Server(
                service, host=args.host, port=args.porta_sc501,
                passivo=settings.get_bool("SC501_PASSIVE", False),
            )
            sc501.start()

    # SC504 só sobe se pedido explicitamente ou habilitado na configuração:
    # a maioria das lojas tem só terminais SC501, e abrir porta à toa é
    # superfície de ataque sem contrapartida.
    if args.modo == "sc504" or (args.modo == "todos"
                                and settings.get_bool("AUTO_INIT_504", True)):
        if _avisar_porta("SC504", args.porta_sc504):
            sc504 = Sc504Server(
                service, host=args.host, port=args.porta_sc504,
                formato=settings.get("SC504_FRAME"),
                debug=args.debug_protocolo or settings.get_bool("PROTOCOL_DEBUG", False),
                passivo=args.passivo or settings.get_bool("SC504_PASSIVE", False),
            )
            sc504.start()

    arauto_runtime.registrar(
        service=service, sc501=sc501, sc504=sc504, modo=args.modo,
    )

    if args.modo in ("todos", "api"):
        if _avisar_porta("API", args.porta_api):
            t = UvicornThread(create_api(service), args.host, args.porta_api, "api")
            t.start()
            threads.append(t)

    if args.modo in ("todos", "webviewer"):
        if _avisar_porta("WebViewer", args.porta_webviewer):
            t = UvicornThread(create_viewer(service), args.host, args.porta_webviewer, "webviewer")
            t.start()
            threads.append(t)

    time.sleep(0.6)  # deixa o uvicorn abrir as portas antes de imprimir os links
    dizer("Serviços no ar:")
    for t in threads:
        alvo = "localhost" if t.host in ("0.0.0.0", "::") else t.host
        if t.label == "webviewer":
            dizer(f"  WebViewer   http://{alvo}:{t.port}/         terminal de consulta")
            dizer(f"              http://{alvo}:{t.port}/painel   painel do operador")
            dizer(f"              http://{alvo}:{t.port}/config   configuração")
            dizer(f"              http://{alvo}:{t.port}/logs     logs")
            dizer(f"              http://{alvo}:{t.port}/monitor  tráfego cru dos terminais")
        else:
            dizer(f"  API         http://{alvo}:{t.port}/docs     documentação interativa")
    if atalho:
        dizer(f"  Atalho      {atalho['url']}")
        try:
            from arauto.core import localurl as _localurl
            if settings.get_bool("OPEN_BROWSER_ON_START", True):
                _localurl.abrir_quando_pronto(atalho["url"], atraso_s=0.8)
        except Exception:
            log.debug("Não abri o navegador", exc_info=True)
    if sc501:
        dizer(f"  SC501       tcp://{args.host}:{args.porta_sc501}      TC-406/502/505/507")
    if sc504:
        dizer(f"  SC504       tcp://{args.host}:{args.porta_sc504}     TC-504/506M/508, GB-600/601")
    elif args.modo == "todos":
        dizer(f"  SC504       desligado (AUTO_INIT_504=false)")
    dizer("\nCtrl+C para encerrar.\n")

    parar = threading.Event()

    def encerrar(signum=None, frame=None):  # noqa: ARG001
        parar.set()

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    # .exe no Windows: ícone na bandeja (área de ícones ocultos).
    # Flags vêm de arauto/build_flags.py (gravadas pelo build_exe.bat).
    try:
        from arauto import build_flags as _flags
        tray_on = bool(getattr(_flags, "TRAY_ENABLED", True))
        tray_notify = bool(getattr(_flags, "TRAY_NOTIFY", True))
    except Exception:
        tray_on, tray_notify = True, True

    # --tray: logon via autostart.cmd; também funciona com python (não só .exe)
    usar_bandeja = (
        sys.platform == "win32"
        and tray_on
        and not args.proxy
        and not args.sniffer
        and (getattr(sys, "frozen", False) or getattr(args, "tray", False))
    )
    forcar_notificar = bool(getattr(args, "tray", False)) or tray_notify

    try:
        if usar_bandeja:
            try:
                from arauto.tray import run_tray
                run_tray(
                    porta_web=args.porta_webviewer,
                    host=args.host,
                    on_quit=encerrar,
                    notificar=forcar_notificar,
                    origem_logon=bool(getattr(args, "tray", False)),
                )
            except Exception:
                log.exception("Falha ao iniciar ícone da bandeja — modo espera")
                while not parar.wait(1.0):
                    pass
        else:
            while not parar.wait(1.0):
                pass
    finally:
        dizer("\nEncerrando…")
        for t in threads:
            t.stop()
        if sc501:
            sc501.stop()
        if sc504:
            sc504.stop()
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



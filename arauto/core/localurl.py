"""Atalho local http://arauto.localhost:6689/painel.

Nomes *.localhost resolvem para 127.0.0.1 sem arquivo hosts e sem administrador.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser

log = logging.getLogger("arauto.localurl")

HOSTNAME_PADRAO = "arauto.localhost"
PORTA_WEB_PADRAO = 6689


def hostname_efetivo(nome: str | None = None) -> str:
    n = (nome or "").strip().lower()
    if not n or n == "arauto.local":
        return HOSTNAME_PADRAO
    return n


def url_painel(hostname: str | None, porta_web: int, *_args, **_kwargs) -> str:
    host = hostname_efetivo(hostname)
    porta = int(porta_web or PORTA_WEB_PADRAO)
    return f"http://{host}:{porta}/painel"


def url_fallback(porta_web: int) -> str:
    return f"http://127.0.0.1:{int(porta_web or PORTA_WEB_PADRAO)}/painel"


def abrir_navegador(url: str) -> bool:
    if not url:
        return False
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        log.info("Sem DISPLAY/WAYLAND — não abro o navegador")
        return False
    try:
        ok = webbrowser.open(url, new=2)
        log.info("Navegador: %s (%s)", url, "ok" if ok else "pedido enviado")
        return True
    except Exception:
        log.debug("webbrowser.open falhou para %s", url, exc_info=True)
        return False


def abrir_quando_pronto(url: str, atraso_s: float = 1.4) -> None:
    def _go() -> None:
        abrir_navegador(url)

    t = threading.Timer(max(0.2, float(atraso_s)), _go)
    t.daemon = True
    t.start()

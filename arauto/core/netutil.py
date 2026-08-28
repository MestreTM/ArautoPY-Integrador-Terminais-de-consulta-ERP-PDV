"""Utilitários de rede (abertura de porta, mensagens amigáveis)."""
from __future__ import annotations

import errno
import logging
import socket


def porta_em_uso(exc: BaseException) -> bool:
    """True se o erro indica endereço/porta já em uso ou acesso negado à porta."""
    en = getattr(exc, "errno", None)
    win = getattr(exc, "winerror", None)
    # Linux EADDRINUSE=98, EACCES=13; macOS EADDRINUSE=48; Windows 10048/10013
    if en in (errno.EADDRINUSE, getattr(errno, "EADDRINUSE", 98), 48, 98, 13):
        return True
    if win in (10048, 10013):
        return True
    msg = str(exc).lower()
    return any(
        s in msg
        for s in (
            "address already in use",
            "only one usage of each socket address",
            "permissão de acesso",
            "access permission",
            "10048",
            "10013",
        )
    )


def mensagem_falha_porta(servico: str, porta: int, exc: BaseException, host: str = "0.0.0.0") -> str:
    """Texto claro quando não dá para escutar numa porta."""
    if porta_em_uso(exc):
        return (
            f"Não foi possível abrir a porta {porta} ({servico}). "
            f"Verifique se nenhum outro programa já está utilizando essa porta "
            f"(outro ArautoPY, TC Server Gertec, etc.) e tente novamente. "
            f"Host: {host}."
        )
    return (
        f"Não foi possível abrir a porta {porta} ({servico}) em {host}: {exc}"
    )


def log_falha_porta(log: logging.Logger, servico: str, porta: int, exc: BaseException,
                    host: str = "0.0.0.0") -> None:
    log.error("%s", mensagem_falha_porta(servico, porta, exc, host=host))
    win = getattr(exc, "winerror", None)
    if win == 10013:
        log.error(
            "No Windows o erro 10013 também pode ser porta reservada pelo "
            "sistema (Hyper-V/WSL). Confira com: "
            "netsh interface ipv4 show excludedportrange protocol=tcp"
        )


def testar_bind(host: str, porta: int) -> OSError | None:
    """Tenta bind rápido; devolve o OSError se falhar, senão None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, porta))
        return None
    except OSError as exc:
        return exc
    finally:
        try:
            sock.close()
        except OSError:
            pass

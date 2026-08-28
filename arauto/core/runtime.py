"""Referências ao processo em execução — permite recarregar módulos sem restart.

Mantém ponteiros para o QueryService e para os servidores SC501/SC504
iniciados em ``run.py``. A tela de configuração usa isso para aplicar
mudanças de base e de portas de terminal sem derrubar o processo inteiro.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger("arauto.runtime")

_lock = threading.RLock()
_service = None
_sc501 = None
_sc504 = None
_args_modo: str = "todos"


def registrar(*, service=None, sc501=None, sc504=None, modo: str | None = None) -> None:
    global _service, _sc501, _sc504, _args_modo
    with _lock:
        if service is not None:
            _service = service
        if sc501 is not None:
            _sc501 = sc501
        if sc504 is not None:
            _sc504 = sc504
        if modo is not None:
            _args_modo = modo


def service():
    return _service


def aplicar_base_produtos() -> dict:
    """Fecha o repositório atual e monta outro a partir das settings vigentes."""
    from .service import QueryService
    from ..data.repositories import build_repository

    with _lock:
        svc = _service
        if svc is None:
            return {"ok": False, "detail": "Serviço ainda não registrado."}
        antigo = svc.repo
        try:
            novo = build_repository(svc.settings)
        except Exception as exc:
            log.exception("Falha ao montar nova base de produtos")
            return {"ok": False, "detail": str(exc)}
        svc.repo = novo
        try:
            antigo.close()
        except Exception:
            log.debug("Falha ao fechar repositório antigo", exc_info=True)
        total = novo.count()
        log.info("Base de produtos reconfigurada em quente: %s (%d produtos)",
                 novo.mode, total)
        return {
            "ok": True,
            "modo": novo.mode,
            "produtos": total,
            "status": novo.status(),
        }


def reiniciar_terminais() -> dict:
    """Recria SC501/SC504 conforme settings (porta, frame, AUTO_INIT_504)."""
    from .settings import get_settings
    from ..protocol.sc501 import Sc501Server
    from ..protocol.sc504 import Sc504Server

    global _sc501, _sc504
    settings = get_settings()
    host = settings.get("BIND_HOST") or "0.0.0.0"
    detalhes: list[str] = []

    with _lock:
        svc = _service
        if svc is None:
            return {"ok": False, "detail": "Serviço ainda não registrado."}

        # SC501
        if _args_modo == "sc501" or (
            _args_modo == "todos" and settings.get_bool("AUTO_INIT_501", True)
        ):
            porta = settings.get_int("LAST_PORT_501", 6500)
            if _sc501 is not None:
                try:
                    _sc501.stop()
                except Exception:
                    log.exception("Erro ao parar SC501")
                _sc501 = None
                detalhes.append("SC501 parado")
            try:
                srv = Sc501Server(
                    svc, host=host, port=porta,
                    passivo=settings.get_bool("SC501_PASSIVE", False),
                )
                srv.start()
                _sc501 = srv
                detalhes.append(f"SC501 em {host}:{porta}")
            except Exception as exc:
                log.exception("Falha ao reiniciar SC501")
                detalhes.append(f"SC501 falhou: {exc}")
        elif _args_modo == "todos" and not settings.get_bool("AUTO_INIT_501", True):
            if _sc501 is not None:
                try:
                    _sc501.stop()
                except Exception:
                    log.exception("Erro ao parar SC501")
                _sc501 = None
            detalhes.append("SC501 desligado (AUTO_INIT_501=false)")

        # SC504
        if _args_modo == "sc504" or (
            _args_modo == "todos" and settings.get_bool("AUTO_INIT_504", True)
        ):
            porta = settings.get_int("LAST_PORT_504", 16510)
            if _sc504 is not None:
                try:
                    _sc504.stop()
                except Exception:
                    log.exception("Erro ao parar SC504")
                _sc504 = None
                detalhes.append("SC504 parado")
            try:
                srv = Sc504Server(
                    svc,
                    host=host,
                    port=porta,
                    formato=settings.get("SC504_FRAME"),
                    debug=settings.get_bool("PROTOCOL_DEBUG", False),
                    passivo=settings.get_bool("SC504_PASSIVE", False),
                )
                srv.start()
                _sc504 = srv
                detalhes.append(f"SC504 em {host}:{porta}")
            except Exception as exc:
                log.exception("Falha ao reiniciar SC504")
                detalhes.append(f"SC504 falhou: {exc}")
        else:
            if _sc504 is not None:
                try:
                    _sc504.stop()
                except Exception:
                    log.exception("Erro ao parar SC504")
                _sc504 = None
                detalhes.append("SC504 desligado (AUTO_INIT_504=false)")

    return {"ok": True, "detalhes": detalhes}



def servidor_sc504():
    """Instância viva do Sc504Server, ou None."""
    return _sc504


def servidor_sc501():
    return _sc501


def listar_conexoes_sc504() -> list:
    """Conexões SC504 ativas (objetos Sc504Connection)."""
    srv = _sc504
    if srv is None:
        return []
    return list((getattr(srv, "conexoes", None) or {}).values())


def _normalizar_mac(mac: str) -> str:
    """Normaliza MAC para comparação (AA:BB:CC:DD:EE:FF)."""
    s = (mac or "").strip().upper().replace("-", ":")
    if not s:
        return ""
    # aceita AABBCCDDEEFF
    hexonly = "".join(c for c in s if c in "0123456789ABCDEF")
    if len(hexonly) == 12 and ":" not in s:
        s = ":".join(hexonly[i:i + 2] for i in range(0, 12, 2))
    return s


def conexao_sc504(peer: str):
    """Conexão SC504 viva pelo peer ``ip:porta`` **ou** pelo MAC, ou None.

    O MAC vem do IDvGetUID e é o identificador estável do aparelho
    (o IP pode mudar entre sessões).
    """
    srv = _sc504
    if srv is None or not peer:
        return None
    conexoes = getattr(srv, "conexoes", None) or {}
    if peer in conexoes:
        return conexoes[peer]
    mac_alvo = _normalizar_mac(peer)
    if not mac_alvo:
        return None
    for conn in conexoes.values():
        mac = _normalizar_mac(getattr(conn, "mac", "") or "")
        if mac and mac == mac_alvo:
            return conn
    return None


def peers_sc504() -> list[dict]:
    """Resumo dos terminais SC504 conectados (para UI/plugins).

    ``id`` prefere o MAC (estável); se ainda não chegou o UID, cai no peer.
    """
    out = []
    for conn in listar_conexoes_sc504():
        term = getattr(conn, "terminal", None)
        peer = getattr(conn, "peer", "") or ""
        mac = _normalizar_mac(
            getattr(conn, "mac", "") or getattr(term, "mac", "") or ""
        )
        modelo = getattr(term, "model", None) or ""
        nome = (
            getattr(conn, "nome_aparelho", "")
            or getattr(term, "nome_aparelho", "")
            or ""
        )
        out.append({
            "peer": peer,
            "mac": mac,
            "id": mac or peer,  # chave estável para configuração
            "modelo": modelo,
            "nome_aparelho": nome,
            "tipo": getattr(term, "tipo", None),
        })
    return out



"""Acesso ao painel: senha com hash, cookie assinado, primeiro acesso."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

COOKIE = "arauto_sess"
ITERACOES = 200_000
VALIDADE_S = 30 * 24 * 3600


def _settings():
    from .settings import get_settings
    return get_settings()


def secret() -> bytes:
    s = _settings()
    atual = (s.get("SESSION_SECRET") or "").strip()
    if len(atual) < 16:
        atual = secrets.token_hex(32)
        s.set("SESSION_SECRET", atual)
    return atual.encode("utf-8")


def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt.encode("ascii"), ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${salt}${dk.hex()}"


def verificar_senha(senha: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = (stored or "").split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        n = int(iters)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt.encode("ascii"), n)
    return hmac.compare_digest(dk.hex(), digest)


def setup_completo() -> bool:
    return _settings().get_bool("SETUP_COMPLETE", False)


def tem_conta() -> bool:
    s = _settings()
    return bool((s.get("ADMIN_USER") or "").strip() and (s.get("ADMIN_PASSWORD_HASH") or "").strip())


def gravar_conta(usuario: str, senha: str) -> None:
    usuario = (usuario or "").strip()
    if len(usuario) < 2:
        raise ValueError("Usuário precisa ter pelo menos 2 caracteres.")
    if len(senha or "") < 6:
        raise ValueError("Senha precisa ter pelo menos 6 caracteres.")
    s = _settings()
    s.set("ADMIN_USER", usuario)
    s.set("ADMIN_PASSWORD_HASH", hash_senha(senha))


def marcar_completo() -> None:
    _settings().set("SETUP_COMPLETE", "true")


def token_sessao(usuario: str) -> str:
    exp = int(time.time()) + VALIDADE_S
    payload = f"{usuario}|{exp}"
    sig = hmac.new(secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def ler_sessao(token: str) -> str | None:
    if not token or token.count("|") < 2:
        return None
    usuario, exp_s, sig = token.rsplit("|", 2)
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if exp < int(time.time()):
        return None
    payload = f"{usuario}|{exp}"
    esperado = hmac.new(secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado, sig):
        return None
    atual = (_settings().get("ADMIN_USER") or "").strip()
    if atual and usuario != atual:
        return None
    return usuario


def usuario_request(request: Request) -> str | None:
    return ler_sessao(request.cookies.get(COOKIE) or "")


def aplicar_cookie(resp, usuario: str):
    resp.set_cookie(
        COOKIE,
        token_sessao(usuario),
        max_age=VALIDADE_S,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp


def limpar_cookie(resp):
    resp.delete_cookie(COOKIE, path="/")
    return resp


def autenticar(usuario: str, senha: str) -> str | None:
    s = _settings()
    esperado = (s.get("ADMIN_USER") or "").strip()
    digest = s.get("ADMIN_PASSWORD_HASH") or ""
    if not esperado or not digest:
        return None
    if usuario.strip() != esperado:
        return None
    if not verificar_senha(senha, digest):
        return None
    return esperado


_PUBLICOS_EXATOS = {"/", "/login", "/logout", "/setup", "/favicon.ico", "/api/status"}
_PUBLICOS_PREFIXO = (
    "/static/",
    "/consulta/",
    "/api/auth/login",
)
_SETUP_API = (
    "/api/config/dialectos",
    "/api/config/testar-sql",
    "/api/config/listar-tabelas",
    "/api/config/listar-colunas",
    "/api/config/amostra-produto",
    "/api/autostart",
    "/api/plugins/catalogo",
    "/api/plugins/catalogo/refresh",
)


def _quer_html(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept or request.method == "GET" and not request.url.path.startswith("/api/")


def _publico(path: str) -> bool:
    if path in _PUBLICOS_EXATOS:
        return True
    if any(path.startswith(p) for p in _PUBLICOS_PREFIXO):
        return True
    if path.startswith("/api/imagens/") and path.count("/") == 3:
        return True
    return False


async def middleware_acesso(request: Request, call_next):
    path = request.url.path or "/"
    if _publico(path):
        return await call_next(request)

    completo = setup_completo()
    if not completo:
        if path.startswith("/setup") or path in _SETUP_API or path.startswith("/api/setup"):
            return await call_next(request)
        if path.startswith("/api/plugins/") and ("instalar" in path or path.endswith("/icone")):
            return await call_next(request)
        if _quer_html(request):
            return RedirectResponse("/setup", status_code=303)
        return JSONResponse({"detail": "Conclua o assistente de instalação."}, status_code=403)

    if usuario_request(request):
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse({"detail": "Faça login no painel."}, status_code=401)
    nxt = quote(path)
    return RedirectResponse(f"/login?next={nxt}", status_code=303)

"""Atualização do ArautoPY a partir do repositório oficial no GitHub.

Repositório fixo (não configurável pelo usuário):
  MestreTM/ArautoPY-Integrador-Terminais-de-consulta-ERP-PDV

Changelog:
  https://raw.githubusercontent.com/.../main/changelog.md
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

log = logging.getLogger("arauto.updater")

# --- constantes oficiais (não expostas na config editável) ---
GITHUB_REPO = "MestreTM/ArautoPY-Integrador-Terminais-de-consulta-ERP-PDV"
GITHUB_ASSET = "ArautoPY.zip"
CHANGELOG_URL = (
    "https://raw.githubusercontent.com/"
    "MestreTM/ArautoPY-Integrador-Terminais-de-consulta-ERP-PDV/"
    "refs/heads/main/changelog.md"
)
REPO_URL = f"https://github.com/{GITHUB_REPO}"

_USER_AGENT = "ArautoPY-Updater"
_estado_lock = threading.Lock()
_ultimo_check: dict[str, Any] = {}
_em_andamento = False
_changelog_cache: dict[str, Any] = {"texto": "", "erro": ""}


def raiz_instalacao() -> Path:
    """Pasta que contém run.py / pacote arauto (não o APP_DIR de dados)."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def versao_local() -> str:
    from .settings import APP_VERSION
    return str(APP_VERSION)


def _parse_versao(texto: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", texto or "")
    if not nums:
        return (0,)
    return tuple(int(x) for x in nums[:4])


def _mais_nova(remota: str, local: str) -> bool:
    return _parse_versao(remota) > _parse_versao(local)


def _http_json(url: str, timeout: int = 25) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _http_download(url: str, destino: Path, timeout: int = 180) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(destino, "wb") as out:
        shutil.copyfileobj(resp, out)


def status() -> dict:
    with _estado_lock:
        ultimo = dict(_ultimo_check)
        andamento = _em_andamento
    import sys
    return {
        "ok": True,
        "versao_local": versao_local(),
        "repo": GITHUB_REPO,
        "repo_url": REPO_URL,
        "configurado": True,
        "em_andamento": andamento,
        "ultimo": ultimo,
        "frozen": bool(getattr(sys, "frozen", False)),
        "raiz": str(raiz_instalacao()),
    }


def changelog() -> dict:
    """Baixa o changelog.md e converte com o mesmo leitor das docs de plugins."""
    global _changelog_cache
    from ..plugins.markdown_lite import para_html

    def _pack(texto: str, **extra) -> dict:
        return {
            "ok": True,
            "markdown": texto,
            "html": para_html(texto),
            "url": CHANGELOG_URL,
            **extra,
        }

    try:
        texto = _http_text(CHANGELOG_URL)
        with _estado_lock:
            _changelog_cache = {"texto": texto, "erro": ""}
        return _pack(texto)
    except Exception as exc:
        log.debug("changelog: %s", exc)
        with _estado_lock:
            cached = _changelog_cache.get("texto") or ""
        if cached:
            return _pack(cached, detail=f"Usando cache local (rede: {exc})")
        return {
            "ok": False,
            "markdown": "",
            "html": f"<p>Não foi possível carregar o changelog: {exc}</p>",
            "url": CHANGELOG_URL,
            "detail": f"Não foi possível carregar o changelog: {exc}",
        }



def _latest_via_redirect() -> dict | None:
    """Descobre a tag do último release sem a API (evita rate limit).

    Segue o redirect de ``/releases/latest`` → ``/releases/tag/vX.Y.Z``
    e monta a URL pública do asset ``ArautoPY.zip``.
    """
    latest = f"{REPO_URL}/releases/latest"
    req = urllib.request.Request(
        latest,
        headers={"User-Agent": _USER_AGENT},
        method="GET",
    )
    try:
        # Não seguir redirect automaticamente para ler o Location / URL final
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
        # Usar urlopen normal — ele segue redirects; a URL final tem a tag
        with urllib.request.urlopen(req, timeout=25) as resp:
            final = resp.geturl() or ""
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            final = exc.headers.get("Location") or ""
        else:
            log.debug("latest redirect HTTP %s", exc.code)
            return None
    except Exception as exc:
        log.debug("latest redirect: %s", exc)
        return None

    # .../releases/tag/v1.0.0
    m = re.search(r"/releases/tag/([^/?#]+)", final)
    if not m:
        log.debug("URL final sem tag: %s", final)
        return None
    from urllib.parse import unquote
    tag = unquote(m.group(1))
    asset_url = f"{REPO_URL}/releases/latest/download/{GITHUB_ASSET}"
    return {
        "tag": tag,
        "nome": tag,
        "html_url": f"{REPO_URL}/releases/tag/{tag}",
        "asset_url": asset_url,
        "asset_nome": GITHUB_ASSET,
        "body": "",
        "publicado": "",
        "via": "redirect",
    }


def _latest_via_api() -> dict | None:
    """Consulta a API oficial de releases (pode bater rate limit)."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    dados = _http_json(url)
    if not isinstance(dados, dict):
        return None
    tag = str(dados.get("tag_name") or "").strip()
    if not tag:
        return None
    preferido = GITHUB_ASSET.lower()
    asset_url = ""
    asset_nome = ""
    for a in dados.get("assets") or []:
        if not isinstance(a, dict):
            continue
        an = str(a.get("name") or "")
        if an.lower() == preferido:
            asset_url = str(a.get("browser_download_url") or "")
            asset_nome = an
            break
    if not asset_url:
        for a in dados.get("assets") or []:
            if not isinstance(a, dict):
                continue
            an = str(a.get("name") or "")
            if an.lower().endswith(".zip"):
                asset_url = str(a.get("browser_download_url") or "")
                asset_nome = an
                break
    if not asset_url:
        asset_url = f"{REPO_URL}/releases/latest/download/{GITHUB_ASSET}"
        asset_nome = GITHUB_ASSET
    return {
        "tag": tag,
        "nome": str(dados.get("name") or tag),
        "html_url": str(dados.get("html_url") or ""),
        "asset_url": asset_url,
        "asset_nome": asset_nome,
        "body": str(dados.get("body") or "")[:4000],
        "publicado": str(dados.get("published_at") or ""),
        "via": "api",
    }


def verificar() -> dict:
    """Consulta o GitHub Releases e compara com a versão local."""
    global _ultimo_check
    import sys

    if getattr(sys, "frozen", False):
        return {
            "ok": False,
            "detail": (
                "Versão compilada (.exe): baixe o release manualmente em "
                f"{REPO_URL}/releases"
            ),
            "versao_local": versao_local(),
            "repo": GITHUB_REPO,
            "repo_url": REPO_URL,
        }

    info = None
    api_erro = None
    try:
        info = _latest_via_api()
    except urllib.error.HTTPError as exc:
        api_erro = exc
        if exc.code == 404:
            # tenta fallback antes de desistir
            pass
        elif exc.code == 403:
            log.info("API GitHub rate limit/403 — usando fallback por redirect")
        else:
            log.debug("API GitHub HTTP %s — fallback", exc.code)
    except Exception as exc:
        api_erro = exc
        log.debug("API GitHub falhou: %s — fallback", exc)

    if not info:
        info = _latest_via_redirect()

    if not info:
        if isinstance(api_erro, urllib.error.HTTPError) and api_erro.code == 404:
            return {
                "ok": False,
                "detail": (
                    "Nenhum release publicado ainda neste repositório. "
                    f"Crie um release em {REPO_URL}/releases com o asset "
                    f"{GITHUB_ASSET}."
                ),
                "versao_local": versao_local(),
                "repo": GITHUB_REPO,
                "repo_url": REPO_URL,
            }
        if isinstance(api_erro, urllib.error.HTTPError) and api_erro.code == 403:
            return {
                "ok": False,
                "detail": (
                    "GitHub temporariamente limitou consultas (rate limit). "
                    "Aguarde alguns minutos e tente de novo, ou abra "
                    f"{REPO_URL}/releases"
                ),
                "versao_local": versao_local(),
                "repo": GITHUB_REPO,
                "repo_url": REPO_URL,
            }
        return {
            "ok": False,
            "detail": (
                f"Não foi possível consultar o GitHub ({api_erro or 'sem resposta'}). "
                f"Veja {REPO_URL}/releases"
            ),
            "versao_local": versao_local(),
            "repo": GITHUB_REPO,
            "repo_url": REPO_URL,
        }

    tag = info["tag"]
    local = versao_local()
    disponivel = bool(tag) and _mais_nova(tag, local)
    resultado = {
        "ok": True,
        "versao_local": local,
        "versao_remota": tag,
        "nome_release": info.get("nome") or tag,
        "notas": info.get("body") or "",
        "url_release": info.get("html_url") or f"{REPO_URL}/releases",
        "publicado": info.get("publicado") or "",
        "asset": info.get("asset_nome") or GITHUB_ASSET,
        "asset_url": info.get("asset_url") or "",
        "atualizacao_disponivel": disponivel,
        "repo": GITHUB_REPO,
        "repo_url": REPO_URL,
        "via": info.get("via") or "",
        "detail": (
            f"Nova versão {tag} disponível."
            if disponivel
            else f"Já está na versão mais recente ({local})."
        ),
    }
    with _estado_lock:
        _ultimo_check = dict(resultado)
    return resultado


def _encontrar_raiz_no_zip(extracao: Path) -> Path:
    filhos = [p for p in extracao.iterdir() if p.name not in (".", "..")]
    if len(filhos) == 1 and filhos[0].is_dir():
        cand = filhos[0]
        if (cand / "run.py").is_file() or (cand / "arauto").is_dir():
            return cand
    if (extracao / "run.py").is_file() or (extracao / "arauto").is_dir():
        return extracao
    for p in extracao.rglob("run.py"):
        return p.parent
    return extracao


_IGNORAR = {
    ".venv", "venv", "__pycache__", ".git", "capturas", ".idea",
    "node_modules", "dist", "build",
}


def _copiar_atualizacao(origem: Path, destino: Path) -> list[str]:
    copiados: list[str] = []
    for src in origem.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(origem)
        if any(part in _IGNORAR for part in rel.parts):
            continue
        if rel.suffix == ".pyc":
            continue
        dst = destino / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copiados.append(rel.as_posix())
    return copiados


def aplicar(url: str | None = None) -> dict:
    global _em_andamento
    import sys

    with _estado_lock:
        if _em_andamento:
            return {"ok": False, "detail": "Já existe uma atualização em andamento."}
        _em_andamento = True

    try:
        if getattr(sys, "frozen", False):
            return {
                "ok": False,
                "detail": f"Atualização automática indisponível no .exe. Baixe em {REPO_URL}/releases",
            }

        info = verificar() if not url else None
        download_url = (url or "").strip()
        if not download_url:
            if not info or not info.get("ok"):
                return info or {"ok": False, "detail": "Falha ao verificar."}
            if not info.get("atualizacao_disponivel"):
                return {
                    "ok": False,
                    "detail": info.get("detail") or "Nada para atualizar.",
                    "versao_local": info.get("versao_local"),
                    "versao_remota": info.get("versao_remota"),
                }
            download_url = str(info.get("asset_url") or "")
        if not download_url:
            return {"ok": False, "detail": "URL de download vazia."}

        raiz = raiz_instalacao()
        if not (raiz / "run.py").is_file() and not (raiz / "arauto").is_dir():
            return {"ok": False, "detail": f"Raiz de instalação inválida: {raiz}"}

        tmp = Path(tempfile.mkdtemp(prefix="arautopy-update-"))
        zip_path = tmp / "update.zip"
        extracao = tmp / "extract"
        extracao.mkdir()
        backup = tmp / "backup"
        try:
            log.info("Baixando atualização: %s", download_url)
            _http_download(download_url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extracao)
            fonte = _encontrar_raiz_no_zip(extracao)
            backup.mkdir()
            for nome in ("run.py", "requirements.txt"):
                src = raiz / nome
                if src.is_file():
                    shutil.copy2(src, backup / nome)
            if (raiz / "arauto").is_dir():
                shutil.copytree(
                    raiz / "arauto",
                    backup / "arauto",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                    dirs_exist_ok=True,
                )

            copiados = _copiar_atualizacao(fonte, raiz)
            log.info("Atualização aplicada: %d arquivo(s) em %s", len(copiados), raiz)
            return {
                "ok": True,
                "detail": (
                    f"Atualização aplicada ({len(copiados)} arquivos). "
                    "Reinicie o ArautoPY para carregar a nova versão."
                ),
                "arquivos": len(copiados),
                "versao_remota": (info or {}).get("versao_remota") if info else None,
                "raiz": str(raiz),
                "reinicio_necessario": True,
            }
        except Exception as exc:
            log.exception("aplicar update")
            try:
                if backup.exists():
                    _copiar_atualizacao(backup, raiz)
            except Exception:
                log.exception("falha ao restaurar backup")
            return {"ok": False, "detail": f"Falha na atualização: {exc}"}
        finally:
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except Exception:
                pass
    finally:
        with _estado_lock:
            _em_andamento = False


def verificar_em_background() -> None:
    """Check discreto na subida (só log)."""
    def _job() -> None:
        try:
            r = verificar()
            if r.get("atualizacao_disponivel"):
                log.info(
                    "Atualização disponível: %s → %s (%s)",
                    r.get("versao_local"),
                    r.get("versao_remota"),
                    r.get("url_release") or REPO_URL,
                )
        except Exception:
            log.debug("Update check falhou", exc_info=True)

    threading.Thread(target=_job, name="arauto-update-check", daemon=True).start()

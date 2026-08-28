"""Catálogo híbrido de plugins (local + online).

Não substitui o carregador em ``arauto.plugins.manager``: só descobre,
compara versões e instala/atualiza a partir do índice público.
Plugins sem estado online continuam 100% locais.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import shutil
import tarfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import APP_DIR, APP_VERSION

log = logging.getLogger("arauto.plugin_store")

INDEX_URL = "https://mestretm.github.io/ArautoPY-Plugins/index.json"
CATALOGO_BASE = "https://mestretm.github.io/ArautoPY-Plugins/"
CACHE_TTL_S = 12 * 60
UA = "ArautoPY-PluginStore/1.0"

ESTADO_DIR_NOME = ".estado_plugins"
BACKUP_DIR_NOME = "_backup"
AUDIT_LOG = "auditoria.log"

_lock = threading.RLock()
_cache_index: dict[str, Any] = {"quando": 0.0, "itens": [], "erro": ""}


def _plugins_dir() -> Path:
    from ..plugins.manager import pasta_plugins
    return pasta_plugins()


def _estado_dir() -> Path:
    d = _plugins_dir() / ESTADO_DIR_NOME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_dir() -> Path:
    d = _plugins_dir() / BACKUP_DIR_NOME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _audit(msg: str) -> None:
    linha = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}\n"
    try:
        path = _backup_dir() / AUDIT_LOG
        with path.open("a", encoding="utf-8") as fh:
            fh.write(linha)
    except OSError:
        pass
    log.info("%s", msg)


def _parse_versao(txt: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", txt or "")]
    return tuple(nums[:4] or [0])


def versao_maior(a: str, b: str) -> bool:
    """True se a > b."""
    return _parse_versao(a) > _parse_versao(b)


def host_atende(min_versao: str | None) -> bool:
    if not min_versao:
        return True
    return _parse_versao(APP_VERSION) >= _parse_versao(min_versao)


def _sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _sha256_arquivo(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for bloco in iter(lambda: fh.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler_plugin_json(pasta: Path) -> dict:
    meta = {
        "id": pasta.name,
        "nome": pasta.name,
        "versao": "?",
        "descricao": "",
        "autor": "",
    }
    arq = pasta / "plugin.json"
    if arq.is_file():
        try:
            bruto = json.loads(arq.read_text(encoding="utf-8"))
            if isinstance(bruto, dict):
                meta.update({k: bruto.get(k, meta.get(k, "")) for k in (
                    "id", "nome", "versao", "descricao", "autor",
                    "min_versao_app", "repo", "tag", "checksum_sha256",
                    "dependencias_pip",
                ) if k in bruto or k in meta})
                for k in ("min_versao_app", "repo", "tag", "checksum_sha256"):
                    if k in bruto:
                        meta[k] = bruto.get(k) or ""
                if "dependencias_pip" in bruto:
                    deps = bruto.get("dependencias_pip") or []
                    meta["dependencias_pip"] = list(deps) if isinstance(deps, list) else []
        except Exception:
            log.debug("plugin.json ilegível em %s", pasta)
    meta["id"] = str(meta.get("id") or pasta.name)
    return meta


def _estado_path(plugin_id: str) -> Path:
    return _estado_dir() / f"{plugin_id}.json"


def ler_estado(plugin_id: str) -> dict:
    path = _estado_path(plugin_id)
    if not path.is_file():
        return {
            "origem": "local",
            "repo": "",
            "tag_instalada": "",
            "instalado_em": "",
            "checksum_sha256": "",
            "hash_plugin_py": "",
            "atualizado_manualmente_depois": False,
        }
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(dados, dict):
            dados.setdefault("origem", "local")
            return dados
    except Exception:
        pass
    return {"origem": "local"}


def gravar_estado(plugin_id: str, dados: dict) -> None:
    path = _estado_path(plugin_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _hash_plugin_py(pasta: Path) -> str:
    return _sha256_arquivo(pasta / "plugin.py") or _sha256_arquivo(pasta / "__init__.py")


def listar_instalados() -> list[dict]:
    """Lê plugins/ + .estado_plugins/. Sempre offline."""
    from ..plugins import manager as mgr
    itens = []
    for info in mgr.listar():
        pasta = Path(info.caminho)
        meta = _ler_plugin_json(pasta)
        est = ler_estado(info.id)
        hash_atual = _hash_plugin_py(pasta)
        hash_gravado = str(est.get("hash_plugin_py") or "")
        modificado = bool(est.get("atualizado_manualmente_depois"))
        if est.get("origem") == "online" and hash_gravado and hash_atual and hash_atual != hash_gravado:
            modificado = True
            if not est.get("atualizado_manualmente_depois"):
                est["atualizado_manualmente_depois"] = True
                try:
                    gravar_estado(info.id, est)
                except OSError:
                    pass
        itens.append({
            "id": info.id,
            "nome": info.nome or meta.get("nome") or info.id,
            "versao": info.versao or meta.get("versao") or "?",
            "descricao": info.descricao or meta.get("descricao") or "",
            "autor": info.autor or meta.get("autor") or "",
            "habilitado": info.habilitado,
            "padrao": info.padrao,
            "erro": info.erro or "",
            "abas": [{"id": a.id, "rotulo": a.rotulo, "href": a.href} for a in (info.abas or [])],
            "origem": est.get("origem") or "local",
            "repo": est.get("repo") or meta.get("repo") or "",
            "tag": est.get("tag_instalada") or meta.get("tag") or "",
            "min_versao_app": meta.get("min_versao_app") or "",
            "dependencias_pip": meta.get("dependencias_pip") or [],
            "modificado_localmente": modificado,
            "atualizavel": False,
        })
    return itens


def _http_get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(20 * 1024 * 1024)


def buscar_catalogo_online(forcar_refresh: bool = False) -> list[dict]:
    """GET index.json via jsDelivr. Rede falhou → [] ou cache. Nunca explode."""
    agora = time.time()
    with _lock:
        if (
            not forcar_refresh
            and _cache_index["itens"]
            and (agora - float(_cache_index["quando"] or 0)) < CACHE_TTL_S
        ):
            return list(_cache_index["itens"])
        ultimo = list(_cache_index["itens"])
    try:
        bruto = _http_get(INDEX_URL)
        dados = json.loads(bruto.decode("utf-8"))
        if isinstance(dados, dict):
            dados = dados.get("plugins") or dados.get("itens") or []
        itens = []
        for row in dados if isinstance(dados, list) else []:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("id") or "").strip()
            if not pid:
                continue
            itens.append({
                "id": pid,
                "repo": str(row.get("repo") or ""),
                "tag": str(row.get("tag") or ""),
                "nome": str(row.get("nome") or row.get("name") or pid),
                "descricao": str(row.get("descricao") or row.get("description") or ""),
                "icone": str(row.get("icone") or row.get("icon") or ""),
                "min_versao_app": str(row.get("min_versao_app") or ""),
                "checksum_sha256": str(row.get("checksum_sha256") or ""),
                "dependencias_pip": list(row.get("dependencias_pip") or []),
                "autor": str(row.get("autor") or ""),
                "versao": str(row.get("versao") or row.get("tag") or "").lstrip("v"),
            })
            ico = itens[-1]["icone"]
            if ico and not ico.startswith("http://") and not ico.startswith("https://"):
                itens[-1]["icone"] = CATALOGO_BASE + ico.lstrip("/")
        with _lock:
            _cache_index["quando"] = agora
            _cache_index["itens"] = itens
            _cache_index["erro"] = ""
        return itens
    except Exception as exc:
        log.warning("Catálogo online indisponível: %s", exc)
        with _lock:
            _cache_index["erro"] = str(exc)
            if ultimo:
                return ultimo
        return []


def erro_catalogo() -> str:
    with _lock:
        return str(_cache_index.get("erro") or "")


def catalogo_mesclado(forcar_refresh: bool = False) -> dict:
    instalados = listar_instalados()
    online = buscar_catalogo_online(forcar_refresh=forcar_refresh)
    por_id = {p["id"]: p for p in instalados}
    updates = []
    for item in online:
        inst = por_id.get(item["id"])
        if not inst:
            item["status"] = "disponivel"
            item["atualizavel"] = False
            continue
        item["status"] = "instalado"
        item["instalado_versao"] = inst.get("versao")
        item["origem_instalada"] = inst.get("origem")
        item["modificado_localmente"] = inst.get("modificado_localmente")
        pode = (
            inst.get("origem") == "online"
            and bool(item.get("tag") or item.get("versao"))
            and versao_maior(item.get("versao") or item.get("tag") or "", inst.get("versao") or "")
        )
        item["atualizavel"] = bool(pode)
        if pode:
            inst["atualizavel"] = True
            inst["tag_disponivel"] = item.get("tag")
            inst["versao_disponivel"] = item.get("versao")
            updates.append({
                "id": inst["id"],
                "nome": inst["nome"],
                "versao_atual": inst.get("versao"),
                "versao_nova": item.get("versao") or item.get("tag"),
                "modificado_localmente": inst.get("modificado_localmente"),
            })
    return {
        "ok": True,
        "versao_app": APP_VERSION,
        "base": CATALOGO_BASE,
        "instalados": instalados,
        "online": online,
        "atualizacoes": updates,
        "catalogo_erro": erro_catalogo(),
        "catalogo_ok": not bool(erro_catalogo()) or bool(online),
    }


def diff_atualizacoes() -> list[dict]:
    return catalogo_mesclado().get("atualizacoes") or []


def _url_tarball(repo: str, tag: str) -> str:
    repo = repo.strip("/")
    tag = tag or "main"
    return f"https://codeload.github.com/{repo}/tar.gz/{tag}"


def _membros_seguros(tf: tarfile.TarFile, destino: Path) -> list[tarfile.TarInfo]:
    destino_res = destino.resolve()
    ok = []
    for m in tf.getmembers():
        alvo = (destino / m.name).resolve()
        if alvo != destino_res and destino_res not in alvo.parents:
            raise ValueError(f"Path traversal bloqueado: {m.name}")
        ok.append(m)
    return ok


def _achar_raiz_plugin(extraido: Path) -> Path | None:
    candidatos = list(extraido.rglob("plugin.json"))
    if not candidatos:
        candidatos = list(extraido.rglob("plugin.py"))
    if not candidatos:
        return None
    return candidatos[0].parent


def _copiar_plugin(origem: Path, destino: Path) -> None:
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(origem, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _backup_atual(plugin_id: str, versao: str) -> Path | None:
    src = _plugins_dir() / plugin_id
    if not src.is_dir():
        return None
    stamp = re.sub(r"[^a-zA-Z0-9._-]+", "_", versao or "sem_versao")
    dest = _backup_dir() / f"{plugin_id}_{stamp}"
    n = 1
    while dest.exists():
        dest = _backup_dir() / f"{plugin_id}_{stamp}_{n}"
        n += 1
    shutil.move(str(src), str(dest))
    return dest


def instalar_ou_atualizar(
    plugin_id: str,
    *,
    confirmar: bool = False,
    confirmar_modificado: bool = False,
    confirmar_checksum: bool = False,
    atualizar: bool = False,
) -> dict:
    if not confirmar:
        return {"ok": False, "detail": "Confirme explicitamente (confirmar=true)."}

    pid = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (plugin_id or "").strip()).strip("_")
    if not pid:
        return {"ok": False, "detail": "id inválido"}

    instalados = {p["id"]: p for p in listar_instalados()}
    inst = instalados.get(pid)

    if inst and inst.get("origem") == "local":
        return {
            "ok": False,
            "detail": "Este plugin foi instalado localmente. O catálogo online não o sobrescreve. Exclua e instale de novo pelo catálogo se quiser a versão online.",
        }

    if inst and inst.get("modificado_localmente") and not confirmar_modificado:
        return {
            "ok": False,
            "precisa_confirmar_modificado": True,
            "detail": "Este plugin foi modificado localmente. Envie confirmar_modificado=true para sobrescrever.",
        }

    catalogo = buscar_catalogo_online()
    item = next((x for x in catalogo if x["id"] == pid), None)
    if not item or not item.get("repo"):
        return {"ok": False, "detail": f"Plugin '{pid}' não está no catálogo online."}

    minv = item.get("min_versao_app") or ""
    if not host_atende(minv):
        return {
            "ok": False,
            "detail": (
                f"Este plugin requer ArautoPY {minv}+, "
                f"você está na {APP_VERSION}."
            ),
        }

    repo = item["repo"]
    tag = item.get("tag") or "main"
    url = _url_tarball(repo, tag)
    try:
        tarball = _http_get(url, timeout=60.0)
    except Exception as exc:
        return {"ok": False, "detail": f"Falha ao baixar {repo}@{tag}: {exc}"}

    esperado = (item.get("checksum_sha256") or "").strip().lower()
    obtido = _sha256_bytes(tarball)
    checksum_bate = (not esperado) or (obtido == esperado)
    if esperado and not checksum_bate and not confirmar_checksum:
        _audit(f"CHECKSUM_AVISO id={pid} repo={repo} tag={tag} esperado={esperado} obtido={obtido}")
        return {
            "ok": False,
            "precisa_confirmar_checksum": True,
            "detail": (
                "Checksum não confere — pode ser mudança de empacotamento do GitHub, "
                "não necessariamente adulteração. Continuar mesmo assim?"
            ),
            "esperado": esperado,
            "obtido": obtido,
        }
    if esperado and not checksum_bate:
        _audit(f"CHECKSUM_IGNORADO id={pid} repo={repo} tag={tag} obtido={obtido}")

    import tempfile
    destino_final = _plugins_dir() / pid
    backup = None
    try:
        with tempfile.TemporaryDirectory(prefix="arauto-pl-") as tmp:
            tmp_path = Path(tmp)
            with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:*") as tf:
                membros = _membros_seguros(tf, tmp_path)
                tf.extractall(tmp_path, members=membros)
            raiz = _achar_raiz_plugin(tmp_path)
            if raiz is None:
                return {"ok": False, "detail": "O pacote não contém plugin.json/plugin.py."}
            meta = _ler_plugin_json(raiz)
            real_id = str(meta.get("id") or pid)
            if real_id != pid:
                log.info("id do manifesto=%s, pasta=%s", real_id, pid)
            if inst:
                backup = _backup_atual(pid, inst.get("versao") or "")
            _copiar_plugin(raiz, destino_final)
    except ValueError as exc:
        return {"ok": False, "detail": str(exc)}
    except Exception as exc:
        if backup and backup.exists() and not destino_final.exists():
            try:
                shutil.move(str(backup), str(destino_final))
            except OSError:
                pass
        log.exception("Falha ao extrair plugin %s", pid)
        return {"ok": False, "detail": f"Falha na extração: {exc}"}

    hash_py = _hash_plugin_py(destino_final)
    estado = {
        "origem": "online",
        "repo": repo,
        "tag_instalada": tag,
        "instalado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checksum_sha256": esperado or obtido,
        "hash_plugin_py": hash_py,
        "atualizado_manualmente_depois": False,
    }
    gravar_estado(pid, estado)
    acao = "atualizar" if atualizar or inst else "instalar"
    _audit(f"{acao.upper()} id={pid} repo={repo} tag={tag} checksum_ok={checksum_bate}")

    deps = item.get("dependencias_pip") or meta.get("dependencias_pip") or []
    return {
        "ok": True,
        "id": pid,
        "acao": acao,
        "repo": repo,
        "tag": tag,
        "versao": meta.get("versao") or tag,
        "backup": str(backup) if backup else "",
        "dependencias_pip": deps,
        "pip_cmd": ("pip install " + " ".join(deps)) if deps else "",
        "detail": (
            f"Plugin {pid} {'atualizado' if acao == 'atualizar' else 'instalado'} "
            f"({repo}@{tag})."
        ),
    }

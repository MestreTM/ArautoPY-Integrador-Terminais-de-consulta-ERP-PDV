"""Descoberta, habilitação e carregamento de plugins."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

from ..core.settings import APP_DIR, resource_root
from .base import Plugin, PluginContext, PluginInfo, PluginTab

log = logging.getLogger("arauto.plugins")

PLUGINS_DIR = APP_DIR / "plugins"
ESTADO_ARQUIVO = APP_DIR / "plugins_estado.json"

_lock = threading.RLock()
_estado: dict[str, bool] = {}
_carregados: dict[str, PluginInfo] = {}
_hooks_query: list = []
_app_ref = None
_service_ref = None
_rotas_por_plugin: dict[str, list] = {}
_modulos_por_plugin: dict[str, str] = {}


def pasta_plugins() -> Path:
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    _garantir_plugins_padrao()
    return PLUGINS_DIR


# Plugins copiados automaticamente na primeira subida (se a pasta ainda não existir).
_PLUGINS_PADRAO = ("gerenciador_midia_tc506", "explorador_banco")


def eh_padrao(plugin_id: str) -> bool:
    """Plugins embutidos: não podem ser desinstalados, só desativados."""
    pid = (plugin_id or "").strip()
    return pid in _PLUGINS_PADRAO


def _garantir_plugins_padrao() -> None:
    """Instala plugins padrão e mantém o código alinhado com os exemplos embutidos."""
    import shutil
    exemplos = Path(__file__).resolve().parent / "exemplos"
    for nome in _PLUGINS_PADRAO:
        origem = exemplos / nome
        if not origem.is_dir():
            continue
        destino = PLUGINS_DIR / nome
        try:
            if not destino.exists():
                shutil.copytree(origem, destino)
                log.info("Plugin padrão instalado: %s", destino)
                continue
            # Atualiza arquivos do padrão (não apaga a pasta; sobrescreve o código)
            for src in origem.rglob("*"):
                if not src.is_file():
                    continue
                if src.name == "__pycache__" or "__pycache__" in src.parts:
                    continue
                rel = src.relative_to(origem)
                dst = destino / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except OSError:
            log.debug("Não foi possível instalar/atualizar plugin padrão %s", nome, exc_info=True)


def _ler_estado() -> dict[str, bool]:
    global _estado
    if ESTADO_ARQUIVO.is_file():
        try:
            dados = json.loads(ESTADO_ARQUIVO.read_text(encoding="utf-8"))
            _estado = {str(k): bool(v) for k, v in (dados.get("habilitados") or {}).items()}
        except Exception:
            _estado = {}
    return _estado


def _gravar_estado() -> None:
    pasta_plugins()
    ESTADO_ARQUIVO.write_text(
        json.dumps({"habilitados": _estado}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# Plugins que nascem desativados até o usuário ativar
_DESATIVADOS_POR_PADRAO = frozenset({"explorador_banco"})


def esta_habilitado(plugin_id: str) -> bool:
    st = _ler_estado()
    if plugin_id in st:
        return bool(st[plugin_id])
    # nunca configurado: a maioria sobe ativo; explorador BD fica off
    return plugin_id not in _DESATIVADOS_POR_PADRAO


def definir_habilitado(plugin_id: str, valor: bool) -> None:
    with _lock:
        _ler_estado()
        _estado[plugin_id] = bool(valor)
        _gravar_estado()


def _descobrir_pastas() -> list[Path]:
    base = pasta_plugins()
    pastas = []
    for p in sorted(base.iterdir()) if base.is_dir() else []:
        if p.is_dir() and (p / "plugin.py").is_file():
            pastas.append(p)
        elif p.is_dir() and (p / "__init__.py").is_file() and p.name != "__pycache__":
            # aceita pacote com setup no __init__
            pastas.append(p)
    return pastas


def _carregar_modulo(pasta: Path) -> ModuleType:
    entry = pasta / "plugin.py"
    if not entry.is_file():
        entry = pasta / "__init__.py"
    nome = f"arauto_plugin_{pasta.name}"
    spec = importlib.util.spec_from_file_location(nome, entry)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível carregar {entry}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    # pasta no path para imports relativos do plugin
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    spec.loader.exec_module(mod)
    return mod


def listar() -> list[PluginInfo]:
    """Lista plugins no disco (habilitados ou não), sem exigir app carregado."""
    infos: list[PluginInfo] = []
    for pasta in _descobrir_pastas():
        pid = pasta.name
        meta = {
            "id": pid,
            "nome": pid,
            "versao": "?",
            "descricao": "",
            "autor": "",
        }
        meta_file = pasta / "plugin.json"
        if meta_file.is_file():
            try:
                meta.update(json.loads(meta_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        info = PluginInfo(
            id=str(meta.get("id") or pid),
            nome=str(meta.get("nome") or pid),
            versao=str(meta.get("versao") or "?"),
            descricao=str(meta.get("descricao") or ""),
            autor=str(meta.get("autor") or ""),
            caminho=str(pasta),
            habilitado=esta_habilitado(pid),
            padrao=eh_padrao(pid),
        )
        if info.id in _carregados:
            c = _carregados[info.id]
            info.abas = list(c.abas)
            info.erro = c.erro
        infos.append(info)
    return infos


def carregar_todos(app, service) -> list[PluginInfo]:
    """Importa e executa setup() de cada plugin habilitado."""
    global _app_ref, _service_ref, _hooks_query
    _app_ref = app
    _service_ref = service
    _hooks_query = []
    _carregados.clear()
    resultados: list[PluginInfo] = []

    for pasta in _descobrir_pastas():
        pid = pasta.name
        meta = {"id": pid, "nome": pid, "versao": "0.1.0", "descricao": "", "autor": ""}
        meta_file = pasta / "plugin.json"
        if meta_file.is_file():
            try:
                meta.update(json.loads(meta_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        info = PluginInfo(
            id=str(meta.get("id") or pid),
            nome=str(meta.get("nome") or pid),
            versao=str(meta.get("versao") or "0.1.0"),
            descricao=str(meta.get("descricao") or ""),
            autor=str(meta.get("autor") or ""),
            caminho=str(pasta),
            habilitado=esta_habilitado(pid),
            padrao=eh_padrao(pid),
        )
        if not info.habilitado:
            _carregados[info.id] = info
            resultados.append(info)
            continue
        try:
            mod = _carregar_modulo(pasta)
            ctx = PluginContext(app, service, info.id)
            if hasattr(mod, "setup") and callable(mod.setup):
                mod.setup(ctx)
            elif hasattr(mod, "Plugin"):
                inst = mod.Plugin()
                if isinstance(inst, Plugin) or hasattr(inst, "setup"):
                    info.nome = getattr(inst, "nome", info.nome) or info.nome
                    info.versao = getattr(inst, "versao", info.versao) or info.versao
                    info.descricao = getattr(inst, "descricao", info.descricao) or info.descricao
                    info.autor = getattr(inst, "autor", info.autor) or info.autor
                    inst.setup(ctx)
            else:
                raise RuntimeError("plugin.py precisa definir setup(ctx) ou classe Plugin")
            info.abas = list(ctx._abas)
            _hooks_query.extend(ctx._hooks_query)
            log.info("Plugin carregado: %s v%s (%s)", info.nome, info.versao, pasta)
        except Exception as exc:
            log.exception("Falha ao carregar plugin %s", pid)
            info.erro = str(exc)
            info.habilitado = False
        _carregados[info.id] = info
        resultados.append(info)
    return resultados


def abas_ativas() -> list[PluginTab]:
    abas: list[PluginTab] = []
    for info in _carregados.values():
        if info.habilitado and not info.erro:
            abas.extend(info.abas)
    abas.sort(key=lambda a: (a.ordem, a.rotulo))
    return abas


def disparar_hooks_query(resultado, origem: str, canal: str) -> None:
    for fn in list(_hooks_query):
        try:
            fn(resultado, origem, canal)
        except Exception:
            log.exception("Hook de plugin falhou")




def _id_seguro(nome: str) -> str:
    import re
    n = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (nome or "").strip())
    return n.strip("_") or "plugin"


def instalar_de_zip(dados: bytes, *, atualizar: bool = False) -> dict:
    """Instala ou atualiza plugin a partir de um ZIP.

    Estruturas aceitas:
      - plugin.py na raiz do zip
      - pasta/plugin.py (usa o nome da pasta como id)
    """
    import io
    import shutil
    import tempfile
    import zipfile

    if not dados:
        return {"ok": False, "detail": "ZIP vazio."}
    try:
        zf = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile:
        return {"ok": False, "detail": "Arquivo não é um ZIP válido."}

    with zf:
        nomes = [n for n in zf.namelist() if not n.endswith("/")]
        if not nomes:
            return {"ok": False, "detail": "ZIP sem arquivos."}
        # segurança básica: sem path traversal
        for n in nomes:
            if ".." in Path(n).parts or n.startswith("/") or (len(n) > 1 and n[1] == ":"):
                return {"ok": False, "detail": f"Caminho inválido no ZIP: {n}"}

        with tempfile.TemporaryDirectory(prefix="arauto-plugin-") as tmp:
            tmp_path = Path(tmp)
            zf.extractall(tmp_path)
            # localizar plugin.py
            candidatos = list(tmp_path.rglob("plugin.py"))
            if not candidatos:
                candidatos = [
                    p for p in tmp_path.rglob("__init__.py")
                    if p.parent != tmp_path and (p.parent / "plugin.json").exists()
                ]
            if not candidatos:
                return {"ok": False, "detail": "ZIP deve conter plugin.py (ou pacote com plugin.json)."}
            entry = candidatos[0]
            origem = entry.parent
            # id: plugin.json ou nome da pasta
            pid = origem.name
            meta_file = origem / "plugin.json"
            if meta_file.is_file():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    if meta.get("id"):
                        pid = str(meta["id"])
                except Exception:
                    pass
            pid = _id_seguro(pid)
            destino = pasta_plugins() / pid
            if destino.exists() and not atualizar:
                return {
                    "ok": False,
                    "ja_existe": True,
                    "detail": f"Plugin '{pid}' já está instalado.",
                    "id": pid,
                }
            if destino.exists():
                shutil.rmtree(destino)
            shutil.copytree(origem, destino)
            definir_habilitado(pid, True)
            log.info("Plugin instalado: %s -> %s (atualizar=%s)", pid, destino, atualizar)
            return {
                "ok": True,
                "id": pid,
                "caminho": str(destino),
                "atualizado": bool(atualizar),
                "detail": "Instalado. Use recarregar para ativar sem reiniciar o servidor.",
            }


def desinstalar(plugin_id: str) -> dict:
    """Remove a pasta do plugin e o estado de habilitação."""
    import shutil
    pid = _id_seguro(plugin_id)
    if not pid:
        return {"ok": False, "detail": "ID inválido."}
    if eh_padrao(pid):
        return {
            "ok": False,
            "detail": (
                f"O plugin '{pid}' é padrão do ArautoPY e não pode ser desinstalado. "
                "Use Desativar se não quiser usá-lo."
            ),
        }
    destino = pasta_plugins() / pid
    if not destino.is_dir():
        return {"ok": False, "detail": f"Plugin '{pid}' não encontrado."}
    try:
        shutil.rmtree(destino)
    except OSError as exc:
        return {"ok": False, "detail": str(exc)}
    with _lock:
        _ler_estado()
        _estado.pop(pid, None)
        _gravar_estado()
        _carregados.pop(pid, None)
    log.info("Plugin desinstalado: %s", pid)
    return {
        "ok": True,
        "id": pid,
        "detail": "Removido. Reinicie o servidor se o plugin estava carregado.",
    }


def caminho_exemplo_zip() -> Path | None:
    """ZIP com todos os plugins de exemplo (hello, mídia TC-506, explorador BD).

    Gerado sob demanda a partir de ``arauto/plugins/exemplos/``.
    """
    import zipfile

    exemplos = Path(__file__).resolve().parent / "exemplos"
    if not exemplos.is_dir():
        return None
    pastas = sorted(
        p for p in exemplos.iterdir()
        if p.is_dir() and (p / "plugin.py").is_file()
    )
    if not pastas:
        return None

    out = pasta_plugins().parent / "plugins-exemplos.zip"
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for pasta in pastas:
                for f in pasta.rglob("*"):
                    if not f.is_file():
                        continue
                    if "__pycache__" in f.parts or f.suffix == ".pyc":
                        continue
                    arc = (Path(pasta.name) / f.relative_to(pasta)).as_posix()
                    zf.write(f, arc)
        return out
    except Exception:
        log.debug("Falha ao gerar zip de exemplos", exc_info=True)
        return None


def _remover_rotas_plugin(app, plugin_id: str) -> int:
    """Remove rotas cujo path começa com /plugins/<id> ou marcadas pelo plugin."""
    if app is None:
        return 0
    prefixos = (
        f"/plugins/{plugin_id}",
        f"/plugins/{plugin_id.replace('_', '-')}",
    )
    # também abas registradas
    info = _carregados.get(plugin_id)
    if info:
        for aba in info.abas:
            href = (aba.href or "").split("?")[0].rstrip("/")
            if href:
                prefixos = prefixos + (href,)
    rotas = getattr(app.router, "routes", None)
    if not rotas:
        return 0
    manter = []
    removidas = 0
    for r in list(rotas):
        path = getattr(r, "path", None) or ""
        some = any(path == p or path.startswith(p + "/") or path.startswith(p + "{") for p in prefixos if p)
        # prefix match for path like /plugins/midia-tc506/...
        if not some:
            for p in prefixos:
                if p and (path.startswith(p) or path == p):
                    some = True
                    break
        if some:
            removidas += 1
        else:
            manter.append(r)
    app.router.routes = manter
    return removidas


def _descarregar_modulo(plugin_id: str) -> None:
    nomes = [k for k in list(sys.modules) if k == f"arauto_plugin_{plugin_id}" or k.startswith(f"arauto_plugin_{plugin_id}.")]
    for n in nomes:
        sys.modules.pop(n, None)
    _modulos_por_plugin.pop(plugin_id, None)


def recarregar_plugins() -> dict:
    """Recarrega todos os plugins habilitados sem reiniciar o processo.

    Remove rotas antigas dos plugins e executa ``setup`` de novo.
    """
    global _hooks_query
    app = _app_ref
    service = _service_ref
    if app is None or service is None:
        return {"ok": False, "detail": "App ainda não inicializou plugins."}

    with _lock:
        # limpa abas/hooks; remove rotas conhecidas
        for pid in list(_carregados.keys()):
            _remover_rotas_plugin(app, pid)
            _descarregar_modulo(pid)
        _carregados.clear()
        _hooks_query = []
        resultados = carregar_todos(app, service)
        return {
            "ok": True,
            "plugins": len(resultados),
            "ativos": sum(1 for p in resultados if p.habilitado and not p.erro),
            "detail": "Plugins recarregados.",
            "lista": [{"id": p.id, "habilitado": p.habilitado, "erro": p.erro} for p in resultados],
        }


def recarregar_plugin(plugin_id: str) -> dict:
    """Recarrega um único plugin (após instalar/atualizar/ativar)."""
    app = _app_ref
    service = _service_ref
    if app is None or service is None:
        return {"ok": False, "detail": "App ainda não inicializou plugins."}
    pid = (plugin_id or "").strip()
    if not pid:
        return {"ok": False, "detail": "ID inválido."}

    with _lock:
        _remover_rotas_plugin(app, pid)
        _descarregar_modulo(pid)
        _carregados.pop(pid, None)
        # remove hooks — simplifica recarregando todos se hooks existirem
        # (hooks não são por plugin; recarrega completo se houver hooks)
        if _hooks_query:
            return recarregar_plugins()

        pasta = pasta_plugins() / pid
        if not pasta.is_dir() or not esta_habilitado(pid):
            return {"ok": True, "id": pid, "detail": "Plugin descarregado.", "habilitado": False}

        # carrega só este
        meta = {"id": pid, "nome": pid, "versao": "0.1.0", "descricao": "", "autor": ""}
        meta_file = pasta / "plugin.json"
        if meta_file.is_file():
            try:
                meta.update(json.loads(meta_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        info = PluginInfo(
            id=str(meta.get("id") or pid),
            nome=str(meta.get("nome") or pid),
            versao=str(meta.get("versao") or "0.1.0"),
            descricao=str(meta.get("descricao") or ""),
            autor=str(meta.get("autor") or ""),
            caminho=str(pasta),
            habilitado=True,
        )
        try:
            mod = _carregar_modulo(pasta)
            ctx = PluginContext(app, service, info.id)
            if hasattr(mod, "setup") and callable(mod.setup):
                mod.setup(ctx)
            elif hasattr(mod, "Plugin"):
                inst = mod.Plugin()
                inst.setup(ctx)
            else:
                raise RuntimeError("plugin.py precisa definir setup(ctx)")
            info.abas = list(ctx._abas)
            _hooks_query.extend(ctx._hooks_query)
            _carregados[info.id] = info
            log.info("Plugin recarregado: %s", info.id)
            return {"ok": True, "id": info.id, "detail": "Plugin recarregado.", "habilitado": True}
        except Exception as exc:
            log.exception("Falha ao recarregar %s", pid)
            info.erro = str(exc)
            info.habilitado = False
            _carregados[info.id] = info
            return {"ok": False, "id": pid, "detail": str(exc)}


def documentacao_path() -> Path:
    # docs/ no root do projeto
    candidatos = [
        resource_root().parent / "docs" / "plugins.md",
        Path(__file__).resolve().parents[2] / "docs" / "plugins.md",
        APP_DIR / "docs" / "plugins.md",
    ]
    for c in candidatos:
        if c.is_file():
            return c
    return candidatos[0]



"""Inicialização automática com o sistema operacional.

Windows
  1) Atalho/script em %%APPDATA%%\\...\\Startup  (mais confiável)
  2) HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
  3) Fallback: comando ``reg add`` se winreg falhar

Linux → ~/.config/autostart/arautopy.desktop (XDG)
Docker → não aplicável (restart policy do container)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("arauto.autostart")

APP_NAME = "ArautoPY"
REG_VALUE = "ArautoPY"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_PATH_FULL = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
DESKTOP_NAME = "arautopy.desktop"
CHAVE_SETTINGS = "AUTOSTART_ENABLED"
STARTUP_CMD_NAME = "ArautoPY.cmd"


def _em_docker() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore")
        if "docker" in cgroup or "containerd" in cgroup or "/lxc/" in cgroup:
            return True
    except OSError:
        pass
    return bool(os.environ.get("ARAUTO_DOCKER") or os.environ.get("container"))


def plataforma() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    return sys.platform


def suporte() -> dict:
    plat = plataforma()
    docker = _em_docker()
    if docker:
        return {
            "disponivel": False,
            "plataforma": plat,
            "docker": True,
            "metodo": "",
            "motivo": (
                "Em Docker a inicialização fica a cargo do container "
                "(restart: unless-stopped / always), não do SO host."
            ),
        }
    if plat == "windows":
        return {
            "disponivel": True,
            "plataforma": "windows",
            "docker": False,
            "metodo": "startup+registro",
            "motivo": (
                "Grava um script na pasta Inicializar do Windows e a chave "
                "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. "
                "Não precisa de administrador."
            ),
        }
    if plat == "linux":
        return {
            "disponivel": True,
            "plataforma": "linux",
            "docker": False,
            "metodo": "xdg",
            "motivo": "Arquivo ~/.config/autostart/arautopy.desktop (sessão gráfica).",
        }
    return {
        "disponivel": False,
        "plataforma": plat,
        "docker": False,
        "metodo": "",
        "motivo": f"Sistema operacional não suportado para autostart ({plat}).",
    }


def _app_dir() -> Path:
    from .settings import APP_DIR
    APP_DIR.mkdir(parents=True, exist_ok=True)
    return APP_DIR


def caminho_run() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    aqui = Path(__file__).resolve()
    candidatos = [
        aqui.parents[2] / "run.py",
        Path.cwd() / "run.py",
    ]
    for c in candidatos:
        if c.is_file():
            return c.resolve()
    return candidatos[0]


def _python_exe() -> Path:
    exe = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return exe
    if sys.platform.startswith("win"):
        w = exe.with_name("pythonw.exe")
        if w.is_file():
            return w
    return exe


def comando_inicio() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    return f'"{_python_exe()}" "{caminho_run()}"'


def _workdir() -> Path:
    return caminho_run().parent


def _startup_folder() -> Path:
    """Pasta 'Inicializar' do usuário atual (shell:startup)."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def _startup_cmd_path() -> Path:
    return _startup_folder() / STARTUP_CMD_NAME


def _cmd_dados_path() -> Path:
    """Cópia de apoio em ~/.arautopy (não depende da pasta Startup)."""
    return _app_dir() / "autostart.cmd"


def _conteudo_cmd() -> str:
    """Script de logon: sobe o servidor com --tray (ícone + notificação)."""
    wd = _workdir()
    py = _python_exe()
    script = caminho_run()
    if getattr(sys, "frozen", False):
        return (
            "@echo off\r\n"
            f'cd /d "{wd}"\r\n'
            f'start "" "{script}" --tray\r\n'
        )
    return (
        "@echo off\r\n"
        f'cd /d "{wd}"\r\n'
        f'start "" "{py}" "{script}" --tray\r\n'
    )


def _escrever_cmd(destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(_conteudo_cmd(), encoding="utf-8")
    return destino.resolve()


def _reg_abrir(escrita: bool = False):
    """Abre HKCU\\...\\Run sem flags WOW64 (desnecessárias e problemáticas no HKCU)."""
    import winreg

    # KEY_WRITE = SET_VALUE + CREATE_SUB_KEY + STANDARD_RIGHTS_WRITE
    acesso = winreg.KEY_READ | winreg.KEY_WRITE if escrita else winreg.KEY_READ
    if escrita:
        return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, acesso)
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, acesso)


def _reg_ler() -> str | None:
    try:
        import winreg

        with _reg_abrir(False) as key:
            valor, _tipo = winreg.QueryValueEx(key, REG_VALUE)
        texto = str(valor or "").strip()
        return texto or None
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.debug("reg ler: %s", exc)
        return None
    except Exception as exc:
        log.debug("reg ler (outro): %s", exc)
        return None


def _reg_gravar_winreg(comando: str) -> None:
    import winreg

    with _reg_abrir(True) as key:
        winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, comando)
        try:
            winreg.FlushKey(key)
        except OSError:
            pass


def _reg_gravar_reg_exe(comando: str) -> None:
    """Fallback: utilitário reg.exe do Windows (mesma hive do usuário)."""
    # /d recebe o valor; aspas no valor são necessárias se houver espaços
    valor = comando if comando.startswith('"') else f'"{comando}"'
    flags = 0
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        [
            "reg",
            "add",
            REG_PATH_FULL,
            "/v",
            REG_VALUE,
            "/t",
            "REG_SZ",
            "/d",
            valor,
            "/f",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=flags,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"código {proc.returncode}"
        raise OSError(f"reg add falhou: {err}")


def _reg_gravar(comando: str) -> str:
    """Tenta winreg e, se falhar, reg.exe. Devolve o método que funcionou."""
    erros: list[str] = []
    try:
        _reg_gravar_winreg(comando)
        lido = _reg_ler()
        if lido:
            return "winreg"
        erros.append("winreg gravou mas a leitura voltou vazia")
    except Exception as exc:
        erros.append(f"winreg: {exc}")
        log.warning("winreg falhou ao gravar Run: %s", exc)

    try:
        _reg_gravar_reg_exe(comando)
        lido = _reg_ler()
        if lido:
            return "reg.exe"
        # reg.exe pode ter gravado mesmo se winreg ler falhar
        return "reg.exe"
    except Exception as exc:
        erros.append(f"reg.exe: {exc}")
        log.warning("reg.exe falhou ao gravar Run: %s", exc)

    raise OSError("Não foi possível gravar no registro. " + " | ".join(erros))


def _reg_apagar() -> None:
    try:
        import winreg

        with _reg_abrir(True) as key:
            try:
                winreg.DeleteValue(key, REG_VALUE)
            except FileNotFoundError:
                pass
            except OSError:
                pass
    except Exception as exc:
        log.debug("winreg delete: %s", exc)

    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
        subprocess.run(
            ["reg", "delete", REG_PATH_FULL, "/v", REG_VALUE, "/f"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=flags,
        )
    except Exception as exc:
        log.debug("reg delete: %s", exc)


def _desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / DESKTOP_NAME


def _persistir_settings(ativo: bool) -> None:
    try:
        from .settings import get_settings

        get_settings().set(CHAVE_SETTINGS, "true" if ativo else "false")
    except Exception:
        log.debug("Não foi possível gravar %s nas settings", CHAVE_SETTINGS, exc_info=True)


def status() -> dict:
    info = suporte()
    ativo = False
    detalhe = ""
    erro = ""
    metodos: list[str] = []
    if info["disponivel"]:
        try:
            if info["plataforma"] == "windows":
                valor = _reg_ler()
                startup = _startup_cmd_path()
                if valor:
                    ativo = True
                    detalhe = valor
                    metodos.append("registro")
                if startup.is_file():
                    ativo = True
                    metodos.append("startup")
                    if not detalhe:
                        detalhe = str(startup)
                if not detalhe:
                    apoio = _cmd_dados_path()
                    if apoio.is_file():
                        detalhe = str(apoio)
            elif info["plataforma"] == "linux":
                p = _desktop_path()
                if p.is_file():
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    ativo = (
                        "Hidden=true" not in txt
                        and "X-GNOME-Autostart-enabled=false" not in txt
                    )
                    detalhe = str(p)
                    if ativo:
                        metodos.append("xdg")
        except Exception as exc:
            erro = str(exc)
            log.exception("Falha ao ler status de autostart")
    if erro:
        info = {**info, "erro": erro}
    return {
        **info,
        "ativo": ativo,
        "comando": comando_inicio(),
        "detalhe": detalhe,
        "metodos_ativos": metodos,
    }


def habilitar() -> dict:
    info = suporte()
    if not info["disponivel"]:
        return {"ok": False, "detail": info.get("motivo") or "Autostart indisponível."}
    try:
        if info["plataforma"] == "windows":
            feitos: list[str] = []
            falhas: list[str] = []

            # 1) Script de dados (sempre)
            apoio = _escrever_cmd(_cmd_dados_path())
            feitos.append(f"script {apoio}")

            # 2) Pasta Inicializar (mais confiável que só o registro)
            try:
                startup = _escrever_cmd(_startup_cmd_path())
                feitos.append(f"Startup {startup}")
            except Exception as exc:
                falhas.append(f"Startup: {exc}")
                log.warning("Falha ao gravar pasta Startup: %s", exc)
                startup = apoio

            # 3) Registro Run — aponta para o .cmd (Startup se existir, senão apoio)
            alvo_reg = str(startup if startup.is_file() else apoio)
            comando_reg = f'"{alvo_reg}"'
            try:
                metodo = _reg_gravar(comando_reg)
                feitos.append(f"registro via {metodo}")
            except Exception as exc:
                falhas.append(f"registro: {exc}")
                log.warning("Falha ao gravar registro Run: %s", exc)

            if not any("Startup" in f or "registro" in f for f in feitos):
                return {
                    "ok": False,
                    "ativo": False,
                    "detail": (
                        "Não foi possível registrar a inicialização. "
                        + " | ".join(falhas)
                    ),
                    "falhas": falhas,
                }

            _persistir_settings(True)
            log.info("Autostart Windows: %s", " · ".join(feitos))
            msg = "Inicialização ativada: " + " · ".join(feitos)
            if falhas:
                msg += " (avisos: " + " | ".join(falhas) + ")"
            return {
                "ok": True,
                "ativo": True,
                "detail": msg,
                "comando": comando_reg,
                "script": str(apoio),
                "startup": str(startup) if startup.is_file() else "",
                "feitos": feitos,
                "falhas": falhas,
            }

        if info["plataforma"] == "linux":
            p = _desktop_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            if getattr(sys, "frozen", False):
                exec_cmd = str(Path(sys.executable).resolve())
            else:
                exec_cmd = f"{_python_exe()} {caminho_run()}"
            p.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                "Comment=Servidor de integração ArautoPY\n"
                f"Exec={exec_cmd}\n"
                f"Path={_workdir()}\n"
                "X-GNOME-Autostart-enabled=true\n"
                "Hidden=false\n"
                "Terminal=false\n"
                "Categories=Utility;\n",
                encoding="utf-8",
            )
            try:
                p.chmod(0o644)
            except OSError:
                pass
            _persistir_settings(True)
            return {"ok": True, "ativo": True, "detail": f"Criado {p}", "comando": exec_cmd}
    except Exception as exc:
        log.exception("Falha ao habilitar autostart")
        return {"ok": False, "detail": f"Não foi possível registrar a inicialização: {exc}"}
    return {"ok": False, "detail": "Plataforma não implementada."}


def desabilitar() -> dict:
    info = suporte()
    if not info["disponivel"]:
        return {"ok": False, "detail": info.get("motivo") or "Autostart indisponível."}
    try:
        if info["plataforma"] == "windows":
            _reg_apagar()
            for caminho in (_startup_cmd_path(), _cmd_dados_path()):
                if caminho.is_file():
                    try:
                        caminho.unlink()
                    except OSError as exc:
                        log.debug("unlink %s: %s", caminho, exc)
            _persistir_settings(False)
            return {
                "ok": True,
                "ativo": False,
                "detail": "Removido da inicialização (registro + pasta Startup).",
            }
        if info["plataforma"] == "linux":
            p = _desktop_path()
            if p.is_file():
                p.unlink()
            _persistir_settings(False)
            return {"ok": True, "ativo": False, "detail": "Arquivo de autostart removido."}
    except Exception as exc:
        log.exception("Falha ao desabilitar autostart")
        return {"ok": False, "detail": str(exc)}
    return {"ok": False, "detail": "Plataforma não implementada."}


def aplicar_se_configurado() -> None:
    """Na subida: se a config pede autostart, tenta regravar."""
    if not suporte().get("disponivel"):
        return
    try:
        from .settings import get_settings

        if not get_settings().get_bool(CHAVE_SETTINGS, False):
            return
        st = status()
        if st.get("ativo"):
            return
        r = habilitar()
        if r.get("ok"):
            log.info("Autostart reaplicado na inicialização")
        else:
            log.warning("Autostart configurado, mas falhou ao reaplicar: %s", r.get("detail"))
    except Exception:
        log.debug("aplicar_se_configurado ignorado", exc_info=True)



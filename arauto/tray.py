"""Ícone na bandeja do sistema (Windows: .exe ou ``python run.py --tray``).

Depende de ``pystray`` e ``Pillow``. Se não estiverem instalados, o servidor
continua rodando sem a bandeja.
"""

from __future__ import annotations

import logging
import webbrowser
from typing import Callable

log = logging.getLogger("arauto.tray")


def _icone_pil():
    """Gera um ícone 64×64 sem arquivo externo (âmbar sobre fundo escuro)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 61, 61), radius=14, fill=(11, 18, 32, 255))
    d.rounded_rectangle((10, 10, 53, 53), radius=10, fill=(255, 201, 60, 255))
    x = 16
    for w in (3, 2, 4, 2, 3, 5, 2, 3, 2, 4):
        d.rectangle((x, 20, x + w - 1, 44), fill=(11, 18, 32, 255))
        x += w + 1
    return img


def _notificar_windows(titulo: str, mensagem: str) -> None:
    """Toast do Windows 10/11 via PowerShell (sem dependência extra)."""
    import subprocess

    # Escapa aspas simples para o literal PowerShell
    def esc(s: str) -> str:
        return s.replace("'", "''")

    ps = f"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>{esc(titulo)}</text>
      <text>{esc(mensagem)}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("ArautoPY").Show($toast)
"""
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        log.debug("Toast PowerShell indisponível", exc_info=True)


def run_tray(
    *,
    porta_web: int = 6689,
    host: str = "127.0.0.1",
    on_quit: Callable[[], None] | None = None,
    notificar: bool = True,
    origem_logon: bool = False,
) -> None:
    """Bloqueia até o usuário escolher Sair no menu da bandeja."""
    try:
        import pystray
        from pystray import MenuItem as Item
    except ImportError:
        log.warning("pystray não instalado — bandeja indisponível")
        return

    alvo = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    base = f"http://{alvo}:{porta_web}"

    def abrir(path: str = "/") -> None:
        try:
            webbrowser.open(base + path)
        except Exception:
            log.exception("Não foi possível abrir o navegador")

    def sair(icon, _item) -> None:  # noqa: ANN001
        icon.stop()
        if on_quit:
            on_quit()

    menu = pystray.Menu(
        Item("Abrir terminal de consulta", lambda: abrir("/")),
        Item("Abrir painel", lambda: abrir("/painel")),
        Item("Configuração", lambda: abrir("/config")),
        Item("Logs", lambda: abrir("/logs")),
        pystray.Menu.SEPARATOR,
        Item("Sair", sair),
    )

    icon = pystray.Icon(
        "ArautoPY",
        _icone_pil(),
        f"ArautoPY — :{porta_web}",
        menu,
    )

    def on_activate(icon) -> None:  # noqa: ANN001, ARG001
        abrir("/painel")

    try:
        icon.default_action = on_activate
    except Exception:
        pass

    def ao_mostrar(icon) -> None:  # noqa: ANN001
        icon.visible = True
        if notificar:
            titulo = "ArautoPY"
            if origem_logon:
                msg = f"Iniciado com o Windows · painel :{porta_web}"
            else:
                msg = f"ArautoPY em execução na bandeja · painel :{porta_web}"
            # Preferência: API nativa do pystray; fallback: toast Win10
            try:
                icon.notify(msg, titulo)
            except Exception:
                _notificar_windows(titulo, msg)
            log.info("Notificação de bandeja enviada")

    log.info("Ícone na bandeja ativo (%s)", base)
    icon.run(setup=ao_mostrar)



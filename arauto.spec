# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller — gera ArautoPY.exe sem janela de console.

Uso (no Windows, com o venv ativo):
    pip install pyinstaller pillow
    pyinstaller arauto.spec

O executável sai em dist/ArautoPY.exe
Dados (config, sqlite, logs) ficam em %USERPROFILE%\\.arauto\\
"""

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

datas = [
    (str(root / "arauto" / "web" / "templates"), "arauto/web/templates"),
    (str(root / "arauto" / "web" / "static"), "arauto/web/static"),
]

a = Analysis(
    ["run.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "PIL",
        "PIL.Image",
        "pystray",
        "pystray._win32",
        "arauto.tray",
        "arauto.build_flags",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ArautoPY",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # sem prompt de comando
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)



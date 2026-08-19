"""Flags gravadas pelo build_exe.bat no momento da compilação.

Não edite à mão se for recompilar — o script de build sobrescreve este arquivo.
Em desenvolvimento (python run.py) estes valores são ignorados para a bandeja
(só o .exe usa bandeja), mas a notificação pode ser ligada via config.
"""

# Mostrar ícone na bandeja do Windows (só surte efeito no .exe)
TRAY_ENABLED = True

# Disparar notificação do Windows ao iniciar ("está na bandeja")
TRAY_NOTIFY = True

# True = .exe com janela de console; False = sem prompt
# (o PyInstaller também precisa de console=True/False no .spec — o bat cuida disso)
CONSOLE = False



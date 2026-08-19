@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title ArautoPY - Compilador
color 0E

echo.
echo  ============================================================
echo   ArautoPY - Servidor de integracao
echo  ============================================================
echo.
echo   Pasta: %CD%
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo  [ERRO] Python nao encontrado no PATH.
  echo  Instale o Python e marque "Add Python to PATH".
  echo.
  goto :fim_erro
)

set "OPT_CONSOLE=N"
set "OPT_TRAY=S"
set "OPT_NOTIFY=S"

echo  [1/3] Janela de prompt (console)
echo        S = mostra o CMD com logs (util para depurar)
echo        N = sem janela (recomendado em loja)
echo.
set /p "OPT_CONSOLE=        Mostrar prompt de comando? [S/N] (padrao N): "
if "!OPT_CONSOLE!"=="" set "OPT_CONSOLE=N"
if /i not "!OPT_CONSOLE!"=="S" if /i not "!OPT_CONSOLE!"=="N" set "OPT_CONSOLE=N"

echo.
echo  [2/3] Icone na bandeja do sistema
echo        S = icone perto do relogio (recomendado)
echo        N = sem icone
echo.
set /p "OPT_TRAY=        Mostrar icone na bandeja? [S/N] (padrao S): "
if "!OPT_TRAY!"=="" set "OPT_TRAY=S"
if /i not "!OPT_TRAY!"=="S" if /i not "!OPT_TRAY!"=="N" set "OPT_TRAY=S"

echo.
echo  [3/3] Notificacao ao iniciar
echo        S = avisa que o programa esta na bandeja
echo        N = inicia em silencio
echo.
set /p "OPT_NOTIFY=        Disparar notificacao ao iniciar? [S/N] (padrao S): "
if "!OPT_NOTIFY!"=="" set "OPT_NOTIFY=S"
if /i not "!OPT_NOTIFY!"=="S" if /i not "!OPT_NOTIFY!"=="N" set "OPT_NOTIFY=S"

if /i "!OPT_TRAY!"=="N" set "OPT_NOTIFY=N"

echo.
echo  ------------------------------------------------------------
echo   Resumo
echo  ------------------------------------------------------------
if /i "!OPT_CONSOLE!"=="S" (echo   Prompt de comando : SIM) else (echo   Prompt de comando : NAO)
if /i "!OPT_TRAY!"=="S"    (echo   Icone na bandeja  : SIM) else (echo   Icone na bandeja  : NAO)
if /i "!OPT_NOTIFY!"=="S"  (echo   Notificacao       : SIM) else (echo   Notificacao       : NAO)
echo  ------------------------------------------------------------
echo.
set /p "CONFIRMA=  Confirmar e compilar? [S/N] (padrao S): "
if "!CONFIRMA!"=="" set "CONFIRMA=S"
if /i not "!CONFIRMA!"=="S" (
  echo.
  echo  Cancelado pelo usuario.
  echo.
  goto :fim_ok
)

set "PY_CONSOLE=False"
set "PY_TRAY=True"
set "PY_NOTIFY=True"
if /i "!OPT_CONSOLE!"=="S" set "PY_CONSOLE=True"
if /i "!OPT_TRAY!"=="N"    set "PY_TRAY=False"
if /i "!OPT_NOTIFY!"=="N"  set "PY_NOTIFY=False"

echo.
echo  [ ] Gravando arauto\build_flags.py ...
if not exist "arauto" (
  echo  [ERRO] Pasta arauto nao encontrada. Execute este bat na raiz do projeto.
  goto :fim_erro
)

(
echo """Flags gravadas pelo build_exe.bat."""
echo.
echo TRAY_ENABLED = !PY_TRAY!
echo TRAY_NOTIFY = !PY_NOTIFY!
echo CONSOLE = !PY_CONSOLE!
) > "arauto\build_flags.py"
if errorlevel 1 (
  echo  [ERRO] Nao foi possivel gravar build_flags.py
  goto :fim_erro
)
echo  [OK] build_flags.py

echo  [ ] Ajustando console no arauto.spec ...
set "ARAUTO_CONSOLE=!PY_CONSOLE!"
python -c "from pathlib import Path; import os, re; c=os.environ.get('ARAUTO_CONSOLE','False'); p=Path('arauto.spec'); t=p.read_text(encoding='utf-8'); t2=re.sub(r'console\s*=\s*(True|False)', 'console='+c, t); p.write_text(t2, encoding='utf-8'); print('console='+c)"
if errorlevel 1 (
  echo  [ERRO] Falha ao ajustar arauto.spec
  goto :fim_erro
)
echo  [OK] arauto.spec

echo.
echo  [ ] Instalando dependencias (pode demorar na primeira vez)...
python -m pip install -r requirements.txt pyinstaller pystray
if errorlevel 1 (
  echo  [ERRO] pip install falhou
  goto :fim_erro
)
echo  [OK] dependencias

echo.
echo  [ ] Compilando com PyInstaller (aguarde)...
python -m PyInstaller --noconfirm arauto.spec
if errorlevel 1 (
  echo  [ERRO] PyInstaller falhou
  goto :fim_erro
)

set "EXE_PATH=%CD%\dist\ArautoPY.exe"
if not exist "!EXE_PATH!" (
  echo  [ERRO] Compilacao terminou sem gerar o exe.
  echo  Verifique a pasta dist\
  goto :fim_erro
)

echo.
echo  ============================================================
echo   COMPILACAO CONCLUIDA COM SUCESSO
echo  ------------------------------------------------------------
echo   Executavel:
echo     !EXE_PATH!
echo.
echo   Config/logs:
echo     %USERPROFILE%\.arauto\
echo.
echo   Painel web:
echo     http://127.0.0.1:6689/painel
if /i "!OPT_TRAY!"=="S" echo   Bandeja: icone ativo
if /i "!OPT_NOTIFY!"=="S" echo   Ao iniciar: notificacao Windows
echo  ============================================================
echo.
goto :fim_ok

:fim_erro
echo.
echo  A compilacao nao foi concluida. Veja as mensagens acima.
echo.
pause
endlocal
exit /b 1

:fim_ok
echo  Pressione uma tecla para sair...
pause >nul
endlocal
exit /b 0



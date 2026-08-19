@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

title ArautoPY (venv)
echo.
echo  ========================================
echo   ArautoPY - Servidor de integracao
echo   Ambiente virtual: .venv\
echo  ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao encontrado no PATH.
  echo Instale o Python 3.10+ e marque "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

if not exist "%VENV_PY%" (
  echo Criando ambiente virtual em .venv ...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar o venv.
    pause
    exit /b 1
  )
  echo Venv criado.
) else (
  echo Venv encontrado: .venv\
)

echo Verificando dependencias no venv...
"%VENV_PY%" -c "import fastapi,uvicorn,jinja2,PIL,multipart,sqlalchemy" >nul 2>&1
if errorlevel 1 (
  echo Bibliotecas ausentes no venv. Instalando requirements.txt ...
  echo.
  "%VENV_PY%" -m pip install --upgrade pip
  "%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar dependencias no venv.
    pause
    exit /b 1
  )
  echo.
  echo Dependencias instaladas no venv.
) else (
  echo Dependencias do venv OK.
)

echo.
echo Iniciando: .venv\Scripts\python.exe run.py
echo.
"%VENV_PY%" "%~dp0run.py" %*
set EC=%ERRORLEVEL%
echo.
if not "%EC%"=="0" (
  echo [ERRO] O processo terminou com codigo %EC%.
  pause
)
exit /b %EC%



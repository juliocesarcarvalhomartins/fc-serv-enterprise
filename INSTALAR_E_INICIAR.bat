@echo off
chcp 65001 >nul
setlocal
title FC SERV - Instalação
cd /d "%~dp0"

echo ============================================================
echo                    FC SERV - INSTALACAO
echo ============================================================
echo.

set "PYTHON_EXE="
set "PYTHON_ARGS="

for /f "delims=" %%P in ('where py 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if defined PYTHON_EXE set "PYTHON_ARGS=-3"

if not defined PYTHON_EXE (
  for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if defined PYTHON_EXE (
  "%PYTHON_EXE%" %PYTHON_ARGS% --version >nul 2>nul
  if errorlevel 1 set "PYTHON_EXE="
)

if not defined PYTHON_EXE (
  echo Python nao foi encontrado. Tentando instalar automaticamente...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo.
    echo ERRO: o Windows nao possui o instalador Winget.
    echo Instale o Python 3.12 pelo site python.org e execute novamente.
    pause
    exit /b 1
  )

  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel instalar o Python automaticamente.
    pause
    exit /b 1
  )

  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  if not defined PYTHON_EXE (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
  )
  if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where py 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
    if defined PYTHON_EXE set "PYTHON_ARGS=-3"
  )
)

if not defined PYTHON_EXE (
  echo.
  echo ERRO: o Python foi instalado, mas nao foi localizado.
  echo Reinicie o computador e abra o instalador novamente.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Preparando o ambiente Python pela primeira vez...
  "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
  if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel criar o ambiente Python.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
echo.
echo Instalando os componentes necessarios. Aguarde...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERRO: nao foi possivel instalar os componentes necessarios.
  echo Verifique sua conexao com a internet e tente novamente.
  pause
  exit /b 1
)

echo.
echo Iniciando o FC SERV...
python run.py
if errorlevel 1 (
  echo.
  echo O aplicativo encontrou um erro ao iniciar.
  pause
  exit /b 1
)

echo.
echo O FC SERV foi encerrado. Esta janela pode ser fechada.

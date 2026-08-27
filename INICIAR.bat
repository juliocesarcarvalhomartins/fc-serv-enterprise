@echo off
chcp 65001 >nul
title FC SERV
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo O sistema ainda nao foi instalado nesta maquina.
  echo Iniciando a instalacao...
  call "INSTALAR_E_INICIAR.bat"
  exit /b
)

call ".venv\Scripts\activate.bat"
python run.py
if errorlevel 1 (
  echo.
  echo O aplicativo encontrou um erro ao iniciar.
  pause
)

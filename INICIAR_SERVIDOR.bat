@echo off
chcp 65001 >nul
title FC SERV - Servidor Central
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo O sistema ainda nao foi instalado nesta maquina.
  echo Execute primeiro INSTALAR_E_INICIAR.bat.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python run_server.py
if errorlevel 1 (
  echo.
  echo O servidor encontrou um erro ao iniciar.
  pause
)

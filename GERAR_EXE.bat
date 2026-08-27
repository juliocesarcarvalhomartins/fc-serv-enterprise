@echo off
chcp 65001 >nul
title Gerar EXE - FC SERV
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call INSTALAR_E_INICIAR.bat
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name FC_SERV ^
  --add-data "app\static;app\static" ^
  --collect-all uvicorn --collect-all fastapi --collect-all sqlalchemy --hidden-import win32timezone ^
  run.py
echo.
echo Executável gerado na pasta dist.
pause

@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Gerar Instalador FC SERV v4.0.0

echo ==============================================
echo   FC SERV v4.0.0 - GERADOR DO INSTALADOR EXE
echo ==============================================
echo.

if not exist "dist\FC_SERV_Python_4.0.0.zip" (
  echo ERRO: pacote dist\FC_SERV_Python_4.0.0.zip nao encontrado.
  pause
  exit /b 1
)

where bun >nul 2>nul
if errorlevel 1 (
  echo Bun nao encontrado. Tentando instalar automaticamente...
  where powershell >nul 2>nul || (
    echo ERRO: PowerShell nao encontrado.
    pause
    exit /b 1
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm bun.sh/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.bun\bin;%PATH%"
)

where bun >nul 2>nul
if errorlevel 1 (
  echo.
  echo Nao foi possivel instalar o Bun automaticamente.
  echo Instale o Bun e execute este arquivo novamente.
  pause
  exit /b 1
)

echo.
echo Validando pacote incorporado...
set FATURA_INSTALLER_VALIDATE=1
bun run installer\installer.js
if errorlevel 1 (
  set FATURA_INSTALLER_VALIDATE=
  echo ERRO: falha na validacao do pacote.
  pause
  exit /b 1
)
set FATURA_INSTALLER_VALIDATE=

echo.
echo Gerando executavel unico...
bun build installer\installer.js --compile --target=bun-windows-x64 --outfile "Instalar_FC_SERV_v4.0.0.exe"
if errorlevel 1 (
  echo ERRO ao gerar o instalador.
  pause
  exit /b 1
)

if exist "app\static\fc-serv-logo.ico" (
  if exist "installer\patch_windows_icon.py" (
    python installer\patch_windows_icon.py "Instalar_FC_SERV_v4.0.0.exe" "app\static\fc-serv-logo.ico" >nul 2>nul
  )
)

echo.
echo ==============================================
echo Instalador criado com sucesso:
echo %CD%\Instalar_FC_SERV_v4.0.0.exe
echo ==============================================
pause
endlocal

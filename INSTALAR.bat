@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Instalando o Analise de Video (modo desenvolvimento) ===
rem Cache do pip e temporarios ficam dentro desta pasta (nada no C:)
set "PIP_CACHE_DIR=%~dp0.cache\pip"
set "TEMP=%~dp0temp"
set "TMP=%~dp0temp"
if not exist "temp" mkdir "temp"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python nao encontrado. Instale em https://www.python.org/downloads/
  echo e marque a opcao "Add Python to PATH" na instalacao.
  pause
  exit /b 1
)
if not exist ".venv" (
  echo Criando ambiente virtual...
  python -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo === Pronto! Agora e so abrir o ABRIR.bat ===
pause

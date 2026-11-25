@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Tudo que for temporario/cache fica dentro desta pasta (nada no C:)
set "PIP_CACHE_DIR=%~dp0.cache\pip"
set "TEMP=%~dp0temp"
set "TMP=%~dp0temp"
if not exist "temp" mkdir "temp"
if not exist ".venv\Scripts\python.exe" (
  echo Rode o INSTALAR.bat primeiro.
  pause
  exit /b 1
)
echo === Gerando o executavel (demora alguns minutos) ===
".venv\Scripts\python.exe" -m pip install -q pyinstaller
".venv\Scripts\python.exe" build_exe.py
if errorlevel 1 (
  echo.
  echo *** DEU ERRO ao gerar o executavel. Veja as mensagens acima. ***
  pause
  exit /b 1
)
echo.
echo O executavel esta em: dist\AnaliseVideo\AnaliseVideo.exe
echo O zip para subir no GitHub Releases: dist\AnaliseVideo-windows.zip
pause

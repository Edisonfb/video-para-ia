@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Rode o INSTALAR.bat primeiro.
  pause
  exit /b 1
)
rem O proprio programa atualiza o baixador (yt-dlp.exe) ao abrir
start "" ".venv\Scripts\pythonw.exe" app.py

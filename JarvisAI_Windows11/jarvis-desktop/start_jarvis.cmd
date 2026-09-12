@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Jarvis ist noch nicht eingerichtet.
  echo Bitte zuerst setup_windows.ps1 ausfuehren.
  pause
  exit /b 1
)
".venv\Scripts\pythonw.exe" main.py

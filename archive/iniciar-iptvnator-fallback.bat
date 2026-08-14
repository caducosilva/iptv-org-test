@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0iptvnator_companion.py"
endlocal

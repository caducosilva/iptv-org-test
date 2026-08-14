@echo off
title IPTV Cast Companion - Servidor e Logs ao Vivo
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ===============================================================
echo   IPTV Cast Companion - Painel PC Desktop
echo ===============================================================
echo   - Backend API  : http://127.0.0.1:8769
echo   - Front-End UI : http://127.0.0.1:3000
echo ===============================================================
echo   [ CARREGANDO CANAIS E SERVIDOR - LOGS ABAIXO ]
echo ===============================================================
echo.

if exist "logs\iptv_app.lock" del /f /q "logs\iptv_app.lock" >nul 2>&1
if exist "logs\companion.pid" del /f /q "logs\companion.pid" >nul 2>&1

set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "%~dp0iptvnator_companion.py"

echo.
echo ===============================================================
echo   Servidor encerrado. Pressione qualquer tecla para fechar.
echo ===============================================================
pause
endlocal

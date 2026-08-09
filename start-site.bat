@echo off
chcp 65001 >nul 2>&1
title ClinProc Local Preview
cd /d "%~dp0"
echo.
echo  ========================================
echo   ClinProc Papers Index - Local Preview
echo  ========================================
echo.
echo  Starting local server...
echo  Browser will open http://localhost:8080
echo.
echo  Close this window to stop the server.
echo.
start /b python -m http.server 8080 --directory site
timeout /t 2 /nobreak >nul
start http://localhost:8080/
echo  Server started. Press Ctrl+C or close window to stop.
echo.
cmd /k

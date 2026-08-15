@echo off
chcp 65001 >nul 2>&1
title ClinProc Auto Push
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0auto_push.ps1" %*
pause

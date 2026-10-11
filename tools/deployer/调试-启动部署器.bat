@echo off
chcp 65001 >nul
title OC Ferry Deployer - Debug
cd /d "%~dp0"
echo 正在启动 OC Ferry Deployer（开发版）...
echo.
"E:\C\CTools\PythonTools\python\python.exe" deployer.py
echo.
echo [进程已退出] 错误码 %ERRORLEVEL%
pause

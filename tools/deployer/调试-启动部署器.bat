@echo off
chcp 65001 >nul
title OC Ferry Deployer - Debug
cd /d "%~dp0"
echo 正在启动 OC Ferry Deployer（开发版）...
echo.
rem 用 PATH 里的 python；想指定解释器就设 PYTHON 环境变量
if defined PYTHON (
  "%PYTHON%" deployer.py
) else (
  python deployer.py
)
echo.
echo [进程已退出] 错误码 %ERRORLEVEL%
pause

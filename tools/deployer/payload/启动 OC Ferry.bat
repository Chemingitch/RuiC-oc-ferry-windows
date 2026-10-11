@echo off
chcp 936 >nul
setlocal
title OC Ferry

rem ============================================================
rem  OC Ferry 0.3.0 (Windows 绿色便携版)
rem  双击本文件即可启动，启动后常驻系统托盘。
rem ============================================================

set "HERE=%~dp0"
set "FERRY_DATA_DIR=%HERE%data"

rem 清掉父进程可能带入的变量。不清掉的话，主程序在某些环境里
rem 会被当成纯 Node 运行，窗口永远起不来。
set "ELECTRON_RUN_AS_NODE="
set "ELECTRON_NO_ATTACH_CONSOLE="

rem 退出时如何处理 OpenCode 桌面版遗留的 opencode-cli.exe:
rem   orphans (默认) 只清「父进程已退出」的孤儿，不动你正在用的桌面版
rem   always        连正在运行的桌面版一起结束
rem   off           完全不清理
rem set "FERRY_KILL_OPENCODE_CLI=always"

if not exist "%HERE%app\OC Ferry.exe" (
  echo.
  echo   [错误] 找不到 "%HERE%app\OC Ferry.exe"
  echo.
  echo   本程序必须完整解压后使用，不能只复制 exe 文件。
  echo   请确认 app 子文件夹与本文件在同一个目录下。
  echo.
  pause
  exit /b 1
)

echo 正在启动 OC Ferry ...
start "OC Ferry" "%HERE%app\OC Ferry.exe"
exit /b 0

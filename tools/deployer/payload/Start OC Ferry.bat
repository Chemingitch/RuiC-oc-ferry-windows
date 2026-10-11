@echo off
setlocal
title OC Ferry

rem ============================================================
rem  OC Ferry 0.3.0 (Windows portable build)
rem  Double-click to start. The app then lives in the system tray.
rem ============================================================

set "HERE=%~dp0"
set "FERRY_DATA_DIR=%HERE%data"

rem Clear variables that a parent process may have injected.
rem Otherwise the app may run as plain Node and never open a window.
set "ELECTRON_RUN_AS_NODE="
set "ELECTRON_NO_ATTACH_CONSOLE="

if not exist "%HERE%app\OC Ferry.exe" (
  echo.
  echo   [ERROR] Missing "%HERE%app\OC Ferry.exe"
  echo.
  echo   This build must be extracted completely; copying the exe alone
  echo   will not work. Make sure the "app" folder sits next to this file.
  echo.
  pause
  exit /b 1
)

echo Starting OC Ferry ...
start "OC Ferry" "%HERE%app\OC Ferry.exe"
exit /b 0

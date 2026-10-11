# -*- coding: utf-8 -*-
"""生成发布载荷里的「附加文件」——启动脚本与快速开始文档。

为什么单独生成而不是直接复制现成文件：
  1. 现成的 .bat 是 UTF-8 + BOM + LF 换行。cmd.exe 对 BOM 会在首行塞进
     ﻿ 字符导致 ``@echo off`` 失效，对 LF 换行的括号块/标签解析也不可靠。
     Windows 批处理的稳妥写法是 **GBK(cp936) + CRLF**。
  2. 现成的文档里带本机绝对路径与用户名（E:\\C\\CTools\\... 、Chemingitch），
     不能直接对外分发。

输出目录: <fork_repo>/tools/deployer/payload/
"""
import os
import sys

BAT_START = r"""@echo off
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
"""

BAT_START_EN = r"""@echo off
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
"""

README = r"""OC Ferry 0.3.0 - Windows 绿色便携版
================================================

【怎么用】
双击本目录下的  启动 OC Ferry.bat

【为什么必须用 .bat 启动，不能直接双击 app\OC Ferry.exe】
启动脚本会做两件必要的事：
  1. 把数据目录固定成 ./data —— 绿色便携，整个文件夹可整体搬迁，
     不想要了直接删文件夹就是干净卸载。
  2. 清除父进程可能带入的 ELECTRON_RUN_AS_NODE 变量。
     不清掉的话，主程序在某些环境里会被当成纯 Node 运行，窗口起不来。

【目录结构】
  app\                 主程序（Electron，约 373 MB）
  data\                运行时数据，首次启动自动生成
  启动 OC Ferry.bat    启动入口
  快速开始.txt          本文件

【首次使用】
  1. 启动后程序常驻系统托盘，右键托盘图标可退出。
  2. 它会自动准备一份「隔离的」OpenCode 运行时（首次需要联网下载），
     并在本机开一个 OpenAI 兼容的转发口。
  3. 在 WorkBuddy 里导入 models.json，就能看到名字形如
     「OC · 模型名」的条目，选中即可使用。

【运行要求】
  - Windows 10 / 11 (x64)
  - 首次启动需要联网（下载 OpenCode 运行时）
  - 界面依赖系统自带的 WebView2 运行时（Win11 及新版 Win10 已内置）

【常见问题】
  Q: 双击 .bat 后一闪而过没有窗口？
  A: 说明 app\OC Ferry.exe 不完整。请重新完整解压压缩包，
     不要只把 exe 单独复制出来。

  Q: 杀掉进程后托盘图标残留？
  A: 右键托盘图标选「退出 OC Ferry」，让它走正常退出流程。

【来源与许可】
  上游项目: https://github.com/HRuiCcc/RuiC-oc-ferry   (MIT)
  本 Windows 构建: https://github.com/Chemingitch/RuiC-oc-ferry-windows
  本包基于上游 v0.3.0 构建，并合入本 fork 的 Windows 改动：
  托盘常驻、退出清理、便携数据目录。
"""

README_EN = r"""OC Ferry 0.3.0 - Windows portable build
================================================

HOW TO START
  Double-click   Start OC Ferry.bat

WHY THE .bat AND NOT app\OC Ferry.exe DIRECTLY
  The launcher does two required things:
    1. Pins the data directory to .\data, so the whole folder is
       portable and uninstalling is just deleting the folder.
    2. Clears ELECTRON_RUN_AS_NODE, which a parent process may have
       injected. Without this the app can run as plain Node and
       never open a window.

LAYOUT
  app\                 main program (Electron, ~373 MB)
  data\                runtime data, created on first launch
  Start OC Ferry.bat   launcher
  README.txt           this file

FIRST RUN
  1. The app lives in the system tray; right-click the tray icon to quit.
  2. It prepares an isolated OpenCode runtime (needs network on first run)
     and opens a local OpenAI-compatible endpoint.
  3. Import models.json in WorkBuddy to see entries named "OC - <model>".

REQUIREMENTS
  - Windows 10 / 11 (x64)
  - Network access on first launch
  - WebView2 runtime (built into Windows 11 and recent Windows 10)

SOURCE & LICENSE
  Upstream: https://github.com/HRuiCcc/RuiC-oc-ferry   (MIT)
  This build: https://github.com/Chemingitch/RuiC-oc-ferry-windows
  Based on upstream v0.3.0 plus this fork's Windows changes.
"""

FILES = {
    "启动 OC Ferry.bat": (BAT_START, "gbk"),
    "Start OC Ferry.bat": (BAT_START_EN, "ascii"),
    "快速开始.txt": (README, "gbk"),
    "README.txt": (README_EN, "ascii"),
}


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        r"E:\C\CTools\AI Make\oc-ferry-fork", "tools", "deployer", "payload")
    os.makedirs(out, exist_ok=True)
    print(f"输出目录: {out}")
    for name, (text, enc) in FILES.items():
        # 统一 CRLF：Windows 文本文件的标准换行
        data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode(enc)
        p = os.path.join(out, name)
        with open(p, "wb") as f:
            f.write(data)
        print(f"  {name:24s} {len(data):6d}B  ({enc}, CRLF)")
    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

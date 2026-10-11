# -*- coding: utf-8 -*-
"""把 OC Ferry Deployer 打包为单文件、无控制台的 exe。"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent

# 用「当前正在跑本脚本的解释器」来打包，避免硬编码绝对路径。
# 前提：这个解释器里装好了 pyinstaller（pip install pyinstaller）。
# 想换解释器也可以：PYTHON=/path/to/python.exe python build.py
PYEXE = os.environ.get("PYTHON") or sys.executable

NAME = "OC-Ferry-Deployer"


def main() -> int:
    ui = HERE / "ui"
    icon = HERE / "app.ico"
    if not ui.is_dir():
        print("缺少 ui/ 目录", file=sys.stderr)
        return 1
    if not icon.is_file():
        print("缺少 app.ico，请先运行 gen_icon.py", file=sys.stderr)
        return 1

    args = [
        str(PYEXE), "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",                      # 单文件分发
        "--noconsole",                    # GUI 子系统：不创建控制台
        "--name", NAME,
        "--icon", str(icon),              # 任务栏 / 资源管理器图标
        "--add-data", f"{ui}{os.pathsep}ui",
        "--collect-all", "webview",       # pywebview 的运行时资源
        "--collect-all", "clr_loader",
        "--hidden-import", "pythonnet",
        "--distpath", str(HERE / "dist"),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE),
        str(HERE / "deployer.py"),
    ]
    print("$ " + " ".join(args))
    return subprocess.run(args, cwd=str(HERE)).returncode


if __name__ == "__main__":
    raise SystemExit(main())

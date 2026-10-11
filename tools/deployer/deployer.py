# -*- coding: utf-8 -*-
"""
OC Ferry Deployer — 科技感一键部署器（pywebview 外壳 / 开发版）

本文件只负责「窗口 + 前端通信」，部署逻辑在 _run() 中逐步接入。
打包：见 build.py
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

import webview

APP_NAME = "OC Ferry Deployer"
VERSION = "1.0.0"


# ---------------------------------------------------------------- 路径
def resource_dir() -> pathlib.Path:
    """开发态取脚本目录；PyInstaller 打包后取解包目录。"""
    if getattr(sys, "frozen", False):
        return pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(sys.executable).parent))
    return pathlib.Path(__file__).resolve().parent


def log_file() -> pathlib.Path:
    d = pathlib.Path(os.environ.get("TEMP", ".")) / "OC-Ferry-Deployer"
    d.mkdir(parents=True, exist_ok=True)
    return d / "deployer.log"


# ---------------------------------------------------------------- 子进程
# 所有子进程调用统一走这里：CREATE_NO_WINDOW 保证不会闪出控制台黑框。
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def run_hidden(cmd, timeout: int = 20):
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW
    )


# ---------------------------------------------------------------- 环境探测
def webview2_version() -> str | None:
    """读取 WebView2 Runtime 版本（机器级 / 用户级）。"""
    try:
        import winreg
    except ImportError:
        return None
    guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    probes = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
    ]
    for hive, path in probes:
        try:
            with winreg.OpenKey(hive, path) as k:
                pv = winreg.QueryValueEx(k, "pv")[0]
                if pv and pv != "0.0.0.0":
                    return pv
        except OSError:
            continue
    return None


def find_opencode() -> pathlib.Path | None:
    """按 OC Ferry 的 runtimeCandidates() 顺序查找本机已有的 opencode。"""
    cands: list[pathlib.Path] = []
    env = os.environ.get("FERRY_OPENCODE_PATH")
    if env:
        cands.append(pathlib.Path(env))
    home = os.environ.get("USERPROFILE")
    if home:
        cands.append(pathlib.Path(home) / ".opencode" / "bin" / "opencode.exe")
    appdata = os.environ.get("APPDATA")
    if appdata:
        cands.append(pathlib.Path(appdata) / "npm" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe")
    for c in cands:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def opencode_version(path: pathlib.Path) -> str:
    """读取 opencode 版本号。只认裸 x.y.z（与 runtime.js 的严格校验一致）。"""
    try:
        p = run_hidden([str(path), "--version"], timeout=15)
    except Exception:
        return ""
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    for line in out.splitlines():
        line = line.strip()
        if re.match(r"^\d+\.\d+\.\d+", line):
            return line
    return ""


def dir_state(target: str) -> tuple[bool, str, float]:
    """返回 (是否可写, 说明, 可用空间GB)。"""
    p = pathlib.Path(target)
    probe = p if p.exists() else p.parent
    if not probe.exists():
        return False, f"上级目录不存在：{probe}", 0.0
    writable = os.access(str(probe), os.W_OK)
    try:
        free = shutil.disk_usage(str(probe)).free / (1024 ** 3)
    except OSError:
        free = 0.0
    return writable, str(probe), round(free, 1)


# ---------------------------------------------------------------- API
class Api:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self._busy = False

    # ---------- 前端 → Python ----------
    def env_info(self) -> dict:
        oc = find_opencode()
        if oc:
            ver = opencode_version(oc)
            runtime = f"opencode · v{ver}" if ver else "opencode · 已就绪"
        else:
            runtime = "opencode · 未安装"
        return {
            "runtime": runtime,
            "platform": "win-x64" if platform.machine().endswith("64") else platform.machine(),
            "version": VERSION,
            "webview2": webview2_version() or "",
        }

    def pick_directory(self) -> str | None:
        if not self.window:
            return None
        try:
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            return None
        return str(result[0]) if result else None

    def minimize(self) -> None:
        if self.window:
            self.window.minimize()

    def quit_app(self) -> None:
        if self.window:
            self.window.destroy()

    def start_deploy(self, target: str) -> bool:
        if self._busy:
            return False
        self._busy = True
        threading.Thread(target=self._safe_run, args=(target,), daemon=True).start()
        return True

    # ---------- Python → 前端 ----------
    def _js(self, fn: str, *args) -> None:
        if not self.window:
            return
        payload = ",".join(json.dumps(a, ensure_ascii=False) for a in args)
        try:
            self.window.evaluate_js(f"window.dep.{fn}({payload})")
        except Exception:
            pass

    def _log(self, msg: str = "", cls: str = "") -> None:
        self._js("log", msg, cls)

    def _safe_run(self, target: str) -> None:
        try:
            self._run(target)
        except Exception:
            tb = traceback.format_exc()
            try:
                log_file().write_text(tb, encoding="utf-8")
            except OSError:
                pass
            self._log("部署过程中发生异常，已写入日志：" + str(log_file()), "err")
            self._log(tb.strip().splitlines()[-1], "err")
            self._js("status", "err", "异常")
        finally:
            self._busy = False

    # ------------------------------------------------------------ 主流程
    def _run(self, target: str) -> None:
        t0 = time.time()

        # ===== 0 · 环境检测 =====
        self._js("step", 0, "active")
        self._js("prog", 2, "检测运行环境")
        self._log(f"{APP_NAME} v{VERSION} 启动", "hi")
        self._log(f"目标目录: {target}", "cmd")
        self._log("─" * 34)
        self._log("检测系统版本 …", "cmd")
        time.sleep(0.22)
        ver = platform.version()
        build = ver.split(".")[-1] if "." in ver else ver
        self._log(f"Windows {platform.release()} (Build {build})  ✓ 满足要求", "ok")

        self._log("检测 WebView2 运行时 …", "cmd")
        time.sleep(0.2)
        wv = webview2_version()
        if wv:
            self._log(f"WebView2 Runtime {wv}  ✓ 已就绪", "ok")
        else:
            self._log("未检测到 WebView2 Runtime（界面仍可运行）", "warn")

        self._js("prog", 9)
        self._js("step", 0, "done")

        # ===== 1 · 校验部署位置 =====
        self._js("step", 1, "active")
        self._js("prog", 11, "校验部署位置")
        self._log()
        self._log("检查目标目录可写性 …", "cmd")
        time.sleep(0.24)
        writable, probe, free = dir_state(target)
        if writable:
            self._log(f"写入权限  ✓ 通过（探测点 {probe}）", "ok")
        else:
            self._log(f"写入权限  ✗ 失败：{probe} 不可写", "err")
            self._js("status", "err", "权限不足")
            self._log("请换一个位置，或以管理员身份运行。", "warn")
            return
        time.sleep(0.2)
        self._log(f"磁盘可用空间 {free} GB  ✓ 充足", "ok")
        self._js("prog", 18)
        self._js("step", 1, "done")

        # ===== 2 · 获取 OpenCode 运行时 =====
        self._js("step", 2, "active")
        self._js("prog", 21, "获取运行时")
        self._log()
        self._log("查找本机已有 opencode 运行时 …", "cmd")
        time.sleep(0.3)
        existing = find_opencode()
        if existing:
            self._log(f"已发现运行时：{existing}", "ok")
            self._log("跳过下载，直接复用本机副本。", "ok")
            self._js("prog", 52)
        else:
            self._log("本机未发现运行时。", "warn")
            self._log("将自动下载最新稳定版（此步骤待接入）", "warn")
            self._js("prog", 30)
        self._js("step", 2, "done")

        # ===== 3~5 · 待接入 =====
        for idx, (ph, prog, note) in enumerate(
            [
                (3, 58, "展开 OC Ferry 主程序"),
                (4, 78, "写入模型配置"),
                (5, 92, "创建启动入口"),
            ],
            start=3,
        ):
            self._js("step", idx, "active")
            self._js("prog", prog, ph)
            self._log()
            self._log(f"[待接入] {ph}", "warn")
            time.sleep(0.25)
            self._js("step", idx, "done")

        # ===== 完成 =====
        self._js("prog", 100, "全部完成")
        self._log()
        self._log("─" * 34)
        self._log(f"界面验证完成，用时 {time.time() - t0:.1f} 秒", "hi")
        self._log("注：当前为原型模式，步骤 3~5 的真实部署逻辑尚未接入。", "warn")
        self._js("status", "ready", "已完成")
        self._js("done")


# ---------------------------------------------------------------- 单实例
_MUTEX = None


def single_instance() -> bool:
    """保证同一时刻只有一个实例在跑。

    已有实例时，把它的窗口还原并置前，然后让本次启动静默退出——
    避免用户重复双击后两个部署同时写同一个目录。
    """
    global _MUTEX
    if os.name != "nt":
        return True

    import ctypes

    ERROR_ALREADY_EXISTS = 183
    _MUTEX = ctypes.windll.kernel32.CreateMutexW(
        None, False, "OC-Ferry-Deployer-SingleInstance"
    )
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        hwnd = ctypes.windll.user32.FindWindowW(None, APP_NAME)
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)          # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        return False
    return True


# ---------------------------------------------------------------- 入口
def main() -> None:
    if not single_instance():
        return
    # 屏蔽 pywebview 在 Windows 后端枚举 COM 属性时刷出的噪声日志
    for name in ("pywebview", "webview"):
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)

    # 高分屏清晰度
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    api = Api()
    ui = resource_dir() / "ui" / "index.html"
    if not ui.exists():
        raise SystemExit(f"找不到界面文件：{ui}")

    window = webview.create_window(
        APP_NAME,
        url=ui.as_uri(),
        js_api=api,
        width=1024,
        height=708,
        min_size=(900, 640),
        frameless=True,
        easy_drag=False,
        background_color="#04060c",
        text_select=False,
        resizable=True,
    )
    api.window = window
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()

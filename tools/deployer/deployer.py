# -*- coding: utf-8 -*-
"""
OC Ferry Deployer — 科技感一键部署器（pywebview 外壳 / 开发版）

本文件只负责「窗口 + 前端通信」，部署逻辑在 _run() 中逐步接入。
打包：见 build.py
"""
from __future__ import annotations

import base64
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

# 同目录模块。放在脚本目录下 import 即可，PyInstaller 会自动收集。
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import netfetch                      # noqa: E402
import sources                       # noqa: E402
from netfetch import FetchError      # noqa: E402

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


# ---------------------------------------------------------------- 诊断（默认关闭）
# 用法：设 FERRY_TRACE=1 启动，会在 %TEMP%\OC-Ferry-Deployer\ 下产出
#   trace-<pid>.log  每 5 秒 dump 一次「全部线程的 Python 栈」（faulthandler）
#   hb-<pid>.log     每秒一行心跳，用来区分「进程活着但 UI 线程卡」与「整个进程死了」
#   stage-<pid>.log  启动阶段标记，定位卡在哪一步
# 全部为默认关闭，正式产物零开销。
_TRACE_FH = None


def trace_enabled() -> bool:
    # 1 = 线程栈 + 心跳 + 阶段标记；2 = 再加内省探针
    return os.environ.get("FERRY_TRACE") in ("1", "2")


def trace_dir() -> pathlib.Path:
    d = pathlib.Path(os.environ.get("TEMP", ".")) / "OC-Ferry-Deployer"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stage(msg: str) -> None:
    if not trace_enabled():
        return
    try:
        with open(trace_dir() / f"stage-{os.getpid()}.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')}  {msg}\n")
    except OSError:
        pass


def install_trace() -> None:
    global _TRACE_FH
    if not trace_enabled():
        return
    import faulthandler

    pid = os.getpid()
    _TRACE_FH = open(trace_dir() / f"trace-{pid}.log", "ab", buffering=0)
    _TRACE_FH.write(f"\n===== run pid={pid} {time.strftime('%H:%M:%S')} =====\n".encode())
    faulthandler.dump_traceback_later(5, repeat=True, file=_TRACE_FH)
    _stage("T0 进程启动，trace 已挂载")

    def heartbeat():
        n = 0
        p = trace_dir() / f"hb-{pid}.log"
        while True:
            n += 1
            try:
                with open(p, "a", encoding="utf-8") as f:
                    f.write(f"{n}\n")
            except OSError:
                pass
            time.sleep(1)

    threading.Thread(target=heartbeat, daemon=True).start()


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


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def desktop_dir() -> pathlib.Path:
    """取真实桌面路径。

    不能直接拼 ``~/Desktop`` —— 中文系统上桌面叫「桌面」，而且很可能被
    OneDrive 重定向到 ``%USERPROFILE%\\OneDrive\\桌面``。注册表里的
    ``User Shell Folders\\Desktop`` 才是权威值（值里可能含 %USERPROFILE% 这类变量）。
    """
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            raw = winreg.QueryValueEx(k, "Desktop")[0]
        path = pathlib.Path(os.path.expandvars(raw))
        if path.is_dir():
            return path
    except OSError:
        pass
    return pathlib.Path(os.environ.get("USERPROFILE", ".")) / "Desktop"


def make_shortcut(lnk_path: str, target: str, workdir: str,
                  icon: str | None = None, description: str = "") -> tuple[bool, str]:
    """建一个 .lnk 快捷方式，返回 (是否成功, 错误信息)。

    命令走 ``-EncodedCommand``（UTF-16LE + base64）：安装路径里几乎必然有
    中文和空格，直接拼命令行会被代码页和引号规则折腾得七零八落，
    而 base64 是纯 ASCII，完全绕开这一层。
    """
    q = lambda s: str(s).replace("'", "''")          # noqa: E731 - PowerShell 单引号转义
    ps = (
        "$ErrorActionPreference = 'Stop'\n"
        "$w = New-Object -ComObject WScript.Shell\n"
        f"$s = $w.CreateShortcut('{q(lnk_path)}')\n"
        f"$s.TargetPath = '{q(target)}'\n"
        f"$s.WorkingDirectory = '{q(workdir)}'\n"
        f"$s.Description = '{q(description)}'\n"
        + (f"$s.IconLocation = '{q(icon)},0'\n" if icon else "")
        + "$s.Save()\n"
    )
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        p = run_hidden(["powershell", "-NoProfile", "-NonInteractive",
                        "-EncodedCommand", encoded], timeout=40)
    except Exception as e:                            # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    if p.returncode != 0:
        return False, ((p.stderr or "") + (p.stdout or "")).strip()[:200]
    return os.path.isfile(lnk_path), ""


# ---------------------------------------------------------------- API
class Api:
    """暴露给 JS 的接口对象。

    ⚠️ 踩过的坑（必现死锁，不是偶发）：

    pywebview 在页面加载完成后，会在**注入线程**里执行
    ``webview/util.py: inject_pywebview() -> generate_func() -> get_functions()``，
    而 ``get_functions()`` 会 ``for name in dir(obj)`` 逐个 ``getattr``，
    并把「非 callable 且有 __module__」的属性**递归**展开成 JS 可调函数清单。

    所以只要这个类里挂了一个 pywebview 自己的对象（我们原来挂了 ``self.window``），
    它就会顺着 ``Api.window -> Window.events/.state/.dom/...`` 一路递归进框架内部，
    而这些属性里有一批是**会阻塞的 property**：例如 ``Window.width/.height/.x/.y``
    会先 ``self.events.shown.wait(15)`` 再跨线程去读 WinForms 控件。

    实测后果（faulthandler 抓到的全线程栈，10 秒稳定复现）：
      * 注入线程卡死在 ``util.py:196 in get_functions``
      * 卡死时**持有 GIL** -> 心跳线程停摆
      * WinForms 消息循环停泵 -> 窗口标题出现「(未响应)」，界面定格在最后绘制的一帧

    两条防线，双保险：
      1. 内部引用一律用下划线开头（``_window``），``get_functions`` 会跳过 ``_`` 前缀；
      2. 显式实现 ``__dir__``，只暴露真正要给 JS 调的方法 —— 从根上杜绝递归。
    """

    # 唯一允许暴露给 JS 的方法清单
    JS_METHODS = ("env_info", "pick_directory", "minimize", "quit_app", "start_deploy")

    def __dir__(self):
        # 见类文档：绝不能让 pywebview 顺着我们的属主对象往框架里递归。
        return list(self.JS_METHODS)

    def __init__(self) -> None:
        self._window: webview.Window | None = None
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
        if not self._window:
            return None
        try:
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            return None
        return str(result[0]) if result else None

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def quit_app(self) -> None:
        if self._window:
            self._window.destroy()

    def start_deploy(self, target: str) -> bool:
        if self._busy:
            return False
        self._busy = True
        threading.Thread(target=self._safe_run, args=(target,), daemon=True).start()
        return True

    # ---------- Python → 前端 ----------
    def _js(self, fn: str, *args) -> None:
        if not self._window:
            return
        payload = ",".join(json.dumps(a, ensure_ascii=False) for a in args)
        try:
            self._window.evaluate_js(f"window.dep.{fn}({payload})")
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

    # ---------- 流程辅助 ----------
    def _fail(self, step: int, msg: str) -> None:
        """把某一步标记为失败，并让流程停在这里。"""
        self._log(msg, "err")
        self._js("step", step, "fail")
        self._js("status", "err", "部署失败")

    def _progress(self, lo: float, hi: float, phase: str):
        """把 [0,1] 的进展映射到进度条的 [lo, hi] 区间，并节流推给前端。

        下载 150 MB 会触发六百多次回调，每次都 evaluate_js 会把界面线程打满，
        所以限制成最快每 0.12 秒推一次。

        两个例外必须放行，否则进度条会停在 99% 让人以为卡住了：
          * 下载完成那一次（got >= total）无条件推；
          * 服务器没给 Content-Length 时（total 为 0）没法算百分比，
            改按时间推，显示已下载的绝对体积。
        """
        state = {"t": 0.0, "last": -1}

        def cb(got: int, total: int) -> None:
            now = time.monotonic()
            if total:
                frac = got / total
                pct = int(frac * 100)
                if got < total and (pct == state["last"] or now - state["t"] < 0.12):
                    return
                label = f"{phase} {pct}%"
            else:
                if now - state["t"] < 0.12:
                    return
                frac = 0.0
                label = f"{phase} {human_size(got)}"
            state["t"] = now
            state["last"] = int(frac * 100) if total else -1
            self._js("prog", lo + (hi - lo) * frac, label)

        return cb

    def _download(self, url: str, dest_path: pathlib.Path, size: int,
                  lo: float, hi: float, phase: str) -> None:
        """下载到 dest_path；已有完整同名文件则直接跳过。

        「跳过」这一条是给重试用的：上一次跑到一半失败，这次不必重新下 150 MB。
        """
        if size and dest_path.is_file() and dest_path.stat().st_size == size:
            self._log(f"{dest_path.name} 已存在且大小正确，跳过下载。", "ok")
            self._js("prog", hi, phase)
            return
        self._log(f"下载 {dest_path.name} …", "cmd")
        netfetch.http_download(url, str(dest_path), self._progress(lo, hi, phase))
        self._log(f"下载完成 {human_size(dest_path.stat().st_size)}  ✓", "ok")
        self._js("prog", hi, phase)

    # ------------------------------------------------------------ 主流程
    def _run(self, target: str) -> None:
        t0 = time.time()
        dest = pathlib.Path(target)

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
        if not writable:
            return self._fail(1, f"写入权限  ✗ 失败：{probe} 不可写（请换一个位置，或以管理员身份运行）")
        self._log(f"写入权限  ✓ 通过（探测点 {probe}）", "ok")

        # 门槛按「解压后体积 + 余量」算。压缩包本身会落在目标盘的 .ocferry-setup 下，
        # 但重试时可以复用，所以不把它计进硬门槛。
        need_gb = 0.9
        if free < need_gb:
            return self._fail(1, f"磁盘可用空间 {free} GB 不足（至少需要 {need_gb} GB）")
        self._log(f"磁盘可用空间 {free} GB  ✓ 充足", "ok")

        setup = dest / ".ocferry-setup"
        setup.mkdir(parents=True, exist_ok=True)
        self._js("prog", 12)
        self._js("step", 1, "done")

        # ===== 2 · 展开 OC Ferry 主程序 =====
        self._js("step", 2, "active")
        self._js("prog", 13, "解析发布信息")
        self._log()
        self._log("查询最新发布 …", "cmd")
        try:
            payload = sources.resolve_payload()
        except FetchError as e:
            return self._fail(2, f"解析发布信息失败：{e}")
        self._log(f"来源：{payload['source']}", "ok")
        size_note = f"（{human_size(payload['size'])}）" if payload["size"] else ""
        self._log(f"安装包 {payload['name']}{size_note}", "cmd")

        zip_path = setup / payload["name"]
        try:
            self._download(payload["url"], zip_path, payload["size"], 14, 62, "下载主程序")
        except FetchError as e:
            return self._fail(2, f"下载失败：{e}")

        # 让路策略：先把旧 app/ 改名，新的一旦解压失败还能改回来。
        # 直接往旧目录上覆盖写会留下一个很难受的中间态 —— 解压到一半失败，
        # 用户既没有新版本、也没有完整的老版本。
        old_app = dest / "app"
        parked = None
        if old_app.exists():
            parked = dest / f"app.old-{int(time.time())}"
            self._log(f"检测到已有安装，先移开旧目录 → {parked.name}", "warn")
            try:
                old_app.rename(parked)
            except OSError as e:
                return self._fail(2, f"无法移动旧目录（主程序可能正在运行，请先退出）：{e}")

        self._log("展开应用文件 …", "cmd")
        try:
            count = netfetch.extract_zip(str(zip_path), str(dest),
                                         self._progress(62, 76, "展开应用文件"))
        except Exception as e:                        # noqa: BLE001
            if parked is not None:
                shutil.rmtree(old_app, ignore_errors=True)
                parked.rename(old_app)
                self._log("解压失败，已回滚到原有安装。", "warn")
            return self._fail(2, f"解压失败：{type(e).__name__}: {e}")

        if parked is not None:
            if os.environ.get("FERRY_KEEP_OLD") == "1":
                # 想留一份旧版本以便回滚的用户可以开这个
                self._log(f"按设置保留旧版本备份：{parked.name}", "cmd")
            else:
                shutil.rmtree(parked, ignore_errors=True)
        self._log(f"展开 {count} 个文件  ✓ 完毕", "ok")
        self._js("prog", 76)
        self._js("step", 2, "done")

        # ===== 3 · 获取 OpenCode 运行时 =====
        self._js("step", 3, "active")
        self._js("prog", 78, "获取 OpenCode 运行时")
        self._log()
        self._log("查询 OpenCode 官方版本 …", "cmd")
        try:
            oc = sources.resolve_opencode()
        except FetchError as e:
            return self._fail(3, f"获取版本信息失败：{e}")
        oc_ver = oc["version"]
        self._log(f"官方最新稳定版 {oc_ver}（源：{oc['source']}）", "ok")

        # 落点必须和主程序 findRuntime() 的约定一致：
        #   <dataDir>/runtime/<版本>/opencode.exe
        # 版本号对上，主程序启动时就直接复用，不会再自己下一遍 60 MB。
        rt_exe = dest / "data" / "runtime" / oc_ver / "opencode.exe"

        if rt_exe.is_file() and opencode_version(rt_exe) == oc_ver:
            self._log(f"运行时已就绪，跳过下载。", "ok")
            self._js("prog", 94)
            self._js("step", 3, "done")
        else:
            local = find_opencode()
            local_ver = opencode_version(local) if local else ""
            if local and local_ver == oc_ver:
                rt_exe.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local, rt_exe)
                self._log(f"复用本机已有的同版本运行时：{local}", "ok")
                self._js("prog", 94)
                self._js("step", 3, "done")
            else:
                if local:
                    self._log(f"本机运行时版本（{local_ver or '未知'}）与官方 {oc_ver} 不符，改为下载。", "warn")
                tgz = setup / f"opencode-{oc_ver}.tgz"
                try:
                    self._download(oc["url"], tgz, 0, 80, 90, "下载运行时")
                except FetchError as e:
                    return self._fail(3, f"下载运行时失败：{e}")

                # 校验值来自官方元数据：镜像的字节和它不符就不能装。
                # 这正是镜像被投毒时唯一能拦住的地方，所以宁可装不上也不放行。
                self._log("校验 SHA-512 …", "cmd")
                if oc["integrity"] and netfetch.sha512_b64(str(tgz)) != oc["integrity"]:
                    tgz.unlink(missing_ok=True)
                    return self._fail(3, "运行时完整性校验失败，已丢弃该文件（镜像字节与官方元数据不符）")
                self._log("完整性校验通过  ✓", "ok")

                self._log("提取二进制 …", "cmd")
                try:
                    netfetch.extract_tar_member(str(tgz), sources.TARBALL_MEMBER, str(rt_exe))
                except Exception as e:                # noqa: BLE001
                    return self._fail(3, f"提取运行时失败：{type(e).__name__}: {e}")
                tgz.unlink(missing_ok=True)
                self._log(f"运行时已就位 {rt_exe}", "ok")
                self._js("prog", 94)
                self._js("step", 3, "done")

        # ===== 4 · 创建启动入口 =====
        self._js("step", 4, "active")
        self._js("prog", 95, "创建启动入口")
        self._log()
        launcher = dest / "启动 OC Ferry.bat"
        main_exe = dest / "app" / "OC Ferry.exe"

        if not main_exe.is_file():
            return self._fail(4, f"安装包里没有主程序（{main_exe}）")
        self._log(f"主程序就位  {main_exe.name}  ✓", "ok")

        if launcher.is_file():
            self._log("启动脚本就位  ✓", "ok")
            if os.environ.get("FERRY_NO_SHORTCUT") == "1":
                # 自动化测试用：别往用户桌面上真的扔快捷方式
                self._log("已跳过桌面快捷方式（FERRY_NO_SHORTCUT=1）", "cmd")
            else:
                lnk = desktop_dir() / "OC Ferry.lnk"
                ok, err = make_shortcut(str(lnk), str(launcher), str(dest),
                                        icon=str(main_exe),
                                        description="OC Ferry · 本地模型摆渡")
                if ok:
                    self._log(f"桌面快捷方式已创建  {lnk}", "ok")
                else:
                    self._log(f"桌面快捷方式创建失败（不影响使用）：{err}", "warn")
        else:
            self._log("安装包里没有启动脚本，跳过快捷方式。", "warn")
        self._js("prog", 98)
        self._js("step", 4, "done")

        # ===== 收尾 =====
        shutil.rmtree(setup, ignore_errors=True)
        self._js("prog", 100, "全部完成")
        self._log()
        self._log("─" * 34)
        self._log(f"部署完成，用时 {time.time() - t0:.1f} 秒", "hi")
        self._log(f"安装位置：{dest}", "cmd")
        self._log(f"启动方式：双击安装目录里的「{launcher.name}」，或用桌面快捷方式。", "hi")
        self._js("status", "ready", "已完成")
        self._js("done")


# ---------------------------------------------------------------- 内省探针（FERRY_TRACE=2）
def probe_introspection(root, path="api.window", depth=0, seen=None, max_depth=6) -> None:
    """逐条复刻 pywebview ``get_functions()`` 的遍历，把每一步写进 stage 日志。

    用途：定位「到底是哪个属性把注入线程卡死」——日志写在 getattr 之前，
    所以卡死时最后一行就是元凶。（FERRY_TRACE=2 时在守护线程里跑，会冻结界面，仅用于取证。）
    """
    import inspect as _inspect

    if seen is None:
        seen = set()
    pad = "  " * depth
    if depth > max_depth:
        _stage(f"{pad}[到达深度上限] {path}")
        return
    try:
        names = dir(root)
    except Exception as e:
        _stage(f"{pad}dir({path}) 失败: {e!r}")
        return

    for name in names:
        if name.startswith("_"):
            continue
        full = f"{path}.{name}"
        _stage(f"{pad}→ getattr({full})   [宿主 {type(root).__name__}]")
        try:
            attr = getattr(root, name)
        except Exception as e:
            _stage(f"{pad}  ✗ {type(e).__name__}: {e}")
            continue
        _stage(f"{pad}  = {type(attr).__name__} {repr(attr)[:70]}")

        try:
            if not getattr(attr, "_serializable", True):
                _stage(f"{pad}  · 跳过（_serializable=False）")
                continue
        except Exception:
            pass

        if _inspect.ismethod(attr) or _inspect.isfunction(attr):
            continue
        try:
            recurse = _inspect.isclass(attr) or (
                isinstance(attr, object) and not callable(attr) and hasattr(attr, "__module__")
            )
        except Exception:
            recurse = False
        if recurse:
            if id(attr) in seen:
                _stage(f"{pad}  · 跳过（已访问）")
                continue
            seen.add(id(attr))
            probe_introspection(attr, full, depth + 1, seen, max_depth)


# ---------------------------------------------------------------- 单实例
_MUTEX = None


def single_instance() -> bool:
    """保证同一时刻只有一个实例在跑。

    实现上有两个坑，都踩过：

    1. 必须用 ``use_last_error=True`` + ``ctypes.get_last_error()`` 读错误码。
       直接调 ``windll.kernel32.GetLastError()`` 不可靠：ctypes 在两次 Win32
       调用之间可能插入其它调用，把 last error 覆盖掉。一旦被覆盖，第二个实例
       就会把「已有实例」误判成「没有」，继续启动并创建第二个 WebView2，
       两个实例撞在一起会直接卡死（实测表现为窗口「未响应」）。

    2. 判定已存在后，**不要碰对方的窗口**。
       实测（双实例撞车压力测试）：在对方 WebView2 尚未初始化完成时
       给它发 SC_RESTORE 或抢前台，会把对方窗口卡成「未响应」。
       ShowWindow 是同步等待、SetForegroundWindow 会打断初始化、
       PostMessage(SC_RESTORE) 同样有副作用 —— 三种都试过，都会出问题。
       最安全的是静默退出，本次启动不做任何 UI 动作。
    """
    global _MUTEX
    if os.name != "nt":
        return True

    import ctypes

    ERROR_ALREADY_EXISTS = 183
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]

    _MUTEX = kernel32.CreateMutexW(None, False, "OC-Ferry-Deployer-SingleInstance")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    return True


# ---------------------------------------------------------------- 入口
def main() -> None:
    install_trace()
    _stage("T1 main() 进入")
    if not single_instance():
        return
    _stage("T2 单实例检查通过")
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
    _stage("T3 界面文件就位")

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
    api._window = window
    _stage("T4 create_window 完成，准备 webview.start()")

    if os.environ.get("FERRY_TRACE") == "2":

        def probe_later():
            time.sleep(4)  # 等窗口起来、页面加载完
            _stage("===== 开始内省探测（定位卡死属性）=====")
            probe_introspection(api._window)
            _stage("===== 内省探测结束（没卡）=====")

        threading.Thread(target=probe_later, daemon=True).start()

    webview.start(gui="edgechromium", debug=False)
    _stage("T5 webview.start() 已返回（窗口关闭）")


if __name__ == "__main__":
    main()

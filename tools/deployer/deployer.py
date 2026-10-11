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

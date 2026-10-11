# -*- coding: utf-8 -*-
"""部署器 Python 端逻辑自测（不创建窗口）。"""
import importlib.util
import json
import pathlib
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("deployer_mod", HERE / "deployer.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["deployer_mod"] = mod
spec.loader.exec_module(mod)

FAIL = []


def check(label, fn, expect_ok=True):
    try:
        val = fn()
        print(f"  [ OK ] {label} -> {val!r}")
        return val
    except Exception as e:
        print(f"  [FAIL] {label} -> {type(e).__name__}: {e}")
        FAIL.append(label)
        return None


print("=" * 64)
print("A. Python 逻辑层自测")
print("=" * 64)

check("A1 webview2_version()", mod.webview2_version)
check("A2 find_opencode()", mod.find_opencode)

tmp = pathlib.Path(tempfile.gettempdir()) / "ocferry-selftest"
print("\n  A3 dir_state(合法目录) —— 目标:", tmp)
check("A3 dir_state()", lambda: mod.dir_state(str(tmp)))

print()
check("A4 dir_state(不存在的盘)", lambda: mod.dir_state(r"Z:\nonexistent\deep\path"))
check("A5 resource_dir()", mod.resource_dir)

print()
api = mod.Api()
print("  A6 Api.env_info():")
check("A6 env_info()", lambda: json.dumps(api.env_info(), ensure_ascii=False))

print()
try:
    api._js("log", "no-window-should-be-silent")
    print("  [ OK ] A7 _js() 在 window=None 时静默通过")
except Exception as e:
    print(f"  [FAIL] A7 _js() -> {type(e).__name__}: {e}")
    FAIL.append("A7")

check("A8 log_file()", mod.log_file)

print()
ui = mod.resource_dir() / "ui" / "index.html"
print(f"  A9 UI 文件存在: {ui.exists()}  ({ui})")
if not ui.exists():
    FAIL.append("A9")

ico = HERE / "app.ico"
print(f"  A10 图标存在: {ico.exists()}")
if not ico.exists():
    FAIL.append("A10")

# ---- A11~A13：回归防护 ------------------------------------------------
# 背景：pywebview 的 inject_pywebview() -> get_functions() 会 for name in dir(js_api)
# 逐个 getattr 并把「非 callable 且有 __module__」的属性递归展开。
# 一旦 js_api 上挂了 pywebview 自己的对象（哪怕只是 self.window），
# 它就会顺着 Window.native 递归进 WinForms/COM 的整个 .NET 对象图，
# 从后台线程跨套间读 WebView2 控件属性 -> 挂住并持有 GIL -> 窗口「未响应」。
# 这三条断言就是防止这个坑被重新引入。
print()
exposed = dir(api)
print(f"  A11 Api.__dir__() 暴露清单: {sorted(exposed)}")
if sorted(exposed) != sorted(mod.Api.JS_METHODS):
    print("       [FAIL] 暴露清单与 JS_METHODS 不一致")
    FAIL.append("A11")

leak = []
for _name in exposed:
    _val = getattr(api, _name, None)
    if _val is not None and not callable(_val):
        leak.append(f"{_name}={type(_val).__name__}")
print(f"  A12 暴露项里的非 callable 泄漏: {leak or '无'}")
if leak:
    print("       [FAIL] 有框架对象会被 pywebview 递归内省")
    FAIL.append("A12")

print(f"  A13 内部窗口引用已下划线命名: {hasattr(api, '_window')}")
if not hasattr(api, "_window"):
    FAIL.append("A13")

# ---- A14~A20：新流程用到的纯函数与安全边界 ------------------------------
nf, src = mod.netfetch, mod.sources

print()
check("A14 human_size()",
      lambda: [mod.human_size(n) for n in (512, 4096, 5 * 1024 ** 2, 3 * 1024 ** 3)])

print()
_desk = mod.desktop_dir()
print(f"  A15 desktop_dir() -> {_desk}  (存在={_desk.is_dir()})")
if not _desk.is_dir():
    FAIL.append("A15")

# 压缩包是外来输入：解压前必须先把路径夹在目标目录里，否则一个
# 精心构造的 ../../ 就能往系统目录里写文件。
print()
_missed = []
for _n in ["../evil.txt", "a/../../evil.txt", "C:/Windows/system32/x.dll", "/etc/passwd"]:
    try:
        nf._safe_join(r"C:\dest", _n)
        _missed.append(_n)
    except nf.FetchError:
        pass
print(f"  A16 _safe_join 拒绝越界路径: {'全部拒绝' if not _missed else '漏放 ' + str(_missed)}")
if _missed:
    FAIL.append("A16")
_ok_path = nf._safe_join(r"C:\dest", r"app\bin\x.exe")
print(f"      正常相对路径放行 -> {_ok_path}")
if not _ok_path.lower().startswith("c:\\dest"):
    FAIL.append("A16")

print()
_zdir = pathlib.Path(tempfile.gettempdir()) / "ocferry-ziptest"
_zdir.mkdir(parents=True, exist_ok=True)
_zp = _zdir / "t.zip"
with zipfile.ZipFile(_zp, "w") as _zf:
    _zf.writestr("app/hello.txt", "你好")
    _zf.writestr("app/sub/x.bin", b"\x00\x01\x02")
_out = _zdir / "out"
_cnt = nf.extract_zip(str(_zp), str(_out))
_txt = (_out / "app" / "hello.txt").read_text(encoding="utf-8")
print(f"  A17 extract_zip 往返: {_cnt} 个文件, hello.txt={_txt!r}")
if _cnt != 2 or _txt != "你好" or not (_out / "app" / "sub" / "x.bin").is_file():
    FAIL.append("A17")

print()
_p = src.resolve_payload({"FERRY_PAYLOAD_URL": "https://example.com/a.zip"})
print(f"  A18 resolve_payload 覆盖 -> {_p['url']}")
if _p["url"] != "https://example.com/a.zip":
    FAIL.append("A18")
_o = src.resolve_opencode({"FERRY_OPENCODE_TARBALL": "https://example.com/o.tgz"})
print(f"  A19 resolve_opencode 覆盖 -> {_o['url']}")
if _o["url"] != "https://example.com/o.tgz":
    FAIL.append("A19")

# 进度节流：六百多次回调不能变成六百多次 evaluate_js；但收尾那一次
# 必须推得出去，否则进度条会永久停在 99%。
print()
_api2 = mod.Api()
_pushed = []
_api2._js = lambda fn, *a: _pushed.append(a)
_cb = _api2._progress(0, 100, "测试")
for _i in range(1001):
    _cb(_i * 1000, 1000000)
print(f"  A20 _progress 节流: 1001 次回调 -> {len(_pushed)} 次推送, 末值={_pushed[-1][0] if _pushed else None}")
if not _pushed or len(_pushed) > 200 or _pushed[-1][0] != 100:
    FAIL.append("A20")

print()
print("=" * 64)
if FAIL:
    print("失败项:", ", ".join(FAIL))
    sys.exit(1)
print("全部通过")

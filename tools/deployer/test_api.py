# -*- coding: utf-8 -*-
"""部署器 Python 端逻辑自测（不创建窗口）。"""
import importlib.util
import json
import pathlib
import sys
import tempfile

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

print()
print("=" * 64)
if FAIL:
    print("失败项:", ", ".join(FAIL))
    sys.exit(1)
print("全部通过")

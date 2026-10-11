# -*- coding: utf-8 -*-
"""列出某个 PID 的所有顶层窗口：类名 / 标题 / 是否响应 / 是否可见。

用途：卡死时确认到底是主窗口没在泵消息，还是弹了一个隐藏的模态对话框。
"""
import ctypes
import ctypes.wintypes as wt
import sys

user32 = ctypes.windll.user32

user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.SendMessageTimeoutW.restype = ctypes.c_ulong
user32.SendMessageTimeoutW.argtypes = [
    ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p,
    ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t),
]
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetClassNameW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsHungAppWindow.argtypes = [wt.HWND]
user32.IsHungAppWindow.restype = wt.BOOL

TARGET_PID = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def responding(hwnd) -> str:
    res = ctypes.c_size_t()
    ok = user32.SendMessageTimeoutW(hwnd, 0x0000, 0, 0, 0x0002, 2000, ctypes.byref(res))
    return "RESPONDING" if ok else "HUNG"


def cb(hwnd, _):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if TARGET_PID and pid.value != TARGET_PID:
        return True
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    txt = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, txt, 512)
    vis = bool(user32.IsWindowVisible(hwnd))
    hung = bool(user32.IsHungAppWindow(hwnd))
    print(
        f"pid={pid.value:<7} hwnd=0x{hwnd or 0:08x} vis={int(vis)} "
        f"IsHungAppWindow={int(hung)} {responding(hwnd):<11} class={cls.value!r} title={txt.value!r}"
    )
    return True


CB = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(cb)
user32.EnumWindows(CB, 0)

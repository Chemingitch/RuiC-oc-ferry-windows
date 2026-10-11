# -*- coding: utf-8 -*-
"""判断部署器窗口是否响应：SendMessageTimeout(WM_NULL) 是 Windows 判定「未响应」的标准手段。"""
import ctypes
import sys

user32 = ctypes.windll.user32

# 64 位下 HWND 是指针宽度，必须显式声明，否则默认 c_int 会截断
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]

TITLE = sys.argv[1] if len(sys.argv) > 1 else "OC Ferry Deployer"
hwnd = user32.FindWindowW(None, TITLE)
if not hwnd:
    print("NO_WINDOW")
    sys.exit(2)

user32.SendMessageTimeoutW.restype = ctypes.c_ulong
user32.SendMessageTimeoutW.argtypes = [
    ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p,
    ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t),
]

res = ctypes.c_size_t()
# SMTO_ABORTIFHUNG (0x0002)，2 秒超时
ok = user32.SendMessageTimeoutW(hwnd, 0x0000, 0, 0, 0x0002, 2000, ctypes.byref(res))
print("RESPONDING" if ok else "HUNG")

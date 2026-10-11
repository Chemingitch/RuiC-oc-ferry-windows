# -*- coding: utf-8 -*-
"""抓取部署器窗口截图（Win32 PrintWindow）。"""
import ctypes
import os
import sys
from ctypes import wintypes as wt

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()

TITLE = sys.argv[1] if len(sys.argv) > 1 else "OC Ferry Deployer"

hwnd = user32.FindWindowW(None, TITLE)
if not hwnd:
    print("NOT_FOUND")
    sys.exit(1)


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


rc = RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rc))
x, y = rc.left, rc.top
w, h = rc.right - rc.left, rc.bottom - rc.top
print(f"hwnd={hwnd} rect=({x},{y},{w}x{h})")

hwnd_dc = user32.GetWindowDC(hwnd)
mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
gdi32.SelectObject(mem_dc, bmp)

ok = user32.PrintWindow(hwnd, mem_dc, 2)  # PW_RENDERFULLCONTENT
print("PrintWindow =", ok)

if not ok:
    # 退路：前台 BitBlt
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    screen_dc = user32.GetDC(0)
    gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, 0x00CC0020)
    user32.ReleaseDC(0, screen_dc)
    print("fallback BitBlt done")

bi = BITMAPINFO()
bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
bi.bmiHeader.biWidth = w
bi.bmiHeader.biHeight = -h
bi.bmiHeader.biPlanes = 1
bi.bmiHeader.biBitCount = 32
bi.bmiHeader.biCompression = 0

buf = ctypes.create_string_buffer(w * h * 4)
got = gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bi), 0)
print("GetDIBits rows =", got)

from PIL import Image

img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot.png")
img.convert("RGB").save(out)
print("SAVED", out, os.path.getsize(out), "bytes")

gdi32.DeleteObject(bmp)
gdi32.DeleteDC(mem_dc)
user32.ReleaseDC(hwnd, hwnd_dc)

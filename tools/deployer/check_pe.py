# -*- coding: utf-8 -*-
"""读取 PE 头判断子系统类型：2 = WINDOWS_GUI（不分配控制台），3 = WINDOWS_CONSOLE。"""
import os
import struct
import sys

NAMES = {
    2: "WINDOWS_GUI      <- 不会创建控制台",
    3: "WINDOWS_CONSOLE  <- 会分配控制台窗口",
}


def parse(path):
    with open(path, "rb") as f:
        data = f.read(0x800)
    if data[:2] != b"MZ":
        return None
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return None
    opt = e_lfanew + 4 + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    subsystem = struct.unpack_from("<H", data, opt + 68)[0]
    return magic, subsystem


for p in sys.argv[1:]:
    r = parse(p)
    name = os.path.basename(p)
    if not r:
        print(f"{name:34s} 不是有效的 PE 文件")
        continue
    magic, sub = r
    arch = "PE32+" if magic == 0x20B else "PE32"
    print(f"{name:34s} {arch:6s} Subsystem={sub}  {NAMES.get(sub, '未知')}")

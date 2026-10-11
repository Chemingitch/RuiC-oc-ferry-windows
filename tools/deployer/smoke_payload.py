# -*- coding: utf-8 -*-
"""载荷冒烟测试：解压 zip → 真实启动 → 验证窗口响应 → 关闭。

模拟「用户从 GitHub Release 下载 zip 后解压并使用」的完整路径。
只有当解压出来的东西真能跑起来、窗口真能响应，才允许发 Release。

用法:
    python smoke_payload.py <payload.zip> <work_dir>      # 解压后启动
    python smoke_payload.py <installed_dir> --reuse       # 直接验证已部署目录

    --via-bat   通过目录里的「启动 OC Ferry.bat」启动（用户的真实路径）
    --reuse     跳过解压，直接验证一个已经装好的目录
"""
import ctypes
import ctypes.wintypes as w
import csv
import io
import os
import shutil
import subprocess
import sys
import time
import zipfile

NO_WINDOW = 0x08000000
u = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9


def extract(zip_path: str, work: str) -> str:
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    t0 = time.time()
    print(f"[1] 解压 {os.path.basename(zip_path)} → {work}")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        zf.extractall(work)
    print(f"    {len(names)} 个条目，用时 {time.time()-t0:.1f}s")
    exe = os.path.join(work, "app", "OC Ferry.exe")
    print(f"    主程序存在: {os.path.isfile(exe)}  ({exe})")
    if not os.path.isfile(exe):
        raise SystemExit("✗ 解压后找不到 app/OC Ferry.exe")
    size = os.path.getsize(exe)
    print(f"    OC Ferry.exe = {size/1024/1024:.1f} MB")
    return exe


def start(exe: str, work: str, via_bat: bool = False) -> subprocess.Popen:
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)   # 关键：不清掉的话会被当纯 Node 跑
    env.pop("ELECTRON_NO_ATTACH_CONSOLE", None)
    if via_bat:
        bat = os.path.join(work, "启动 OC Ferry.bat")
        print("[2] 通过发布包内的启动脚本启动（用户的真实路径）")
        print(f"    脚本: {bat}")
        print(f"    存在: {os.path.isfile(bat)}")
        if not os.path.isfile(bat):
            raise SystemExit("✗ 载荷里缺少启动脚本")
        p = subprocess.Popen(["cmd.exe", "/c", bat], cwd=work, env=env, creationflags=NO_WINDOW)
        print("    cmd /c 已派发（脚本内部用 start，会立刻返回）")
        return p
    print("[2] 直接启动 exe（模拟 启动 OC Ferry.bat 的环境变量）")
    env["FERRY_DATA_DIR"] = os.path.join(work, "data")
    print(f"    FERRY_DATA_DIR={env['FERRY_DATA_DIR']}")
    print(f"    ELECTRON_RUN_AS_NODE 已清除: {'ELECTRON_RUN_AS_NODE' not in env}")
    p = subprocess.Popen([exe], env=env, cwd=os.path.dirname(exe))
    print(f"    Popen ok, launcher pid={p.pid}")
    return p


def pids_of(name: str = "OC Ferry.exe") -> set:
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True).stdout.decode("gbk", "replace")
    got = set()
    for row in csv.reader(io.StringIO(out)):
        if row and row[0].strip().lower() == name.lower():
            got.add(int(row[1]))
    return got


def windows_of(pids: set):
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    found = []

    def cb(hwnd, _):
        pid = w.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            n = u.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            found.append((hwnd, pid.value, buf.value, bool(u.IsWindowVisible(hwnd))))
        return True

    u.EnumWindows(CB(cb), 0)
    return found


def responding(hwnd, timeout_ms: int = 3000) -> bool:
    """Windows 判定「未响应」的标准手段：WM_NULL + SMTO_ABORTIFHUNG。"""
    SMTO_ABORTIFHUNG = 0x0002
    res = ctypes.c_ulong()
    r = u.SendMessageTimeoutW(hwnd, 0x0000, 0, 0, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(res))
    return bool(r)


def main() -> int:
    rest = [a for a in sys.argv[1:] if not a.startswith("--")]
    reuse = "--reuse" in sys.argv          # 直接验证一个已部署好的目录
    via_bat = "--via-bat" in sys.argv or reuse

    if reuse:
        if len(rest) < 1:
            print(__doc__)
            return 2
        zip_path, work = None, os.path.abspath(rest[0])
    else:
        if len(rest) < 2:
            print(__doc__)
            return 2
        zip_path, work = os.path.abspath(rest[0]), os.path.abspath(rest[1])

    before = pids_of()
    if before:
        print(f"[!] 测试前已存在 OC Ferry 进程 {sorted(before)}，先结束它们")
        for p in before:
            subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True)
        time.sleep(2)

    if reuse:
        exe = os.path.join(work, "app", "OC Ferry.exe")
        print(f"[1] 复用已部署目录（不再解压）: {work}")
        print(f"    主程序存在: {os.path.isfile(exe)}  ({exe})")
        if not os.path.isfile(exe):
            raise SystemExit("✗ 目标目录里没有 app/OC Ferry.exe")
        print(f"    OC Ferry.exe = {os.path.getsize(exe)/1024/1024:.1f} MB")
    else:
        exe = extract(zip_path, work)

    p = start(exe, work, via_bat)

    print("[3] 等待 12 秒让 Electron 完成初始化 …")
    time.sleep(12)

    pids = pids_of()
    print(f"    OC Ferry.exe 进程: {sorted(pids) or '（无！）'}")

    wins = windows_of(pids)
    print(f"    顶层窗口数: {len(wins)}")
    for hwnd, pid, title, vis in wins:
        print(f"      HWND={hwnd} PID={pid} 标题={title!r} 可见={vis}")

    ok = False
    target = next((f for f in wins if f[3]), None)
    if target:
        hwnd, pid, title, _ = target
        resp = responding(hwnd)
        print(f"\n[4] 主窗口 HWND={hwnd} 标题={title!r}")
        print(f"    响应性检查（WM_NULL/SMTO_ABORTIFHUNG）: {'✅ 响应' if resp else '❌ 未响应（卡死）'}")
        ok = resp and ("OC Ferry" in title or title != "")
    else:
        print("\n[4] ❌ 没有可见窗口 —— 应用没起来或已隐藏到托盘")

    data_dir = os.path.join(work, "data")
    print(f"\n[5] 便携模式检查: {data_dir}")
    print(f"    data/ 已生成: {os.path.isdir(data_dir)}")
    if os.path.isdir(data_dir):
        print(f"    内含: {sorted(os.listdir(data_dir))[:8]}")

    print("\n[6] 收尾：结束进程")
    for pid in pids_of():
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(1)
    print(f"    剩余进程: {sorted(pids_of()) or '无'}")

    print("\n" + "=" * 56)
    if ok:
        print("✅ 冒烟测试通过：载荷可解压、可启动、窗口可响应")
        return 0
    print("❌ 冒烟测试失败：载荷在当前状态下不可用于发布")
    return 1


if __name__ == "__main__":
    sys.exit(main())

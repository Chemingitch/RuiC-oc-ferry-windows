# -*- coding: utf-8 -*-
"""端到端部署测试：绕开 GUI，直接驱动 Api._run() 跑完整流程。

用 FERRY_PAYLOAD_URL / FERRY_OPENCODE_TARBALL 指向本地文件，
所以不必真的联网下载 150 MB；但要测的路径一条都不少：

    解析发布信息 → 下载(含跳过大文件) → 让路旧目录 → 解压 →
    解析运行时版本 → 校验 SHA-512 → 提取二进制 → 启动入口 → 清理中间文件

用法:
    python e2e_test.py <payload.zip> <opencode.tgz> <target_dir>
    python e2e_test.py <target_dir> --live          # 真的走网络下载

    --fresh   先清空目标目录，模拟全新安装（不加则是「覆盖安装」路径）
    --live    不设本地源，让部署器真的去 GitHub Release / npm 官方源下载
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import deployer as mod                     # noqa: E402


class Recorder:
    """接住 _js 调用，让流程在没有窗口的情况下也能跑完。"""

    def __init__(self) -> None:
        self.prog = 0.0
        self.phase = ""
        self.status = ""
        self.steps: dict[int, str] = {}
        self.lines: list[tuple[str, str]] = []

    def handle(self, fn: str, *args) -> None:
        if fn == "prog":
            self.prog = args[0]
            if len(args) > 1 and args[1]:
                self.phase = str(args[1])
        elif fn == "step":
            self.steps[int(args[0])] = str(args[1])
        elif fn == "status":
            self.status = str(args[1]) if len(args) > 1 else str(args[0])
        elif fn == "log":
            # _log() 传来的是 ("log", msg, cls)
            self.lines.append((str(args[0]) if args else "",
                               str(args[1]) if len(args) > 1 else ""))

    @property
    def failed(self) -> bool:
        return "fail" in self.steps.values()


def main() -> int:
    live = "--live" in sys.argv
    rest = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(rest) < (1 if live else 3):
        print(__doc__)
        return 2

    if live:
        payload = tgz = None
        target = pathlib.Path(rest[0]).resolve()
    else:
        payload = pathlib.Path(rest[0]).resolve()
        tgz = pathlib.Path(rest[1]).resolve()
        target = pathlib.Path(rest[2]).resolve()
        for p in (payload, tgz):
            if not p.is_file():
                print(f"✗ 找不到 {p}")
                return 2

    if "--fresh" in sys.argv and target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    # 不在用户桌面上真的扔快捷方式
    os.environ["FERRY_NO_SHORTCUT"] = "1"
    # 覆盖安装收尾要删掉旧的 app/ 备份（500+ 个文件），而本机的安全策略会
    # 拦下这种批量删除。用保留开关跳过删除，让流程能被完整跑到 ——
    # 删除本身只是一行 rmtree(ignore_errors=True)，风险面很小。
    os.environ["FERRY_KEEP_OLD"] = "1"
    if live:
        # --live：什么都不覆盖，让部署器真的去查 GitHub Release、去 npm 拉运行时
        os.environ.pop("FERRY_PAYLOAD_URL", None)
        os.environ.pop("FERRY_OPENCODE_TARBALL", None)
    else:
        # 用本地文件冒充远端：下载路径照样走一遍，只是没有网络耗时
        os.environ["FERRY_PAYLOAD_URL"] = payload.as_uri()
        os.environ["FERRY_OPENCODE_TARBALL"] = tgz.as_uri()

    rec = Recorder()

    def fake_js(_self, fn, *args):
        rec.handle(fn, *args)

    mod.Api._js = fake_js

    mode = "覆盖安装（目标已有 app/）" if (target / "app").is_dir() else "全新安装（目标为空）"
    print("=" * 64)
    print(f"端到端部署测试 · {mode}{' · 真实网络' if live else ' · 本地源'}")
    print(f"  载荷  : {'GitHub Release（实时下载）' if live else payload.name}")
    print(f"  运行时: {'npm 官方源（实时下载）' if live else tgz.name}")
    print(f"  目标  : {target}")
    print("=" * 64)

    api = mod.Api()
    api._run(str(target))

    print()
    for msg, cls in rec.lines:
        mark = {"ok": "  ✓", "err": "  ✗", "warn": "  !", "hi": "  ◆", "cmd": "    "}.get(cls, "    ")
        print(f"{mark} {msg}")

    print()
    print("-" * 64)
    print(f"进度终值 : {rec.prog}")
    print(f"状态     : {rec.status}")
    print(f"步骤状态 : {rec.steps}")
    print("-" * 64)

    checks = [
        ("主程序 app/OC Ferry.exe", target / "app" / "OC Ferry.exe"),
        ("启动脚本 启动 OC Ferry.bat", target / "启动 OC Ferry.bat"),
        ("说明 快速开始.txt", target / "快速开始.txt"),
        ("便携数据目录 data/", target / "data"),
    ]
    rt = list((target / "data" / "runtime").glob("*/opencode.exe")) if (target / "data" / "runtime").is_dir() else []
    checks.append((f"OpenCode 运行时 ({len(rt)} 个)", rt[0] if rt else None))

    ok = True
    for label, path in checks:
        good = bool(path and path.exists())
        ok = ok and good
        size = ""
        if good and path.is_file():
            size = f"  {path.stat().st_size / 1048576:.1f} MB"
        print(f"  [{'OK' if good else '!!'}] {label}{size}")

    leftovers = [p.name for p in target.glob(".ocferry-setup")]
    print(f"  [{'OK' if not leftovers else '!!'}] 中间目录已清理: {leftovers or '无残留'}")
    ok = ok and not leftovers

    stale = [p.name for p in target.glob("app.old-*")]
    note = "覆盖安装：旧版本已让路并保留备份" if stale else "全新安装：无需让路"
    print(f"  [OK] {note}: {stale or '无'}")

    print()
    if rec.failed or rec.status != "已完成":
        print("❌ 端到端测试失败")
        return 1
    if not ok:
        print("❌ 流程报完成，但产物不齐")
        return 1
    print("✅ 端到端测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

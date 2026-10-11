# -*- coding: utf-8 -*-
"""把 OC Ferry 的 Windows Electron 载荷打成 zip，供 GitHub Release 分发。

用法:
    python pack_payload.py <app_dir> <out_zip> [--level 9] [--extra-dir DIR]

zip 内部结构（解压后）:
    app/
      OC Ferry.exe
      resources/app/{src,desktop,node_modules,package.json}
      locales/ ...
    启动 OC Ferry.bat       ← 来自 --extra-dir
    Start OC Ferry.bat
    快速开始.txt
    README.txt
这样部署器解压到安装目录 D:\\OC-Ferry 后，正好得到
D:\\OC-Ferry\\app\\OC Ferry.exe + 同级的启动脚本，直接双击即可用。

刻意排除：运行时数据目录（api-key / Cache / 日志 / *.db）——
那些必须由目标机首次运行时自行生成，绝不能随包分发。
"""
import os
import sys
import time
import zipfile

EXCLUDE_DIRS = {"data", "__pycache__", ".git"}
EXCLUDE_EXT = {".pyc", ".log"}


def should_skip(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    return os.path.splitext(rel)[1].lower() in EXCLUDE_EXT


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    app_dir = os.path.abspath(sys.argv[1])
    out_zip = os.path.abspath(sys.argv[2])
    level = 9
    if "--level" in sys.argv:
        level = int(sys.argv[sys.argv.index("--level") + 1])
    extra_dir = None
    if "--extra-dir" in sys.argv:
        extra_dir = os.path.abspath(sys.argv[sys.argv.index("--extra-dir") + 1])

    if not os.path.isdir(app_dir):
        print(f"[错误] 找不到目录: {app_dir}")
        return 2

    # 收集文件：app 载荷（放在 app/ 前缀下）+ 同级附加文件（启动脚本等）
    files = []
    total_raw = 0
    for root, dirs, names in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, app_dir)
            if should_skip(rel):
                continue
            try:
                total_raw += os.path.getsize(full)
            except OSError:
                continue
            files.append((full, "app/" + rel.replace("\\", "/")))

    if extra_dir:
        if not os.path.isdir(extra_dir):
            print(f"[错误] 找不到附加目录: {extra_dir}")
            return 2
        for root, dirs, names in os.walk(extra_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for n in names:
                if should_skip(n):
                    continue
                full = os.path.join(root, n)
                rel = os.path.relpath(full, extra_dir).replace("\\", "/")
                try:
                    total_raw += os.path.getsize(full)
                except OSError:
                    continue
                files.append((full, rel))

    files.sort(key=lambda t: t[1])
    print(f"源目录 : {app_dir}")
    print(f"输出   : {out_zip}")
    print(f"文件数 : {len(files)}    原始体积: {human(total_raw)}")
    print(f"压缩   : deflate level {level}")
    print("-" * 60)

    t0 = time.time()
    os.makedirs(os.path.dirname(out_zip), exist_ok=True)
    done = 0
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=level, allowZip64=True) as zf:
        for full, arc in files:
            zf.write(full, arc)
            done += 1
            if done % 25 == 0 or done == len(files):
                pct = done * 100.0 / len(files)
                el = time.time() - t0
                print(f"  [{done:4d}/{len(files)}] {pct:5.1f}%  已用 {el:6.1f}s", flush=True)

    size = os.path.getsize(out_zip)
    el = time.time() - t0
    print("-" * 60)
    print(f"完成: {human(size)}  (压缩率 {total_raw / max(size,1):.2f}:1)")
    print(f"耗时: {el:.1f}s")
    print(f"路径: {out_zip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

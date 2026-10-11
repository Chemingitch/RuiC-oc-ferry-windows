# -*- coding: utf-8 -*-
"""部署器的网络与归档工具：下载、断点续传、校验、安全解压。

刻意只用标准库。部署器要在全新的 Windows 上跑起来，多一个第三方依赖
就多一种「import 失败 = 部署失败」的可能。上游 runtime.js 用的 tar /
undici 在 Node 侧是现成的，Python 侧对应物就是 tarfile / urllib。

设计上对齐上游 src/runtime.js 的取舍：
  * 官方源优先，国内镜像兜底（GitHub / npm 双源）；
  * 下载后按官方元数据里的 integrity 做 SHA-512 校验，镜像字节对不上就不装；
  * 代理坏掉不该导致装不上 —— 直接退直连。
"""
from __future__ import annotations

import base64
import hashlib
import os
import tarfile
import urllib.error
import urllib.request
import zipfile

UA = "OC-Ferry-Deployer/1.0 (+https://github.com/Chemingitch/RuiC-oc-ferry-windows)"
CHUNK = 256 * 1024


class FetchError(RuntimeError):
    pass


# ---------------------------------------------------------------- 传输
def _openers():
    """返回 [(名字, opener)]：先跟随系统/环境变量代理，再退直连。

    为什么需要「退直连」这个分支：用户机器上很可能配了一个已经死掉的代理
    （本项目的开发机上就有一个指向 127.0.0.1:7890 的幽灵代理，git 因此常年
    推送失败）。这种情况下直连反而是唯一能走通的路。上游 runtime.js 对
    系统代理也做了同样的降级处理。
    """
    return [
        ("env-proxy", urllib.request.build_opener()),
        ("direct", urllib.request.build_opener(urllib.request.ProxyHandler({}))),
    ]


def http_get(url: str, timeout: int = 30, headers: dict | None = None) -> bytes:
    """取一个小文件（JSON 元数据），返回 bytes。"""
    last: Exception | None = None
    for label, opener in _openers():
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        try:
            with opener.open(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:                      # noqa: BLE001 - 换下一条路继续试
            last = e
            continue
    raise FetchError(f"请求失败 {url}（已尝试环境代理与直连）：{last}")


def http_download(url: str, dest: str, on_progress=None, timeout: int = 900,
                  resume: bool = True, headers: dict | None = None) -> str:
    """流式下载到 dest，支持断点续传。

    on_progress(got_bytes, total_bytes) 在每次写盘后调用。
    total 未知时传 0，调用方据此切到「不确定进度」的显示。
    """
    last: Exception | None = None
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)

    for label, opener in _openers():
        existing = 0
        if resume and os.path.exists(dest):
            existing = os.path.getsize(dest)
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        if existing:
            req.add_header("Range", f"bytes={existing}-")
        try:
            with opener.open(req, timeout=timeout) as resp:
                # 服务器不支持续传会以 200 而非 206 回应：此时必须从头写，
                # 否则会把整包追加到半截文件后面，得到一个静默损坏的压缩包。
                # file:// 源没有 status，用 getattr 兜底（自测时会指向本地包）。
                status = getattr(resp, "status", 200)
                if existing and status != 206:
                    existing = 0
                declared = 0
                try:
                    declared = int(resp.headers.get("Content-Length") or 0)
                except (AttributeError, TypeError, ValueError):
                    declared = 0
                total = declared + existing if declared else 0
                got = existing
                mode = "ab" if existing else "wb"
                with open(dest, mode) as f:
                    while True:
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if on_progress:
                            on_progress(got, total)
                return dest
        except Exception as e:                      # noqa: BLE001
            last = e
            continue
    raise FetchError(f"下载失败 {url}（已尝试环境代理与直连）：{last}")


# ---------------------------------------------------------------- 校验
def sha512_b64(path: str) -> str:
    """返回 npm 风格的 integrity 串：sha512-<base64>。"""
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return "sha512-" + base64.b64encode(h.digest()).decode()


def sha256_hex(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 解压
def _safe_join(dest: str, name: str) -> str:
    """把归档内的相对路径夹到 dest 里，拒绝绝对路径与 .. 逃逸（zip slip）。"""
    target = os.path.abspath(os.path.join(dest, name))
    root = os.path.abspath(dest)
    if target != root and not target.startswith(root + os.sep):
        raise FetchError(f"归档里含有越界路径，已拒绝：{name}")
    return target


def extract_zip(zip_path: str, dest: str, on_progress=None) -> int:
    """解压 zip 到 dest。按「已写字节」报进度，返回解压的文件数。

    zipfile 在读取时会自行校验每个条目的 CRC32，损坏的包会在这里暴露。
    """
    os.makedirs(dest, exist_ok=True)
    written = 0
    with zipfile.ZipFile(zip_path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in infos) or 1
        for info in infos:
            out = _safe_join(dest, info.filename)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as dst:
                while True:
                    chunk = src.read(CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
                    written += len(chunk)
                    if on_progress:
                        on_progress(written, total)
    return len(infos)


def extract_tar_member(tar_path: str, member: str, dest_file: str) -> str:
    """从 .tgz 里只取出 member 这一个文件，写到 dest_file。

    上游装 OpenCode 时也是「只取 package/bin/opencode.exe」，不整个展开 ——
    包里剩下的全是 Windows/macOS/Linux 各平台的冗余二进制。
    """
    os.makedirs(os.path.dirname(os.path.abspath(dest_file)), exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        try:
            entry = tf.getmember(member)
        except KeyError:
            names = [m.name for m in tf.getmembers()][:10]
            raise FetchError(f"压缩包里没有 {member}（前几项：{names}）") from None
        if not entry.isfile():
            raise FetchError(f"{member} 不是普通文件")
        src = tf.extractfile(entry)
        if src is None:
            raise FetchError(f"无法读取 {member}")
        with src, open(dest_file, "wb") as dst:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                dst.write(chunk)
    return dest_file

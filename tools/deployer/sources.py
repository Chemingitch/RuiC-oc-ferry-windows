# -*- coding: utf-8 -*-
"""部署器「从哪儿拿东西」——两处官方源，都用官方元数据自带的校验值兜底。

  1. 主程序载荷：本 fork 的 GitHub Release（zip）
  2. OpenCode 运行时：OpenCode 官方 npm 包 opencode-windows-x64（tgz）

两处都允许用环境变量覆盖，方便离线内网自己搭镜像、或给自己打测试包：
  FERRY_PAYLOAD_URL      直接指定主程序 zip 的地址
  FERRY_OPENCODE_TARBALL 直接指定 opencode 运行时的 tgz 地址
"""
from __future__ import annotations

import json
import os
import re

import netfetch
from netfetch import FetchError

# 主程序载荷所在的仓库（本 fork）。换仓库只需改这一行。
RELEASE_REPO = "Chemingitch/RuiC-oc-ferry-windows"
PAYLOAD_ASSET_RE = re.compile(r"^OC-Ferry-\d+\.\d+\.\d+-win-x64\.zip$")

# OpenCode 运行时。官方源优先，国内镜像兜底（与上游 runtime.js 同一组源）。
NPM_PKG = "opencode-windows-x64"
REGISTRIES = ["https://registry.npmjs.org", "https://registry.npmmirror.com"]
TARBALL_MEMBER = "package/bin/opencode.exe"

# 与上游 runtime.js 的 VERSION 正则一致：只认带可选预发布/构建后缀的三段式版本号。
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def resolve_payload(env: dict | None = None) -> dict:
    """定位主程序载荷，返回 {name, url, size, source}。

    环境变量 FERRY_PAYLOAD_URL 优先 —— 部署器自己的测试就靠它指向本地文件，
    不必每次都真的下载 150 MB。
    """
    env = env if env is not None else os.environ
    override = (env.get("FERRY_PAYLOAD_URL") or "").strip()
    if override:
        return {"name": os.path.basename(override.split("?")[0]) or "payload.zip",
                "url": override, "size": 0, "source": "FERRY_PAYLOAD_URL"}

    api = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"
    try:
        raw = netfetch.http_get(api, timeout=30,
                                headers={"Accept": "application/vnd.github+json"})
    except FetchError as e:
        raise FetchError(
            f"无法读取发布信息（{api}）：{e}\n"
            "如果本机网络需要走代理，请先设好 HTTPS_PROXY；"
            "也可以用 FERRY_PAYLOAD_URL 直接指定安装包地址。") from e

    try:
        data = json.loads(raw)
    except ValueError as e:
        raise FetchError(f"发布信息不是合法 JSON：{e}") from e

    if not isinstance(data, dict) or not data.get("tag_name"):
        raise FetchError("发布信息为空或格式异常（可能触发了 GitHub 的接口限流，稍后重试）")

    tag = data["tag_name"]
    for asset in data.get("assets") or []:
        name = asset.get("name") or ""
        if PAYLOAD_ASSET_RE.match(name):
            url = asset.get("browser_download_url")
            if not url:
                continue
            return {"name": name, "url": url, "size": int(asset.get("size") or 0),
                    "source": f"GitHub Release {tag}"}

    have = ", ".join(a.get("name", "?") for a in (data.get("assets") or [])) or "（无附件）"
    raise FetchError(f"Release {tag} 里没有 Windows 载荷（期望形如 OC-Ferry-x.y.z-win-x64.zip）。"
                     f"实际附件：{have}")


def resolve_opencode(env: dict | None = None) -> dict:
    """定位 OpenCode 运行时，返回 {version, url, integrity, source}。

    integrity 来自官方元数据，下载后必须命中它才落盘 —— 这是镜像被投毒时
    唯一能拦住的地方，所以宁可装不上，也不装一个校验不过的二进制。
    """
    env = env if env is not None else os.environ
    override = (env.get("FERRY_OPENCODE_TARBALL") or "").strip()
    if override:
        return {"version": env.get("FERRY_OPENCODE_VERSION", "0.0.0"),
                "url": override, "integrity": "", "source": "FERRY_OPENCODE_TARBALL"}

    failures = []
    for registry in REGISTRIES:
        host = registry.split("//", 1)[-1]
        try:
            meta = json.loads(netfetch.http_get(f"{registry}/{NPM_PKG}/latest", timeout=30))
        except (FetchError, ValueError) as e:
            failures.append(f"{host}: {e}")
            continue

        name, version = meta.get("name"), meta.get("version") or ""
        dist = meta.get("dist") or {}
        integrity, tarball = dist.get("integrity") or "", dist.get("tarball") or ""

        # 元数据本身也要过一遍：名字、版本号形态、校验值、下载地址的归属。
        # 只信「官方源域名下的官方包名」，元数据被替换也指不到别处去。
        if name != NPM_PKG:
            failures.append(f"{host}: 包名不符（{name}）")
            continue
        if not VERSION_RE.match(version):
            failures.append(f"{host}: 版本号形态不合法（{version}）")
            continue
        if not integrity.startswith("sha512-"):
            failures.append(f"{host}: 缺少 sha512 校验值")
            continue
        if not any(tarball.startswith(r + f"/{NPM_PKG}/-/") for r in REGISTRIES):
            failures.append(f"{host}: 下载地址不在已知源上（{tarball}）")
            continue

        return {"version": version, "url": tarball, "integrity": integrity, "source": host}

    raise FetchError("无法获取 OpenCode 版本信息，官方源与国内镜像均失败（"
                     + "；".join(failures) + "）")

#!/usr/bin/env bash
# 把打包好的 Windows 载荷发布到 GitHub Release。
#
# 用法:
#   ./publish-release.sh <payload.zip> [tag]
#
# 默认 tag: v0.3.0-win
# gh 不在 PATH 时用 GH 覆盖，例如:
#   GH=/path/to/gh.exe ./publish-release.sh release/OC-Ferry-0.3.0-win-x64.zip
#
# 为什么需要这个脚本而不是手敲 gh 命令：
#   release notes 里要带文件大小和 sha256，手算容易写错；
#   而且部署器（tools/deployer/deployer.py）就是按这个资产名去下载的，
#   名字一旦对不上，部署器就拉不到包。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${REPO:-Chemingitch/RuiC-oc-ferry-windows}"
GH="${GH:-gh}"
TAG="${2:-v0.3.0-win}"
TITLE="OC Ferry 0.3.0 · Windows x64 便携载荷"

ZIP="${1:-}"
if [ -z "$ZIP" ]; then
  echo "用法: $0 <payload.zip> [tag]" >&2
  exit 2
fi
ZIP="$(cd "$(dirname "$ZIP")" && pwd)/$(basename "$ZIP")"
[ -f "$ZIP" ] || { echo "✗ 找不到 $ZIP" >&2; exit 2; }

NAME="$(basename "$ZIP")"
SIZE="$(stat -c %s "$ZIP" 2>/dev/null || stat -f %z "$ZIP")"
SIZE_MB="$(awk -v b="$SIZE" 'BEGIN{printf "%.2f", b/1048576}')"
SHA="$(sha256sum "$ZIP" | awk '{print $1}')"

echo "仓库  : $REPO"
echo "tag   : $TAG"
echo "资产  : $NAME"
echo "大小  : $SIZE_MB MB ($SIZE bytes)"
echo "sha256: $SHA"
echo

NOTES="$(mktemp)"
trap 'rm -f "$NOTES"' EXIT

cat > "$NOTES" <<EOF
Windows 版 **OC Ferry 主程序**的绿色便携载荷 —— 解压即用，目标机零依赖。

- 基于上游 [HRuiCcc/RuiC-oc-ferry](https://github.com/HRuiCcc/RuiC-oc-ferry) \`v0.3.0\` 构建
- 合入本 fork 的 Windows 改动：**托盘常驻、退出清理、便携数据目录**

## 资产

| 文件 | 大小 | SHA256 |
| --- | --- | --- |
| \`$NAME\` | $SIZE_MB MB | \`$SHA\` |

## 使用方法

1. 下载 \`$NAME\`，**完整解压**到任意目录（例如 \`D:\OC-Ferry\`）。
   > 必须完整解压：\`app\\\` 子目录是主程序本体，只复制 \`OC Ferry.exe\` 是跑不起来的。
2. 双击解压目录里的 **\`启动 OC Ferry.bat\`**。
3. 程序启动后常驻系统托盘，右键托盘图标可退出。

## 目录结构

\`\`\`
OC-Ferry/
├─ app/                 主程序（Electron）
│   ├─ OC Ferry.exe
│   └─ resources/app/   源码与依赖
├─ data/                运行时数据，首次启动自动生成
├─ 启动 OC Ferry.bat     启动入口（务必用它启动）
├─ Start OC Ferry.bat   同上，英文版
└─ 快速开始.txt / README.txt
\`\`\`

## 为什么必须用 \`.bat\` 启动

启动脚本负责两件事，缺一不可：

1. 把数据目录钉在 \`./data\` —— 整个文件夹可整体搬迁，删除即干净卸载；
2. 清除父进程可能带入的 \`ELECTRON_RUN_AS_NODE\` 变量 —— 不清掉的话，
   主程序在某些环境里会被当成纯 Node 运行，窗口永远起不来。

## 运行要求

- Windows 10 / 11 (x64)
- 首次启动需要联网（自动准备隔离的 OpenCode 运行时）
- 界面依赖系统自带的 WebView2 运行时（Win11 与新版 Win10 已内置）

## 许可

MIT。上游版权归原作者 HRuiCcc 所有，详见包内与仓库中的 \`LICENSE\` / \`NOTICE.md\`。
EOF

echo "--- release notes ---"
cat "$NOTES"
echo "---------------------"
echo

if "$GH" release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "release $TAG 已存在 → 覆盖上传资产"
  "$GH" release upload "$TAG" "$ZIP" --repo "$REPO" --clobber
else
  echo "创建 release $TAG"
  "$GH" release create "$TAG" "$ZIP" --repo "$REPO" --title "$TITLE" --notes-file "$NOTES"
fi

echo
echo "✓ 发布完成"
"$GH" release view "$TAG" --repo "$REPO"

#!/usr/bin/env bash
# 把打包好的 Windows 产物发布到 GitHub Release。
#
# 用法:
#   ./publish-release.sh <payload.zip> [tag] [deployer.exe]
#
# 默认 tag: v0.3.0-win
# gh 不在 PATH 时用 GH 覆盖，例如:
#   GH=/path/to/gh.exe ./publish-release.sh release/OC-Ferry-0.3.0-win-x64.zip
#
# 为什么需要这个脚本而不是手敲 gh 命令：
#   notes 里的文件大小与 sha256 都是现算的，手填容易写错；而部署器就是按
#   「资产名」去下载的，名字一旦对不上就拉不到包。
#   notes 正文在同目录的 release-notes.md，用 {{...}} 留占位。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${REPO:-Chemingitch/RuiC-oc-ferry-windows}"
GH="${GH:-gh}"
TAG="${2:-v0.3.0-win}"
TITLE="${TITLE:-OC Ferry 0.3.0 · Windows 一键部署器 + 便携载荷}"
DEPLOYER="${3:-}"

ZIP="${1:-}"
if [ -z "$ZIP" ]; then
  echo "用法: $0 <payload.zip> [tag] [deployer.exe]" >&2
  exit 2
fi
ZIP="$(cd "$(dirname "$ZIP")" && pwd)/$(basename "$ZIP")"
[ -f "$ZIP" ] || { echo "✗ 找不到 $ZIP" >&2; exit 2; }

size_of() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1"; }
sha_of() { sha256sum "$1" | awk '{print $1}'; }
mb_of() { awk -v b="$1" -v p="$2" 'BEGIN{printf p, b/1048576}'; }

NAME="$(basename "$ZIP")"
SIZE_MB="$(mb_of "$(size_of "$ZIP")" '%.2f') MB"
SHA="$(sha_of "$ZIP")"

if [ -n "$DEPLOYER" ]; then
  DEPLOYER="$(cd "$(dirname "$DEPLOYER")" && pwd)/$(basename "$DEPLOYER")"
  [ -f "$DEPLOYER" ] || { echo "✗ 找不到 $DEPLOYER" >&2; exit 2; }
  DSIZE="$(mb_of "$(size_of "$DEPLOYER")" '%.1f') MB"
  DSHA="$(sha_of "$DEPLOYER")"
else
  DSIZE="—"
  DSHA="—"
fi

echo "仓库   : $REPO"
echo "tag    : $TAG"
echo "载荷   : $NAME  ($SIZE_MB)"
echo "         sha256 $SHA"
if [ -n "$DEPLOYER" ]; then
  echo "部署器 : $(basename "$DEPLOYER")  ($DSIZE)"
  echo "         sha256 $DSHA"
fi
echo

NOTES="$(mktemp)"
trap 'rm -f "$NOTES"' EXIT

sed -e "s|{{PAYLOAD_NAME}}|$NAME|g" \
    -e "s|{{PAYLOAD_SIZE}}|$SIZE_MB|g" \
    -e "s|{{PAYLOAD_SHA256}}|$SHA|g" \
    -e "s|{{DEPLOYER_SIZE}}|$DSIZE|g" \
    -e "s|{{DEPLOYER_SHA256}}|$DSHA|g" \
    "$HERE/release-notes.md" > "$NOTES"

echo "--- release notes 前 20 行 ---"
head -20 "$NOTES"
echo "-----------------------------"
echo

if "$GH" release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "release $TAG 已存在 → 覆盖上传资产"
  "$GH" release upload "$TAG" "$ZIP" --repo "$REPO" --clobber
  if [ -n "$DEPLOYER" ]; then
    "$GH" release upload "$TAG" "$DEPLOYER" --repo "$REPO" --clobber
  fi
  "$GH" release edit "$TAG" --repo "$REPO" --title "$TITLE" --notes-file "$NOTES"
else
  echo "创建 release $TAG"
  "$GH" release create "$TAG" "$ZIP" --repo "$REPO" --title "$TITLE" --notes-file "$NOTES"
  if [ -n "$DEPLOYER" ]; then
    "$GH" release upload "$TAG" "$DEPLOYER" --repo "$REPO" --clobber
  fi
fi

echo
echo "✓ 发布完成"
"$GH" release view "$TAG" --repo "$REPO" --json url,assets \
  --jq '.url, (.assets[] | "  \(.name)  \(.size) bytes  \(.state)")'

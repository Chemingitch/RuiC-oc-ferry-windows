#!/usr/bin/env bash
# 连续多轮启动测试，用于捕捉竞态类问题（如 pywebviewready 时序）
set -u

# 路径自动定位 —— 脚本放哪都能跑，也方便别人 clone 下来直接用
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python}"    # 需要装了 pywebview / pillow 的解释器
BASE="$HERE"
TESTDIR="${OCFERRY_TESTDIR:-/tmp/ocferry-clean-test}"
ROUNDS=${1:-3}

for i in $(seq 1 "$ROUNDS"); do
  echo "########## 第 $i 轮 ##########"
  taskkill //F //IM OC-Ferry-Deployer.exe 2>/dev/null | head -2
  sleep 2
  (cd "$TESTDIR" && cmd //c start "" "OC-Ferry-Deployer.exe")
  sleep 12
  "$PY" "$BASE/shot.py" "OC Ferry Deployer" | tail -1
  cp -f "$BASE/shot.png" "$BASE/round-$i.png"
done

taskkill //F //IM OC-Ferry-Deployer.exe 2>/dev/null | head -2

echo
echo "=== 拼接各轮日志区便于比对 ==="
"$PY" -c "
import os
import sys
from PIL import Image
base = sys.argv[1].rstrip('/') + '/'
crops = []
for i in range(1, $ROUNDS + 1):
    p = base + f'round-{i}.png'
    if not os.path.exists(p): continue
    im = Image.open(p)
    crops.append(im.crop((545, 100, 1050, 270)))
if crops:
    w = crops[0].width
    total = sum(c.height for c in crops) + 10 * (len(crops) - 1)
    canvas = Image.new('RGB', (w, total), (30, 30, 38))
    y = 0
    for c in crops:
        canvas.paste(c, (0, y)); y += c.height + 10
    canvas.save(base + 'round-all.png')
    print('saved round-all.png', canvas.size)
" "$BASE"

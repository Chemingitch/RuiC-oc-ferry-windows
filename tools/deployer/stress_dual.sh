#!/usr/bin/env bash
# 双实例撞车压力测试：从两个不同目录、以随机间隔启动同一程序，
# 用来验证单实例保护是否可靠（这是用户实际遇到的卡死场景）。
set -u

# 路径自动定位 —— 脚本放哪都能跑，也方便别人 clone 下来直接用
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python}"    # 需要装了 pywebview / pillow 的解释器
BASE="$HERE"
D1="${OCFERRY_TESTDIR:-/tmp/ocferry-clean-test}"
D2="$BASE/dist"

N=${1:-8}
BAD=0

# 关键：先把最新构建同步到测试目录。
# （踩过坑：测试目录里的 exe 不更新，会导致整轮测试跑的都是旧版本。）
mkdir -p "$D1"
cp -f "$D2/OC-Ferry-Deployer.exe" "$D1/"

for i in $(seq 1 "$N"); do
  taskkill //F //IM OC-Ferry-Deployer.exe >/dev/null 2>&1
  sleep 2

  (cd "$D1" && cmd //c start "" "OC-Ferry-Deployer.exe")

  # 随机 0.3 ~ 3.0 秒后从另一个目录再撞一次
  DELAY=$(awk -v s=$RANDOM 'BEGIN{srand(s); printf "%.1f", 0.3+rand()*2.7}')
  sleep "$DELAY"
  (cd "$D2" && cmd //c start "" "OC-Ferry-Deployer.exe")

  sleep 11

  CNT=$(tasklist //FI "IMAGENAME eq OC-Ferry-Deployer.exe" //FO CSV 2>/dev/null | tail -n +2 | wc -l)
  R=$("$PY" "$BASE/check_responding.py" 2>&1 | tail -1)

  STATUS="ok"
  if [ "$R" = "HUNG" ]; then STATUS="!! 窗口未响应"; BAD=$((BAD + 1)); fi
  if [ "$CNT" -ne 2 ]; then STATUS="!! 进程数=$CNT（应为2）"; BAD=$((BAD + 1)); fi

  printf "第 %2d 轮  撞车间隔 %ss  进程 %s  窗口 %s  %s\n" "$i" "$DELAY" "$CNT" "$R" "$STATUS"
done

taskkill //F //IM OC-Ferry-Deployer.exe >/dev/null 2>&1

echo
echo "异常轮次: $BAD / $N"

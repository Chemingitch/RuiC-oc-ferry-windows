#!/usr/bin/env bash
# 启动压力测试：反复冷启动并检测窗口响应，卡死时自动留证（截图 + 子进程数）。
#  用法: stress.sh <轮数> [single|dual]
set -u

# 路径自动定位 —— 脚本放哪都能跑，也方便别人 clone 下来直接用
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python}"    # 需要装了 pywebview / pillow 的解释器
BASE="$HERE"
TESTDIR="${OCFERRY_TESTDIR:-/tmp/ocferry-clean-test}"
DIST="$BASE/dist"
N=${1:-10}
MODE=${2:-single}

# 关键：先把最新构建同步到测试目录。
# （踩过坑：测试目录里的 exe 不更新，会导致整轮测试跑的都是旧版本。）
# 硬校验：dist 里没有产物就直接退出。
# （踩过坑：拷贝失败只是打一行 cp 报错，脚本照跑，测的其实是上次剩下的旧 exe。）
[ -f "$DIST/OC-Ferry-Deployer.exe" ] || {
  echo "✗ 找不到 $DIST/OC-Ferry-Deployer.exe —— 先运行 build.py" >&2
  exit 2
}
mkdir -p "$TESTDIR"
cp -f "$DIST/OC-Ferry-Deployer.exe" "$TESTDIR/"

HUNG=0
FAILED=0

for i in $(seq 1 "$N"); do
  taskkill //F //IM OC-Ferry-Deployer.exe >/dev/null 2>&1
  sleep 2

  (cd "$TESTDIR" && cmd //c start "" "OC-Ferry-Deployer.exe")

  TAG=""
  if [ "$MODE" = "dual" ]; then
    DELAY=$(awk -v s=$RANDOM 'BEGIN{srand(s); printf "%.1f", 0.3+rand()*2.7}')
    sleep "$DELAY"
    (cd "$DIST" && cmd //c start "" "OC-Ferry-Deployer.exe")
    TAG="撞车 ${DELAY}s"
  fi

  sleep 9

  R=$("$PY" "$BASE/check_responding.py" 2>&1 | tail -1)
  W=$(tasklist //FI "IMAGENAME eq msedgewebview2.exe" //FO CSV 2>/dev/null | tail -n +2 | wc -l)
  printf "第 %2d 轮  %-11s  webview2子进程 %2d  %s\n" "$i" "$R" "$W" "$TAG"

  case "$R" in
    *HUNG*)
      HUNG=$((HUNG + 1))
      "$PY" "$BASE/shot.py" "OC Ferry Deployer" >/dev/null 2>&1
      cp -f "$BASE/shot.png" "$BASE/hung-$i.png"
      echo "        ^^ 已留证 hung-$i.png"
      ;;
    *NO_WINDOW*)
      FAILED=$((FAILED + 1))
      ;;
  esac
done

taskkill //F //IM OC-Ferry-Deployer.exe >/dev/null 2>&1

echo
echo "结果[$MODE]：未响应 $HUNG 次 / 无窗口 $FAILED 次 / 共 $N 轮"

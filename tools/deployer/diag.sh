#!/usr/bin/env bash
# 卡死诊断：反复冷启动，检测到「未响应」时**不杀进程**，抓齐证据后退出。
#  用法: diag.sh <最大轮数>
set -u

PY="E:/C/CTools/PythonTools/python/python.exe"
BASE="E:/C/CTools/AI Make/OC-Ferry-build/deployer"
TESTDIR="/c/Users/Chemingitch/AppData/Local/Temp/ocferry-clean-test"
TMPDIR_WIN="/c/Users/Chemingitch/AppData/Local/Temp/OC-Ferry-Deployer"
DIST="$BASE/dist"
N=${1:-30}
OUT="$BASE/diag"

export FERRY_TRACE=1

mkdir -p "$OUT" "$TESTDIR"
cp -f "$DIST/OC-Ferry-Deployer.exe" "$TESTDIR/"
rm -f "$TMPDIR_WIN"/trace-*.log "$TMPDIR_WIN"/hb-*.log "$TMPDIR_WIN"/stage-*.log

for i in $(seq 1 "$N"); do
  taskkill //F //IM OC-Ferry-Deployer.exe >/dev/null 2>&1
  sleep 1
  (cd "$TESTDIR" && cmd //c start "" "OC-Ferry-Deployer.exe")

  R=""
  for t in $(seq 1 11); do
    sleep 1
    R=$("$PY" "$BASE/check_responding.py" 2>&1 | tail -1)
    [ "$R" = "RESPONDING" ] || [ "$R" = "HUNG" ] || { R=""; continue; }
    [ "$R" = "HUNG" ] && break
  done

  PID=$(tasklist //FI "IMAGENAME eq OC-Ferry-Deployer.exe" //FO CSV 2>/dev/null | tail -n +2 | head -1 | awk -F'","' '{print $2}')

  if [ "$R" = "HUNG" ]; then
    echo "### 第 $i 轮 卡死  pid=$PID  -> 抓证"
    {
      echo "=== stage ===";  cat "$TMPDIR_WIN/stage-$PID.log" 2>/dev/null
      echo; echo "=== hb 行数（心跳存活秒数）==="; wc -l < "$TMPDIR_WIN/hb-$PID.log" 2>/dev/null
      echo; echo "=== faulthandler 全线程栈 ==="; cat "$TMPDIR_WIN/trace-$PID.log" 2>/dev/null
      echo; echo "=== top-level windows of pid ==="; "$PY" "$BASE/probe_win.py" "$PID" 2>&1
    } > "$OUT/hang-$i.txt"
    "$PY" "$BASE/shot.py" "OC Ferry Deployer" >/dev/null 2>&1
    cp -f "$BASE/shot.png" "$OUT/hang-$i.png"
    echo "### 已留证 $OUT/hang-$i.txt   进程保留未杀。"
    exit 0
  fi

  printf "第 %2d 轮  %s (pid %s)\n" "$i" "${R:-NO_WINDOW}" "$PID"
done

taskkill //F //IM OC-Ferry-Deployer.exe >/dev/null 2>&1
echo "### $N 轮内未复现卡死"

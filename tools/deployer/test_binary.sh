#!/usr/bin/env bash
# 打包产物「干净目录」测试：模拟用户把 exe 拷到别处双击
set -u

PY="E:/C/CTools/PythonTools/python/python.exe"
BASE="E:/C/CTools/AI Make/OC-Ferry-build/deployer"
TESTDIR="/c/Users/Chemingitch/AppData/Local/Temp/ocferry-clean-test"

echo "=== 0. 清理已有实例 ==="
taskkill //F //IM OC-Ferry-Deployer.exe 2>/dev/null | head -3
sleep 2

echo
echo "=== 1. 准备干净测试目录 ==="
mkdir -p "$TESTDIR"
cp -f "$BASE/dist/OC-Ferry-Deployer.exe" "$TESTDIR/"
ls -la "$TESTDIR"

echo
echo "=== 2. 从该目录启动 ==="
cd "$TESTDIR" && cmd //c start "" "OC-Ferry-Deployer.exe"
sleep 15

echo
echo "=== 3. 进程状态 ==="
tasklist //FI "IMAGENAME eq OC-Ferry-Deployer.exe" //FO TABLE 2>/dev/null

echo
echo "=== 4. 窗口截图 ==="
"$PY" "$BASE/shot.py" "OC Ferry Deployer"

echo
echo "=== 5. 任务栏截图 ==="
"$PY" "$BASE/shot_taskbar.py"

echo
echo "=== 6. 单实例验证：再启动一次 ==="
cd "$TESTDIR" && cmd //c start "" "OC-Ferry-Deployer.exe"
sleep 7
echo "进程数应仍为 2（引导 + 应用），不应翻倍："
tasklist //FI "IMAGENAME eq OC-Ferry-Deployer.exe" //FO TABLE 2>/dev/null

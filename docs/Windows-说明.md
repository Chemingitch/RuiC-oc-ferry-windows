# Windows 说明

本 fork 相对上游的改动、以及 Windows 上特有的注意事项。完整功能说明见上游
[README](../README.md)；改动清单见 [NOTICE.md](../NOTICE.md)。

---

## 1. 本 fork 的两个改动

### 最小化到托盘

上游：点最小化 = 缩到任务栏（只有关闭窗口才收进托盘）。
本 fork：最小化、关闭都收进托盘；`Ctrl+M` 或菜单「最小化到托盘」同样效果。
第一次收进托盘会弹一次气泡提示。想真正退出走托盘右键菜单。

### 退出时清理 `opencode-cli.exe` 残留

`opencode-cli.exe` 是 **OpenCode 桌面版**的后台服务，**不是本应用启动的**
（本应用用的是自己托管目录里的 `opencode.exe`）。桌面版如果被异常终止，
它可能留下一个孤儿进程一直占着内存。

退出时本 fork 会扫一遍并清掉这类残留。模式由环境变量控制：

```bat
set "FERRY_KILL_OPENCODE_CLI=orphans"   rem 默认：只清「父进程已退出」的孤儿
set "FERRY_KILL_OPENCODE_CLI=always"    rem 连正在运行的桌面版一起结束
set "FERRY_KILL_OPENCODE_CLI=off"       rem 完全关闭
```

> **关于「权限不足」**：Windows 不允许低权限进程结束高权限进程。如果 OpenCode 桌面版
> 当初是**以管理员身份**启动的，它留下的服务普通权限杀不掉，会回「拒绝访问」。
> 这时本 fork 会**如实记录**这条失败（不会谎报成功），需要清理请在管理员权限下运行：
> `taskkill /IM opencode-cli.exe /F`

---

## 2. OpenCode 运行时的存放规则（Windows 关键）

本应用**不含** OpenCode，需要一份 `opencode.exe`。查找顺序见 `src/runtime.js`
的 `runtimeCandidates()`：

1. 环境变量 `FERRY_OPENCODE_PATH`
2. `%USERPROFILE%\.opencode\bin\opencode.exe`
3. `%APPDATA%\npm\node_modules\opencode-ai\bin\opencode.exe`
4. 托管目录 `<数据目录>\runtime\<版本号>\opencode.exe`
5. 都没有 → 自动从 npm 下载

**找到之后会「复制」一份进托管目录再隔离运行**，所以你的原件放哪都行
（下载文件夹、U 盘、从 rar / 7z 刚解压出来的临时目录都可以），不会被移动或修改。

### 手动预置（免去首次启动下载约 60 MB）

```bash
# 1. 下载（.tgz 即 tar.gz，WinRAR / 7-Zip 都能解）
curl -L -o oc.tgz https://registry.npmmirror.com/opencode-windows-x64/-/opencode-windows-x64-1.19.0.tgz

# 2. 取出 package/bin/opencode.exe
tar -xzf oc.tgz package/bin/opencode.exe

# 3. 放进托管目录：目录名必须等于版本号
#    <数据目录>\runtime\1.19.0\opencode.exe

# 4. 验证：必须输出「裸版本号」，不能带前缀
opencode.exe --version
# 1.19.0
```

### ⚠️ 不能用桌面版自带的 `opencode-cli.exe`

| | `opencode.exe`（官方 npm 包） | `opencode-cli.exe`（桌面版） |
|---|---|---|
| `--version` 输出 | `1.19.0` | `opencode v2.0.25` |
| 被接受 | ✅ | ❌ |

`runtime.js` 用严格正则 `^\d+\.\d+\.\d+(?:-...)?$` 校验版本号，带前缀的一律判为
"unrecognized version output" 而拒绝。

---

## 3. 构建

```bash
npm ci

# 国内网络建议先设镜像（否则 electron 与 electron-builder 的二进制可能拉不下来）
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
set ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/

npm run build:win           # NSIS 安装包（桌面图标 + 开机自启）
npm run build:win:portable  # 便携版（不写注册表、不自启）
```

> `npm ci` 不会自动下载 Electron 二进制。若 `node_modules/electron/dist` 不存在，
> 先跑一次 `node node_modules/electron/install.js`。

### 绿色版启动脚本要注意一件事

从别的 Electron 应用（例如另一个 IDE / 工具）拉起的 shell 里启动本应用时，
环境里可能带着 `ELECTRON_RUN_AS_NODE=1`，那会让 `OC Ferry.exe` **被当成纯 Node 运行**、
窗口起不来（报错形如 `bad option: --enable-logging`）。启动脚本里清掉它：

```bat
set "ELECTRON_RUN_AS_NODE="
set "ELECTRON_NO_ATTACH_CONSOLE="
```

---

## 4. 判定缓存的重试时长

`src/probe-cache.js`：

| 判定 | 有效期 | 常量 |
|---|---|---|
| 通过 | 6 小时 | `DEFAULT_OK_TTL_MINUTES = 360` |
| 超时 / 限流（当时的负载） | 10 分钟 | `DEFAULT_TRANSIENT_TTL_MINUTES = 10` |
| 已下线 / 无权限 / 额度用尽 | 1 小时 | `DEFAULT_REJECT_TTL_MINUTES = 60` |

> 顺带说明一个容易误会的地方：**候选模型是按「价格字段」筛出来的，不是按名字。**
> `freeModels()` 要求 `cost.input/output/cache.read/cache.write` **全为 0**。
> 名字里带 `free` 不算数——例如 `big-pickle` 名字里没有 `free`，但它是免费的；
> 而 `exo-free` 名字里写着 `free`，上游却已经下线它了（目录元数据仍标 `status: active`，
> 属于目录与实际端点不同步，只能在探测阶段才暴露）。

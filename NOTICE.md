# 来源与授权说明 / Attribution & License

## 这是什么

本仓库是 **[HRuiCcc/RuiC-oc-ferry](https://github.com/HRuiCcc/RuiC-oc-ferry)** 的
**非官方 fork**，专注于 Windows 平台的使用体验。

**它不是原项目，也与原作者无隶属关系。** 原作者是 **HRuiCcc**。

## 授权

上游以 **MIT License** 发布：

```
MIT License

Copyright (c) 2026 HRuiCcc
```

MIT 明确授予任何人「使用、复制、修改、合并、发布、分发、再许可和/或销售」本软件的权利，
条件是**在软件的所有副本或实质性部分中保留上述版权声明和本许可声明**。

因此：

- 本仓库的 `LICENSE` 文件**原样保留**，未做任何改动。
- 上游原始版权始终归 HRuiCcc 所有。
- 本 fork 的所有改动同样以 MIT 授权发布。

## 本 fork 相对上游 v0.3.0 的改动

### 1. 最小化到托盘 —— `desktop/main.cjs`

上游：点最小化 = 缩到任务栏（只有关闭窗口才会收进托盘）。

改动：

- 拦截 `minimize` 事件，改为 `hide()` 收进托盘；
- 新增 `hideToTray()`：第一次收进托盘时弹一次气泡提示，避免用户以为程序被关掉；
- 应用菜单新增「最小化到托盘」（快捷键 `Ctrl+M`）；
- `close` 处理器复用 `hideToTray()`，共用同一套提示逻辑。

### 2. 退出时清理 `opencode-cli.exe` 残留 —— `src/opencode-cli-cleanup.js`（新增）+ `src/main.js`

背景：`opencode-cli.exe` 是 **OpenCode 桌面版**的后台服务，**不是本应用启动的**
（本应用用的是自己托管目录里的 `opencode.exe`，镜像名不同，退出时由 `runtime.stop()` 正常结束）。

改动：

- 新增模块 `src/opencode-cli-cleanup.js`，导出 `killLeftoverOpenCodeCli()`；
- 在 `src/main.js` 的 `shutdown()` 中、`runtime.stop()` 之后调用；
- 默认模式 `orphans`：**只清理"父进程已经退出"的孤儿进程**，不会误杀用户正在使用的
  OpenCode 桌面版；通过环境变量 `FERRY_KILL_OPENCODE_CLI` 可切换 `always` / `off`；
- 逐个进程 `try/catch` 分别记账，**不谎报成功**：Windows 上跨权限级别杀进程会返回
  「拒绝访问」（例如桌面版是以管理员身份启动的），这种情况会如实报告并指向提权脚本。

### 3. 部署侧附加（不在本源码仓库内）

- Windows 绿色版启动器（中文 / ASCII 双版本），固定 `FERRY_DATA_DIR` 到本地 `data/`；
- `Clean-OpenCode-Leftover.bat`：提权清理 `opencode-cli.exe` 残留（`fltmc` 判权限 → 自提权）；
- 预置托管运行时 `data/runtime/1.19.0/opencode.exe`，避免首次启动下载约 60 MB。

## 关于原作者的资源

- `assets/wechat-donate.png`（原作者的微信赞赏码）**已从本 fork 移除**，
  README 末尾对应的赞赏段落也已删除。**请通过上游仓库支持原作者。**
- `desktop/icon.png` 与产品名「OC Ferry」沿用上游，仅作标识用途。
  如果你是原作者并希望本 fork 更换名称或图标，请开 Issue，会立即处理。

## 想用这份代码？先考虑回上游

本 fork 的改动（尤其是「最小化到托盘」和「退出清理」）都是**通用改进**，
而且上游 README 把 Windows 列入了支持平台、却只发布了 macOS 构建产物——
Windows 相关改动正是上游缺的那一块。

**推荐顺序：先向上游提 Issue / PR；上游不合并或不活跃，再使用本 fork。**

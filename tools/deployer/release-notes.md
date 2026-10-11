Windows 版 **OC Ferry** 的两个产物：一键部署器，以及它要装的主程序载荷。

- 基于上游 [HRuiCcc/RuiC-oc-ferry](https://github.com/HRuiCcc/RuiC-oc-ferry) `v0.3.0` 构建
- 合入本 fork 的 Windows 改动：**托盘常驻、退出清理、便携数据目录**

## 资产

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `OC-Ferry-Deployer.exe` | {{DEPLOYER_SIZE}} | 一键部署器（推荐） |
| `{{PAYLOAD_NAME}}` | {{PAYLOAD_SIZE}} | 主程序载荷（绿色便携包） |

SHA256：

```
OC-Ferry-Deployer.exe          {{DEPLOYER_SHA256}}
{{PAYLOAD_NAME}}     {{PAYLOAD_SHA256}}
```

## 用法一：一键部署器（推荐）

1. 下载 `OC-Ferry-Deployer.exe`，放到任意位置双击运行。
2. 选一个安装目录（例如 `D:\OC-Ferry`），点「开始部署」。
3. 它会自己完成：检测环境 → 校验位置 → 下载主程序 → 下载并校验 OpenCode 运行时 → 建桌面快捷方式。

整个过程约 1～3 分钟（取决于网速），主程序载荷 151 MB + 运行时 58 MB。

**部署器会做什么**

| 步骤 | 实际动作 |
| --- | --- |
| 检测运行环境 | 读 Windows 版本与 WebView2 版本 |
| 校验部署位置 | 检查可写性与磁盘剩余（要求 ≥ 0.9 GB） |
| 展开 OC Ferry 主程序 | 从本 Release 下载并解压（支持断点续传） |
| 获取 OpenCode 运行时 | 从 npm 官方源下载，按官方 `integrity` 做 **SHA-512 校验** |
| 创建启动入口 | 校验启动脚本 + 建桌面快捷方式 |

覆盖安装时，旧版本会先改名为 `app.old-<时间戳>` 让路，解压失败会自动回滚 ——
不会留下「新旧都不完整」的中间状态。

**关于模型配置**：部署器**不**改你的 WorkBuddy 配置。主程序首次启动时会自己定位并
**原地合并** `models.json`（先备份，绝不碰你自己已有的条目），所以不需要安装器代劳。

## 用法二：手动解压

1. 下载 `{{PAYLOAD_NAME}}`，**完整解压**到任意目录。
   > 必须完整解压：`app\` 是主程序本体，只复制 `OC Ferry.exe` 跑不起来。
2. 双击解压目录里的 **`启动 OC Ferry.bat`**。

## 目录结构（解压后）

```
OC-Ferry/
├─ app/                 主程序（Electron）
│   ├─ OC Ferry.exe
│   └─ resources/app/   源码与依赖
├─ data/                运行时数据，首次启动自动生成
├─ 启动 OC Ferry.bat     启动入口（务必用它启动）
├─ Start OC Ferry.bat   同上，英文版
└─ 快速开始.txt / README.txt
```

## 为什么必须用 `.bat` 启动

启动脚本负责两件事，缺一不可：

1. 把数据目录钉在 `./data` —— 整个文件夹可整体搬迁，删除即干净卸载；
2. 清除父进程可能带入的 `ELECTRON_RUN_AS_NODE` 变量 —— 不清掉的话，
   主程序在某些环境里会被当成纯 Node 运行，窗口永远起不来。

## 运行要求

- Windows 10 / 11 (x64)
- 首次启动需要联网（自动准备隔离的 OpenCode 运行时）
- 界面依赖系统自带的 WebView2 运行时（Win11 与新版 Win10 已内置）

## 网络说明

主程序载荷会依次尝试两条线路：`github.com` 直链，以及 `api.github.com` 的资产端点。
这两个域解析到不同 IP，可达性并不总是同步 —— 实测过 `github.com` 完全不通而
`api.github.com` 仍可用的情形，此时部署器会自动切到备用线路继续。

## 许可

MIT。上游版权归原作者 HRuiCcc 所有，详见仓库中的 `LICENSE` / `NOTICE.md`。

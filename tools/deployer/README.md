# OC Ferry Deployer

Windows 一键部署器 —— 把 OC Ferry 主程序与 OpenCode 运行时装到用户指定的目录，开箱即用。

## 设计目标

| 目标 | 实现方式 |
|---|---|
| 目标机零依赖 | PyInstaller 单文件打包，Python 运行时内嵌，不需要预装 Python / Node |
| 不闪命令窗口 | exe 以 `WINDOWS_GUI` 子系统编译（PE Subsystem=2），系统不分配控制台 |
| 不像 Windows 安装向导 | pywebview + WebView2 无边框窗口，界面 100% 自绘，无任何系统控件 |
| 重复双击不冲突 | Windows 命名 mutex 单实例保护，第二次启动会激活已有窗口并退出 |
| 子进程不留黑框 | 所有 `subprocess` 统一走 `run_hidden()`，固化 `CREATE_NO_WINDOW` |

## 系统要求

| 项目 | 说明 |
|---|---|
| 支持 | **Windows 10 1809+ / Windows 11** |
| 不支持 | **Windows 7 / 8 / 8.1** |
| 运行时依赖 | WebView2 Runtime（Win11 内置；Win10 自 2022 年起随 Edge 预装） |

> **为什么不支持 Win7**：OC Ferry 本体基于 Electron，其现代版本依赖的 Chromium 与
> WebView2 运行时均已放弃 Win7。部署器即使能在 Win7 启动，部署出来的主程序也无法运行，
> 因此不作兼容。

## 目录结构

```
tools/deployer/
├── deployer.py          # 主程序：窗口外壳 + 环境探测 + 部署流程
├── ui/index.html        # 界面：HTML/CSS/JS，暗色科技风
├── gen_icon.py          # 生成 app.ico（双层六边形徽标）
├── app.ico              # 应用图标，含 16/24/32/48/64/128/256 七种尺寸
├── build.py             # PyInstaller 打包脚本
├── check_pe.py          # 读取 PE 头判断子系统（验证「无控制台」）
├── shot.py              # 按窗口标题截图（PrintWindow）
├── shot_taskbar.py      # 抓取屏幕底部任务栏
├── test_api.py          # Python 逻辑层自测（不开窗口）
├── test_binary.sh       # 打包产物集成测试（干净目录 + 单实例）
├── test_loop.sh         # 连续多轮启动测试（用于捕捉竞态）
└── 调试-启动部署器.bat   # 开发态启动脚本
```

## 开发态运行

```bash
pip install pywebview pillow
python deployer.py
```

开发态用 `python.exe` 启动**会**附带控制台窗口（那是解释器自带的）；
想避免可改用同目录的 `pythonw.exe`。

## 打包

```bash
python build.py
# 产物：dist/OC-Ferry-Deployer.exe（约 13.5 MB）
```

关键参数：

```
--onefile     单文件分发
--noconsole    GUI 子系统：不创建控制台
--icon         app.ico
--add-data     ui;ui
--collect-all  webview / clr_loader
```

## 实现上踩过的坑

1. **`pywebviewready` 存在竞态**
   pywebview 注入 `window.pywebview` 的时机与页面脚本注册监听的时机在赛跑。
   若注入先完成，事件会在监听器注册前派发完毕，监听器永远等不到（实测复现过两次）。
   现在界面同时挂**事件监听**与**轮询兜底**，谁先到用谁。见 `ui/index.html`。

2. **子进程会闪黑框**
   主程序是 GUI 的，但它调用的 `opencode.exe`、解压、PowerShell 都是控制台程序。
   必须统一在 `subprocess` 上加 `creationflags=CREATE_NO_WINDOW (0x08000000)`，
   否则部署过程中屏幕会连续闪黑框。

3. **opencode 版本号必须严格匹配**
   上游 `src/runtime.js` 用 `^\d+\.\d+\.\d+` 校验版本，
   桌面版 `opencode-cli.exe --version` 输出 `opencode v2.0.25`（带前缀）会被拒绝，
   必须用官方 npm 包 `opencode-windows-x64`（输出裸 `1.19.0`）。

4. **`DOMContentLoaded` 不是调用后端 API 的时机**
   该时刻 `window.pywebview.api` 尚未注入，调用会静默失败。
   所有后端调用都应等后端就绪后再发起。

## 测试状态

| 层级 | 覆盖内容 | 结果 |
|---|---|---|
| Python 逻辑 | 环境探测 / WebView2 查询 / 目录可写性 / 路径解析，共 10 项 | 通过 |
| 打包产物 | 干净目录独立运行、PE 子系统 = `WINDOWS_GUI`、任务栏图标 | 通过 |
| 集成 | 连续 3 轮冷启动、单实例保护、前后端连通 | 通过 |

> **当前进度**：界面骨架、打包、运行环境适配已完成并验证。
> 部署流程中的「下载 OpenCode 运行时」「展开主程序」「写入配置」三步尚未接入真实逻辑，
> 界面中标记为 *待接入*。

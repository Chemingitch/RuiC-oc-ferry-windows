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
├── netfetch.py          # 下载 / 断点续传 / SHA-512 校验 / 安全解压（纯标准库）
├── sources.py           # 源解析：GitHub Release（主程序）与 npm registry（运行时）
├── ui/index.html        # 界面：HTML/CSS/JS，暗色科技风
├── payload/             # 随主程序一起分发的附加文件（启动脚本、快速开始）
├── gen_payload.py       # 生成 payload/ 内容（GBK+CRLF，见下文「批处理编码」）
├── gen_icon.py          # 生成 app.ico（双层六边形徽标）
├── app.ico              # 应用图标，含 16/24/32/48/64/128/256 七种尺寸
├── build.py             # PyInstaller 打包部署器 exe
├── pack_payload.py      # 打包主程序载荷 zip（app/ + payload/）
├── publish-release.sh   # 把载荷 zip 发到 GitHub Release（自动带 sha256）
├── smoke_payload.py     # 载荷冒烟测试：解压 → 真实启动 → 判定窗口响应
├── check_pe.py          # 读取 PE 头判断子系统（验证「无控制台」）
├── check_responding.py  # 判断窗口是否「未响应」（SendMessageTimeout WM_NULL）
├── shot.py              # 按窗口标题截图（PrintWindow）
├── shot_taskbar.py      # 抓取屏幕底部任务栏
├── probe_win.py         # 列出某个 PID 的全部顶层窗口（排查隐藏模态框）
├── test_api.py          # Python 逻辑层自测（20 项，不开窗口）
├── e2e_test.py          # 端到端部署测试（可加 --live 真走网络）
├── test_binary.sh       # 打包产物集成测试（干净目录 + 单实例）
├── test_loop.sh         # 连续多轮启动测试（用于捕捉竞态）
├── stress.sh            # 压力测试：反复冷启动，卡死自动留证
├── stress_dual.sh       # 双实例撞车压力测试
├── diag.sh              # 卡死取证：抓全线程栈 + 阶段标记 + 窗口枚举
└── 调试-启动部署器.bat   # 开发态启动脚本
```

> 所有 `*.sh` 都是**路径自定位**的（按脚本自身位置推导 `BASE`，测试目录落在系统临时目录），
> clone 下来即可直接跑。两个可用环境变量覆盖默认值：
> `PYTHON`（默认 `python`，需装有 pywebview / pillow）、`OCFERRY_TESTDIR`（默认 `/tmp/ocferry-clean-test`）。

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

`build.py` 用**当前正在运行它的解释器**去调 PyInstaller，所以要先用同一个解释器装好：
`pip install pyinstaller`。想指定别的解释器就 `PYTHON=/path/to/python.exe python build.py`。

关键参数：

```
--onefile     单文件分发
--noconsole    GUI 子系统：不创建控制台
--icon         app.ico
--add-data     ui;ui
--collect-all  webview / clr_loader
```

## 实现上踩过的坑

1. **【最狠的一个】给 `js_api` 挂框架对象 = 窗口必然「未响应」**

   现象：窗口偶发卡死，标题出现「(未响应)」，任务管理器里进程还在、
   WebView2 子进程数量正常，但界面定格在最后一帧。
   实测在 20 轮冷启动里能中 1 次，看起来像 5% 的随机竞态。

   真相是 **100% 会走进死路，只是卡不卡取决于 COM 调用的时序**。
   链条如下：

   ```
   pywebview 在页面加载完后，会在「注入线程」里跑
     webview/util.py: inject_pywebview() -> generate_func() -> get_functions()
   get_functions() 会 for name in dir(obj) 逐个 getattr，
   并把「非 callable 且有 __module__」的属性【递归】展开成 JS 可调函数清单。

   我们原来的 Api 类里有 self.window = <pywebview Window>
     -> get_functions 递归进 Window
       -> Window.native（winforms.py:195 里被赋成了 WinForms 的 BrowserForm！）
         -> 递归进整个 .NET/COM 对象图：
              BrowserForm.AccessibilityObject.Bounds.Empty.Ceiling ...
              一路读到 CoreWebView2 / CanGoBack / get_AllowExternalDrop 这些 COM 属性
   ```

   探针实测日志直接膨胀到 **41927 行**，里面成片是这样的栈：

   ```
   → getattr(api.window.native.AccessibilityObject)      [宿主 BrowserForm]
     → getattr(...AccessibilityObject.Bounds)            [宿主 ControlAccessibleObject]
       → getattr(...Bounds.Empty.Ceiling)                [宿主 Rectangle]
   System.StubHelpers.StubHelpers.GetCOMIPFromRCW(...)
   Microsoft.Web.WebView2.WinForms.WebView2.get_CanGoBack()
   ```

   而 `Window` 上还有一批**会阻塞的 property**：

   ```python
   @property
   def width(self):  self.events.shown.wait(15); ...   # height / x / y 同理
   ```

   从**后台线程**去跨套间读 WinForms/WebView2 的 COM 属性，一旦撞上忙着的 STA
   线程就会挂住；而挂住时**持有 GIL**，于是：

   * 注入线程卡死在 `util.py:196 in get_functions`
   * 心跳线程停摆（拿不到 GIL）
   * WinForms 的 `app.Run()` 停泵 → 窗口变「未响应」
   * `PrintWindow` 只能抓到最后一帧，所以截图看起来"界面是好的，就是不动了"

   用内置 `faulthandler` 每 5 秒 dump 全线程栈，10 秒内稳定复现完整现场。

   **修复（双保险，见 `deployer.py` 的 `Api` 类）**：

   1. 内部引用一律下划线开头（`self._window`）——`get_functions` 会跳过 `_` 前缀；
   2. 显式实现 `__dir__`，只返回 5 个真正要给 JS 调的方法：

      ```python
      JS_METHODS = ("env_info", "pick_directory", "minimize", "quit_app", "start_deploy")
      def __dir__(self): return list(self.JS_METHODS)
      ```

      `get_functions` 用 `dir(obj)` 遍历，所以这样它**完全不递归**，
      以后往 `Api` 里再加属性也不可能重蹈覆辙。

   修复后 30 轮冷启动 30/30 全部响应。

2. **`pywebviewready` 存在竞态**
   pywebview 注入 `window.pywebview` 的时机与页面脚本注册监听的时机在赛跑。
   若注入先完成，事件会在监听器注册前派发完毕，监听器永远等不到（实测复现过两次）。
   现在界面同时挂**事件监听**与**轮询兜底**，谁先到用谁。见 `ui/index.html`。

3. **子进程会闪黑框**
   主程序是 GUI 的，但它调用的 `opencode.exe`、解压、PowerShell 都是控制台程序。
   必须统一在 `subprocess` 上加 `creationflags=CREATE_NO_WINDOW (0x08000000)`，
   否则部署过程中屏幕会连续闪黑框。

4. **opencode 版本号必须严格匹配**
   上游 `src/runtime.js` 用 `^\d+\.\d+\.\d+` 校验版本，
   桌面版 `opencode-cli.exe --version` 输出 `opencode v2.0.25`（带前缀）会被拒绝，
   必须用官方 npm 包 `opencode-windows-x64`（输出裸 `1.19.0`）。

5. **`DOMContentLoaded` 不是调用后端 API 的时机**
   该时刻 `window.pywebview.api` 尚未注入，调用会静默失败。
   所有后端调用都应等后端就绪后再发起。

## 诊断开关（正式产物零开销）

设环境变量 `FERRY_TRACE` 启动，产物会写到 `%TEMP%\OC-Ferry-Deployer\`：

| 值 | 行为 |
|---|---|
| `1` | `trace-<pid>.log` 每 5 秒 dump 全部线程的 Python 栈；`hb-<pid>.log` 每秒一行心跳；`stage-<pid>.log` 启动阶段标记 |
| `2` | 在 `1` 的基础上再跑「内省探针」：把 `js_api` 的对象图逐条遍历并打日志 |

判读要点：

* 心跳**停摆** + 窗口未响应 ⇒ GIL 被某个线程占死，去看 `trace` 里哪个线程没动
* 心跳**正常** + 窗口未响应 ⇒ 纯粹是 UI 线程自己不泵消息
* 「内省探针」日志里**下一个 `getattr`** 就是卡死元凶

配套脚本：`diag.sh`（自动复现 + 抓证）、`check_responding.py`（判定响应性）、
`probe_win.py`（枚举该进程全部顶层窗口，用于排除隐藏模态框）。

## 部署流程

| # | 步骤 | 实际动作 |
|---|---|---|
| 0 | 检测运行环境 | 读 Windows 版本与 WebView2 版本（三个注册表探针） |
| 1 | 校验部署位置 | 真探测可写性 + 真算磁盘剩余，要求 ≥ 0.9 GB |
| 2 | 展开 OC Ferry 主程序 | 查 GitHub Release → 下载 zip（可续传）→ 让路旧 `app/` → 解压 513 个文件 |
| 3 | 获取 OpenCode 运行时 | 查 npm registry（官方源优先、镜像兜底）→ 下载 → **SHA-512 校验** → 只取出 `opencode.exe` |
| 4 | 创建启动入口 | 校验启动脚本 + 建桌面快捷方式 |

> **为什么没有「写入模型配置」这一步**：主程序自己做，而且做得更完整 ——
> `src/sync.js` 会**原地合并** WorkBuddy 的 `models.json`（先备份、绝不碰用户自己的条目），
> Windows 上还会用 `config-finder.js` 自动搜索配置文件位置。
> 安装器再实现一遍是重复劳动，还要额外承担改动用户配置数据的风险。

### 关键取舍

* **让路而非覆盖**：目标已有 `app/` 时，先整体改名为 `app.old-<时间戳>` 再解压新的；
  一旦解压失败立刻改名回滚。直接覆盖写会留下「既没有新版本、也没有完整老版本」的中间态。
* **两级校验**：运行时按 npm 官方元数据的 `integrity` 做 SHA-512；主程序解压时由
  `zipfile` 逐条目校验 CRC32，并带 zip-slip 路径穿越防护。
* **代理坏了必须能直连**：先跟随环境变量代理，失败立刻退直连 —— 本机就常年挂着一个
  指向 `127.0.0.1:7890` 的失效代理。

## 测试状态

| 层级 | 覆盖内容 | 结果 |
|---|---|---|
| Python 逻辑 | 环境探测 / WebView2 / 目录可写性 / 路径解析 / `js_api` 暴露面回归防护 / zip-slip 防护 / 解压往返 / 进度节流，共 20 项 | **20/20 通过** |
| 打包产物 | 干净目录独立运行、PE 子系统 = `WINDOWS_GUI`、任务栏图标 | 通过 |
| 集成 · 连通性 | 连续 3 轮冷启动、单实例保护、前后端连通 | 通过 |
| 集成 · 稳定性 | 连续 30 轮冷启动，逐轮 `SendMessageTimeout` 判定响应性 | **30/30 响应** |
| 端到端 · 本地源 | 全新安装 + 覆盖安装两条路径，产物齐备、中间目录清理干净 | 通过 |
| 端到端 · 真实网络 | GitHub Release 下 151.4 MB + npm 下 57.5 MB + SHA-512 校验 + 展开 513 文件 | **79.1 秒跑通** |
| 载荷冒烟 | 压缩包解压后经 `.bat` 启动，窗口判定为「响应」 | 通过 |

## 部署相关环境变量

正式产物不需要设置任何变量；下面这些是留给自测和私有镜像的。

| 变量 | 作用 |
|---|---|
| `FERRY_PAYLOAD_URL` | 覆盖主程序载荷地址（可指向本地文件，避免每次真下 150 MB） |
| `FERRY_OPENCODE_TARBALL` | 覆盖 OpenCode 运行时 tgz 地址 |
| `FERRY_PAYLOAD_SHA256` | 预留：对载荷做完整 sha256 校验（默认由 zip 的 CRC32 兜底） |
| `FERRY_NO_SHORTCUT=1` | 跳过创建桌面快捷方式（自动化测试用） |
| `FERRY_KEEP_OLD=1` | 覆盖安装时保留旧版本备份 `app.old-*`，便于回滚 |

## 发布链路

```bash
# 1) 打包部署器 exe
python build.py                        # → dist/OC-Ferry-Deployer.exe

# 2) 打包主程序载荷（app/ + payload/ → zip）
python pack_payload.py <OC-Ferry的app目录> ../release/OC-Ferry-0.3.0-win-x64.zip \
    --extra-dir payload

# 3) 发布前先验压缩包本身能跑
python smoke_payload.py ../release/OC-Ferry-0.3.0-win-x64.zip /tmp/smoke --via-bat

# 4) 发到 GitHub Release（自动算 sha256/大小填进 notes，正文取自 release-notes.md）
GH=/path/to/gh ./publish-release.sh ../release/OC-Ferry-0.3.0-win-x64.zip \
    v0.3.0-win dist/OC-Ferry-Deployer.exe

# 5) 端到端验收：跑完整部署，再验证装出来的目录能启动
python e2e_test.py /tmp/installed --live
python smoke_payload.py /tmp/installed --reuse
```

第 4 步的说明正文在 `release-notes.md`，用 `{{PAYLOAD_SHA256}}` 这类占位符 ——
文件名、大小、校验值都由脚本现算，避免手填写错；而部署器正是按「资产名」去
下载的，名字一旦对不上就拉不到包。

### 网络受限时怎么推送

某些网络下 `github.com:443` 会间歇性不可达，但 `api.github.com` 仍然通（两者解析
到不同 IP）。这时 `git push` 会失败，而仓库内容其实可以走 Git Data API 上传：
blob → tree → commit → 更新 ref，并原样带上本地的 author/committer/message，
算出来的 commit sha 与本地完全一致，历史不会分叉。

一个容易踩的坑：**不要用 `git ls-files` 或直接读工作区文件来取内容** ——
那是最终状态，拿它去建中间 commit 会把后续提交的内容一起塞进去，两个 commit
会被压成同一个 tree。必须用 `git show <sha>:<path>` 取**那个 commit 当时**的版本。

### 批处理编码

`payload/` 里的 `.bat` 必须是 **GBK(cp936) + CRLF**。cmd.exe 遇到 UTF-8 BOM 会把
`\ufeff` 塞进首行，使 `@echo off` 直接失效；LF 换行对括号块和标签的解析也不可靠。
所以这些文件不手写，用 `gen_payload.py` 统一生成（它顺带保证文档里不含本机路径）。

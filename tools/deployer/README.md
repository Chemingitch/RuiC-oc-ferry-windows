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
├── check_responding.py  # 判断窗口是否「未响应」（SendMessageTimeout WM_NULL）
├── shot.py              # 按窗口标题截图（PrintWindow）
├── shot_taskbar.py      # 抓取屏幕底部任务栏
├── probe_win.py         # 列出某个 PID 的全部顶层窗口（排查隐藏模态框）
├── test_api.py          # Python 逻辑层自测（不开窗口）
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

## 测试状态

| 层级 | 覆盖内容 | 结果 |
|---|---|---|
| Python 逻辑 | 环境探测 / WebView2 查询 / 目录可写性 / 路径解析 / `js_api` 暴露面回归防护，共 13 项 | 通过 |
| 打包产物 | 干净目录独立运行、PE 子系统 = `WINDOWS_GUI`、任务栏图标 | 通过 |
| 集成 · 连通性 | 连续 3 轮冷启动、单实例保护、前后端连通（日志出现「后端已连接」） | 通过 |
| 集成 · 稳定性 | 连续 30 轮冷启动，逐轮 `SendMessageTimeout` 判定响应性 | **30/30 响应，0 次卡死** |

> **当前进度**：界面骨架、打包、运行环境适配、稳定性已完成并验证。
> 部署流程中的「下载 OpenCode 运行时」「展开主程序」「写入配置」三步尚未接入真实逻辑，
> 界面中标记为 *待接入*。

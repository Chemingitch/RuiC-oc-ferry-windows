import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const exec = promisify(execFile);

// 退出时收拾 OpenCode CLI 的残留进程。
//
// 为什么需要区分模式：`opencode-cli.exe` **不是本应用拉起来的**——那是 OpenCode
// 桌面版的后台服务；本应用用的是自己托管目录里的 `opencode.exe`（镜像名不同，退出时
// 由 runtime.stop() 正常结束）。所以默认只收拾"父进程已经不在了"的孤儿，避免把用户
// 正在使用的桌面版一起掐掉。
//
//   FERRY_KILL_OPENCODE_CLI=orphans  （默认）只清理孤儿进程
//   FERRY_KILL_OPENCODE_CLI=always   连正在运行的桌面版一起结束
//   FERRY_KILL_OPENCODE_CLI=off      完全关闭这个行为
//
// 注意：Windows 上**跨权限级别杀进程会「拒绝访问」**。如果 OpenCode 桌面版是以管理员
// 身份启动的，它留下的服务本应用（普通权限）就收不掉——这时如实报告，指向随包的
// `Clean-OpenCode-Leftover.bat`（会请求一次 UAC）。
export async function killLeftoverOpenCodeCli(writeLog = () => {}) {
  if (process.platform !== 'win32') return { ok: [], blocked: [] };
  const mode = String(process.env.FERRY_KILL_OPENCODE_CLI || 'orphans').toLowerCase();
  if (mode === 'off') return { ok: [], blocked: [] };

  const select = 'Get-CimInstance Win32_Process -Filter "Name=\'opencode-cli.exe\'"';
  const scoped = mode === 'always'
    ? select
    : `${select} | Where-Object { -not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue) }`;
  // 逐个尝试并分别记账：一个杀不掉（权限不足）不能连累其余，也不能谎报成功。
  const script = [
    `$targets = ${scoped}`,
    '$ok = @(); $blocked = @()',
    'foreach ($t in $targets) {',
    '  try { Stop-Process -Id $t.ProcessId -Force -ErrorAction Stop; $ok += [int]$t.ProcessId }',
    '  catch { $blocked += [int]$t.ProcessId }',
    '}',
    '@{ ok = @($ok); blocked = @($blocked) } | ConvertTo-Json -Compress',
  ].join('\n');

  try {
    const { stdout } = await exec('powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
      { windowsHide: true, timeout: 15000 });
    const text = String(stdout).trim();
    const parsed = text ? JSON.parse(text) : {};
    const ok = [].concat(parsed.ok ?? []).filter(Number.isInteger);
    const blocked = [].concat(parsed.blocked ?? []).filter(Number.isInteger);
    if (ok.length) writeLog(`已结束 OpenCode CLI 残留进程：${ok.join(', ')}（模式 ${mode}）`);
    if (blocked.length) writeLog(`OpenCode CLI 残留进程 ${blocked.join(', ')} 权限不足未能结束——它由管理员权限启动；`
      + '需要清理请右键以管理员身份运行 OC-Ferry 目录下的 Clean-OpenCode-Leftover.bat');
    return { ok, blocked };
  } catch (error) {
    // 清理失败不该拖住退出流程：记一笔就够了。
    writeLog(`清理 OpenCode CLI 残留失败：${error.message}`);
    return { ok: [], blocked: [] };
  }
}

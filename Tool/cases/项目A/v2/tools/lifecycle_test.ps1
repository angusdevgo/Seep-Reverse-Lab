# lifecycle_test.ps1 — 通过反射调用 SeepTool.exe 内置模块，验证 <项目A> 双向生命周期
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File .\lifecycle_test.ps1
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Xaml

$root = 'C:\Users\Developer\Desktop\pi\seep\project\Seep-TooL'
$exe  = Join-Path $root 'SeepTool.exe'
$dir  = 'D:\Data\<项目A>'
$XY   = Join-Path $dir '<项目A>.exe'

Write-Host "=== 加载 SeepTool.exe 程序集 ==="
$asm = [Reflection.Assembly]::LoadFrom($exe)
$mod = $asm.GetType('Seep.Modules.XYplorerModule')
if ($null -eq $mod) { Write-Host "[-] 未找到<项目A>授权模块"; exit 1 }
Write-Host "[+] 已加载: $($mod.FullName)"

function NewLog { New-Object 'System.Collections.Generic.List[string]' }
function Show($l) { foreach ($x in $l) { Write-Host "    $x" } }

# ── 阶段 0: 基线（官方纯净态） ──
Write-Host "`n=== 阶段 0: 基线检测（应为 original） ==="
$l0 = NewLog
$st0 = $mod.GetMethod('CheckState').Invoke($null, @($dir, $l0))
Show $l0
Write-Host "    状态 = $st0"

# ── 阶段 1: 部署 ──
Write-Host "`n=== 阶段 1: DeployProxy（自定义授权信息） ==="
$l1 = NewLog
$ok1 = $mod.GetMethod('DeployProxy').Invoke($null, @($dir, 'Seep 授权用户', 'license@seep.local', 'xy05-Lifetime-License-Pro-Seep-2026', $l1))
Show $l1
Write-Host "    部署结果 = $ok1"
$dllOk = Test-Path (Join-Path $dir 'version.dll')
$iniOk = Test-Path (Join-Path $dir 'xyplorer_patch.ini')
Write-Host "    version.dll = $dllOk | xyplorer_patch.ini = $iniOk"
if (-not $dllOk -or -not $iniOk) { Write-Host "[-] 部署失败，终止"; exit 1 }

# ── 阶段 2: 检测状态 ──
Write-Host "`n=== 阶段 2: CheckState（应为 patched） ==="
$l2 = NewLog
$st2 = $mod.GetMethod('CheckState').Invoke($null, @($dir, $l2))
Show $l2
Write-Host "    状态 = $st2"

# ── 阶段 3: 启动验证 ──
Write-Host "`n=== 阶段 3: 启动 <项目A> 验证激活效果 ==="
Get-Process <项目A> -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2
$p = Start-Process -FilePath $XY -WorkingDirectory $dir -PassThru
Start-Sleep 14

$sig = @'
using System; using System.Text; using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern int GetWindowTextLengthW(IntPtr h);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, int n, out IntPtr r);
  delegate bool EnumProc(IntPtr h, IntPtr l);
  public static string Title(int pid) {
    string res = "(none)";
    EnumWindows((h,l) => {
      uint p; GetWindowThreadProcessId(h, out p);
      if (p == pid && IsWindowVisible(h)) {
        int n = GetWindowTextLengthW(h);
        var sb = new StringBuilder(n+2); GetWindowTextW(h, sb, n+2);
        string t = sb.ToString();
        if (t.Contains("<项目A>") && n > 20) res = t;
      } return true; }, IntPtr.Zero);
    return res;
  }
  public static byte[] Rd(int pid, long addr, int n) {
    var h = OpenProcess(0x0410, false, pid); var b = new byte[n]; IntPtr r;
    ReadProcessMemory(h, (IntPtr)addr, b, n, out r); return b;
  }
  public static string Wide(int pid, long addr, int n) {
    var b = Rd(pid, addr, n); return Encoding.Unicode.GetString(b).Split('\0')[0];
  }
  public static uint Dword(int pid, long addr) { return BitConverter.ToUInt32(Rd(pid, addr, 4), 0); }
  public static long Qword(int pid, long addr) { return BitConverter.ToInt64(Rd(pid, addr, 8), 0); }
}
'@
if (-not ('W' -as [type])) { Add-Type -TypeDefinition $sig }

$pid2 = $p.Id
$base = 0x140000000
Write-Host "    标题栏  : $([W]::Title($pid2))"
Write-Host "    license_type = $([W]::Dword($pid2, $base + 0x22FD724))"
$namePtr  = [W]::Qword($pid2, $base + 0x2235A88)
$code1Ptr = [W]::Qword($pid2, $base + 0x2281C70)
Write-Host "    name  = '$([W]::Wide($pid2, $namePtr, 200))'"
Write-Host "    code1 = '$([W]::Wide($pid2, $code1Ptr, 200))'"

# ── 阶段 4: 稳定性（60s） ──
Write-Host "`n=== 阶段 4: 稳定性观察 60 秒 ==="
$crashed = $false
for ($i = 0; $i -lt 12; $i++) {
    Start-Sleep 5
    $q = Get-Process -Id $pid2 -ErrorAction SilentlyContinue
    if ($null -eq $q) { Write-Host "    !! 进程在 $((($i+1)*5)) 秒时消失"; $crashed = $true; break }
}
if (-not $crashed) { Write-Host "    [+] 60 秒稳定运行，无崩溃" }
Get-Process <项目A> -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 3

# ── 阶段 5: 还原 ──
Write-Host "`n=== 阶段 5: RemoveProxy（彻底还原官方原版） ==="
$l5 = NewLog
$ok5 = $mod.GetMethod('RemoveProxy').Invoke($null, @($dir, $l5))
Show $l5
Write-Host "    还原结果 = $ok5"

# ── 阶段 6: 还原后校验 ──
Write-Host "`n=== 阶段 6: 还原后校验（应为 original + 无残留） ==="
$dllLeft = Test-Path (Join-Path $dir 'version.dll')
$iniLeft = Test-Path (Join-Path $dir 'xyplorer_patch.ini')
$logLeft = Test-Path (Join-Path $dir 'version_poc.log')
Write-Host "    version.dll 残留 = $dllLeft | xyplorer_patch.ini 残留 = $iniLeft | 日志残留 = $logLeft"
$l6 = NewLog
$st6 = $mod.GetMethod('CheckState').Invoke($null, @($dir, $l6))
Show $l6
Write-Host "    状态 = $st6"

# ── 阶段 7: 还原后启动（试用态回归） ──
Write-Host "`n=== 阶段 7: 还原后启动，确认回落官方试用态 ==="
$p7 = Start-Process -FilePath $XY -WorkingDirectory $dir -PassThru
Start-Sleep 12
$t7 = [W]::Title($p7.Id)
Write-Host "    标题栏  : $t7"
Write-Host "    license_type = $([W]::Dword($p7.Id, 0x140000000 + 0x22FD724))"
Get-Process <项目A> -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "`n================ 生命周期验收汇总 ================"
Write-Host "  阶段1 部署        : $ok1"
Write-Host "  阶段2 状态=patched: $st2"
Write-Host "  阶段5 还原        : $ok5"
Write-Host "  阶段6 无残留      : $((-not $dllLeft) -and (-not $iniLeft) -and (-not $logLeft))"
Write-Host "  阶段6 状态        : $st6"

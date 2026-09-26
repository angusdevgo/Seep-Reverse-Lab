# Run one <项目A> case: start, wait, screenshot, dump key globals, optionally kill.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File run_case.ps1 -Exe <path> -Tag baseline [-Args '...'] [-WaitSec 15] [-Kill]
param(
  [Parameter(Mandatory=$true)][string]$Exe,
  [Parameter(Mandatory=$true)][string]$Tag,
  [string]$Args = "",
  [int]$WaitSec = 15,
  [string]$LogDir = "logs",
  [switch]$Kill,
  [string]$Rvas = "0x22E4D5C,0x22E8D44,0x22F434A,0x22694A0,0x21E52F0,0x221CEF8,0x265E408"
)
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace R -Name M -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int a, bool b, int p);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, int s, out IntPtr r);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
"@

$exePath = (Resolve-Path $Exe).Path
$exeDir = Split-Path $exePath -Parent
$exeName = Split-Path $exePath -Leaf
Write-Output "=== CASE $Tag : $exePath"
Write-Output ("DLL-PRESENT=" + (Test-Path (Join-Path $exeDir 'version.dll')))
if ($Args -ne "") { Write-Output "ARGS=$Args"; $p = Start-Process -FilePath $exePath -ArgumentList $Args -WorkingDirectory $exeDir -PassThru }
else { $p = Start-Process -FilePath $exePath -WorkingDirectory $exeDir -PassThru }
Start-Sleep -Seconds $WaitSec
$p.Refresh()
if ($p.HasExited) { Write-Output ("PROCESS EXITED code=" + $p.ExitCode); exit 1 }
Write-Output ("PID=" + $p.Id)

$base = $p.Modules[0].BaseAddress.ToInt64()
$h = [R.M]::OpenProcess(0x0410, $false, $p.Id)
if ($h -ne [IntPtr]::Zero) {
  foreach ($r in $Rvas.Split(',')) {
    $rva = [Convert]::ToInt64($r.Trim(), 16)
    $buf = New-Object byte[] 8
    $rd = [IntPtr]::Zero
    if ([R.M]::ReadProcessMemory($h, [IntPtr]($base + $rva), $buf, 8, [ref]$rd)) {
      Write-Output ("RVA 0x{0:X7} dword={1} qword=0x{2:X16}" -f $rva, [BitConverter]::ToUInt32($buf,0), [BitConverter]::ToUInt64($buf,0))
    } else { Write-Output ("RVA 0x{0:X7} READ-FAIL" -f $rva) }
  }
  [R.M]::CloseHandle($h) | Out-Null
}

Add-Type -Namespace R2 -Name W -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
"@
function Activate-Main {
  param([int]$ProcId)
  $script:best = [IntPtr]::Zero
  $cb = [R2.W+EnumWindowsProc]{
    param($h, $l)
    $pp = 0
    [R2.W]::GetWindowThreadProcessId($h, [ref]$pp) | Out-Null
    if ($pp -eq $ProcId -and [R2.W]::IsWindowVisible($h)) {
      $sb = New-Object System.Text.StringBuilder 512
      [R2.W]::GetWindowText($h, $sb, 512) | Out-Null
      if ($sb.ToString() -like "*<项目A>*") { $script:best = $h }
    }
    return $true
  }
  [R2.W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
  if ($script:best -ne [IntPtr]::Zero) {
    [R2.W]::ShowWindow($script:best, 9) | Out-Null
    [R2.W]::BringWindowToTop($script:best) | Out-Null
    [R2.W]::SetForegroundWindow($script:best) | Out-Null
    Start-Sleep -Milliseconds 900
    Write-Output ("ACTIVATED 0x{0:X}" -f $script:best.ToInt64())
  } else { Write-Output "NO <项目A> WINDOW" }
}
Activate-Main -ProcId $p.Id

$out = Join-Path $LogDir ("case_" + $Tag + ".png")
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output "SCREENSHOT $out"
$g.Dispose(); $bmp.Dispose()
if ($Kill) { $p | Stop-Process -Force -ErrorAction SilentlyContinue; Write-Output "KILLED" }
else { Write-Output ("RUNNING pid=" + $p.Id) }

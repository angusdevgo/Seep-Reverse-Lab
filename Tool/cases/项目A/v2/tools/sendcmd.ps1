# Send WM_COMMAND to <项目A> main window and capture resulting windows.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File sendcmd.ps1 -CmdId 218 [-Exe lab\v2830\<项目A>.exe] [-Tag cmd218]
param(
  [Parameter(Mandatory=$true)][int]$CmdId,
  [string]$Exe = "lab\v2830\<项目A>.exe",
  [string]$Tag = "cmd",
  [int]$WaitSec = 20,
  [string]$LogDir = "logs"
)
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace C2 -Name W -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
"@
$exePath = (Resolve-Path $Exe).Path
$dir = Split-Path $exePath -Parent
$p = Start-Process -FilePath $exePath -WorkingDirectory $dir -PassThru
Start-Sleep -Seconds $WaitSec
$p.Refresh()
if ($p.HasExited) { Write-Output ("EXITED " + $p.ExitCode); exit 1 }
$ProcId = $p.Id
$script:best = [IntPtr]::Zero; $script:area = 0
$cb = [C2.W+EnumWindowsProc]{
  param($h, $l)
  $pp = 0
  [C2.W]::GetWindowThreadProcessId($h, [ref]$pp) | Out-Null
  if ($pp -eq $ProcId -and [C2.W]::IsWindowVisible($h)) {
    $r = New-Object C2.W+RECT
    [C2.W]::GetWindowRect($h, [ref]$r) | Out-Null
    $a = ($r.R - $r.L) * ($r.B - $r.T)
    if ($a -gt $script:area) { $script:area = $a; $script:best = $h }
  }
  return $true
}
[C2.W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($script:best -eq [IntPtr]::Zero) { Write-Output "NO WINDOW"; exit 1 }
Write-Output ("MAIN 0x{0:X}" -f $script:best.ToInt64())
[C2.W]::PostMessage($script:best, 0x111, [IntPtr]$CmdId, [IntPtr]::Zero) | Out-Null
Write-Output ("POSTED WM_COMMAND " + $CmdId)
Start-Sleep -Seconds 4
& (Join-Path $PSScriptRoot "shot_windows.ps1") -TargetPid $ProcId -Tag $Tag -LogDir $LogDir
Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue
Write-Output "KILLED"

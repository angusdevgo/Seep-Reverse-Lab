# Verify the PoC DLL: start target, read license state, read window title, optionally trigger dialog.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File verify_dll.ps1 -Exe lab\v2840\<项目A>.exe [-CmdId 218] [-Tag v2840]
param(
  [Parameter(Mandatory=$true)][string]$Exe,
  [string]$Tag = "verify",
  [int]$WaitSec = 20,
  [int]$CmdId = 0,
  [string]$LogDir = "logs",
  [string]$Rvas = "0x22FD724,0x230170C,0x2235A88,0x2281C70,0x21FDDE0"
)
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace V -Name W -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int a, bool b, int p);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, int s, out IntPtr r);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
"@

$exePath = (Resolve-Path $Exe).Path
$dir = Split-Path $exePath -Parent
Write-Output ("=== " + $Tag + "  dll=" + (Test-Path (Join-Path $dir 'version.dll')))
$p = Start-Process -FilePath $exePath -WorkingDirectory $dir -PassThru
Start-Sleep -Seconds $WaitSec
$p.Refresh()
if ($p.HasExited) { Write-Output ("EXITED code=" + $p.ExitCode); exit 1 }
$ProcId = $p.Id
Write-Output ("PID=" + $ProcId)

function List-Wins {
  $script:wins = @()
  $cb = [V.W+EnumWindowsProc]{
    param($h, $l)
    $pp = 0
    [V.W]::GetWindowThreadProcessId($h, [ref]$pp) | Out-Null
    if ($pp -eq $ProcId -and [V.W]::IsWindowVisible($h)) {
      $sb = New-Object System.Text.StringBuilder 512
      [V.W]::GetWindowText($h, $sb, 512) | Out-Null
      $r = New-Object V.W+RECT
      [V.W]::GetWindowRect($h, [ref]$r) | Out-Null
      $script:wins += [pscustomobject]@{ H=$h; Title=$sb.ToString(); W=$r.R-$r.L; Hh=$r.B-$r.T; R=$r }
    }
    return $true
  }
  [V.W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
  return $script:wins
}

$wins = List-Wins
foreach ($w in $wins) { Write-Output ("TITLE: '" + $w.Title + "'  (" + $w.W + "x" + $w.Hh + ")") }

# license globals
$base = $p.Modules[0].BaseAddress.ToInt64()
$h = [V.W]::OpenProcess(0x0410, $false, $ProcId)
if ($h -ne [IntPtr]::Zero) {
  foreach ($r in $Rvas.Split(',')) {
    $rva = [Convert]::ToInt64($r.Trim(), 16)
    $buf = New-Object byte[] 8
    $rd = [IntPtr]::Zero
    if ([V.W]::ReadProcessMemory($h, [IntPtr]($base + $rva), $buf, 8, [ref]$rd)) {
      $ptr = [BitConverter]::ToUInt64($buf,0)
      $txt = ""
      if ($ptr -gt 0x10000 -and $ptr -lt 0x7FFFFFFF0000) {
        $sb2 = New-Object byte[] 200
        $rd2 = [IntPtr]::Zero
        if ([V.W]::ReadProcessMemory($h, [IntPtr]$ptr, $sb2, 200, [ref]$rd2)) { $txt = [System.Text.Encoding]::Unicode.GetString($sb2) -replace "`0.*$","" }
      }
      Write-Output ("RVA 0x{0:X7} dword={1} qword=0x{2:X16} str='{3}'" -f $rva, [BitConverter]::ToUInt32($buf,0), $ptr, $txt)
    }
  }
}

if ($CmdId -ne 0) {
  $main = $wins | Sort-Object -Property @{Expression={$_.W * $_.Hh}} -Descending | Select-Object -First 1
  [V.W]::PostMessage($main.H, 0x111, [IntPtr]$CmdId, [IntPtr]::Zero) | Out-Null
  Write-Output ("POSTED WM_COMMAND " + $CmdId)
  Start-Sleep -Seconds 4
  & (Join-Path $PSScriptRoot "shot_windows.ps1") -TargetPid $ProcId -Tag $Tag -LogDir $LogDir
}
Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue
Write-Output "KILLED"

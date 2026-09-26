# One-shot <项目A> UI flow: start -> activate -> click menu -> screenshots.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File flow_license.ps1 -Exe lab\v2830\<项目A>.exe -Tag cracked [-Dll 1]
param(
  [Parameter(Mandatory=$true)][string]$Exe,
  [Parameter(Mandatory=$true)][string]$Tag,
  [int]$WaitSec = 15,
  [string]$LogDir = "logs",
  [string]$Rvas = "0x22E4D5C,0x22E8D44,0x22694A0,0x21E52F0,0x221CEF8",
  [string]$Clicks = ""   # e.g. "1010:66,60:120" window-relative clicks, each followed by a screenshot
)
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace L -Name W -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, IntPtr e);
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int a, bool b, int p);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, int s, out IntPtr r);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
"@

$exePath = (Resolve-Path $Exe).Path
$dir = Split-Path $exePath -Parent
Write-Output ("=== CASE " + $Tag + " dll=" + (Test-Path (Join-Path $dir 'version.dll')))
$p = Start-Process -FilePath $exePath -WorkingDirectory $dir -PassThru
Start-Sleep -Seconds $WaitSec
$p.Refresh()
if ($p.HasExited) { Write-Output ("EXITED " + $p.ExitCode); exit 1 }
Write-Output ("PID=" + $p.Id)

# find largest visible window
$script:best = [IntPtr]::Zero; $script:area = 0; $script:rect = $null
$ProcId = $p.Id
$cb = [L.W+EnumWindowsProc]{
  param($h, $l)
  $pp = 0
  [L.W]::GetWindowThreadProcessId($h, [ref]$pp) | Out-Null
  if ($pp -eq $ProcId -and [L.W]::IsWindowVisible($h)) {
    $r = New-Object L.W+RECT
    [L.W]::GetWindowRect($h, [ref]$r) | Out-Null
    $a = ($r.R - $r.L) * ($r.B - $r.T)
    if ($a -gt $script:area) { $script:area = $a; $script:best = $h; $script:rect = $r }
  }
  return $true
}
[L.W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($script:best -eq [IntPtr]::Zero) { Write-Output "NO WINDOW"; exit 1 }
Write-Output ("WIN 0x{0:X} rect=({1},{2})-({3},{4})" -f $script:best.ToInt64(), $script:rect.L, $script:rect.T, $script:rect.R, $script:rect.B)
[L.W]::ShowWindow($script:best, 9) | Out-Null
[L.W]::BringWindowToTop($script:best) | Out-Null
[L.W]::SetForegroundWindow($script:best) | Out-Null
Start-Sleep -Milliseconds 1200

function FullShot($name) {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
  $path = Join-Path $LogDir ("{0}_{1}.png" -f $Tag, $name)
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  Write-Output "SHOT $path"
  $g.Dispose(); $bmp.Dispose()
}
function RelClick($dx, $dy) {
  $x = $script:rect.L + $dx; $y = $script:rect.T + $dy
  [L.W]::SetCursorPos($x, $y) | Out-Null
  Start-Sleep -Milliseconds 250
  [L.W]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 90
  [L.W]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 1000
  Write-Output "CLICK $x,$y"
}

FullShot "0_start"
if ($Clicks -ne "") {
  $i = 0
  foreach ($c in $Clicks.Split(',')) {
    $i++
    $xy = $c.Split(':')
    RelClick ([int]$xy[0]) ([int]$xy[1])
    FullShot ("$i" + "_click")
  }
}

# dump globals
$base = $p.Modules[0].BaseAddress.ToInt64()
$h = [L.W]::OpenProcess(0x0410, $false, $p.Id)
if ($h -ne [IntPtr]::Zero) {
  foreach ($r in $Rvas.Split(',')) {
    $rva = [Convert]::ToInt64($r.Trim(), 16)
    $buf = New-Object byte[] 8
    $rd = [IntPtr]::Zero
    if ([L.W]::ReadProcessMemory($h, [IntPtr]($base + $rva), $buf, 8, [ref]$rd)) {
      Write-Output ("RVA 0x{0:X7} dword={1} qword=0x{2:X16}" -f $rva, [BitConverter]::ToUInt32($buf,0), [BitConverter]::ToUInt64($buf,0))
    } else { Write-Output ("RVA 0x{0:X7} FAIL" -f $rva) }
  }
}
Write-Output ("RUNNING pid=" + $p.Id)

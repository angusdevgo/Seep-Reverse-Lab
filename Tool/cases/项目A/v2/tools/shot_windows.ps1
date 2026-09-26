# Capture every top-level window of a process via PrintWindow (works even if occluded).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File shot_windows.ps1 -TargetPid <pid> -Tag name [-LogDir logs]
param(
  [Parameter(Mandatory=$true)][int]$TargetPid,
  [Parameter(Mandatory=$true)][string]$Tag,
  [string]$LogDir = "logs"
)
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace S -Name W -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
"@
$script:wins = @()
$cb = [S.W+EnumWindowsProc]{
  param($h, $l)
  $pp = 0
  [S.W]::GetWindowThreadProcessId($h, [ref]$pp) | Out-Null
  if ($pp -eq $TargetPid -and [S.W]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 512
    [S.W]::GetWindowText($h, $sb, 512) | Out-Null
    $cn = New-Object System.Text.StringBuilder 256
    [S.W]::GetClassName($h, $cn, 256) | Out-Null
    $r = New-Object S.W+RECT
    [S.W]::GetWindowRect($h, [ref]$r) | Out-Null
    $script:wins += [pscustomobject]@{ H=$h; Title=$sb.ToString(); Class=$cn.ToString(); W=$r.R-$r.L; Hh=$r.B-$r.T }
  }
  return $true
}
[S.W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
$idx = 0
foreach ($w in $script:wins) {
  $idx++
  if ($w.W -le 1 -or $w.Hh -le 1) { Write-Output ("SKIP #{0} {1}x{2} '{3}'" -f $idx, $w.W, $w.Hh, $w.Title); continue }
  $bmp = New-Object System.Drawing.Bitmap $w.W, $w.Hh
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  $ok = [S.W]::PrintWindow($w.H, $hdc, 2)
  $g.ReleaseHdc($hdc)
  $path = Join-Path $LogDir ("{0}_w{1}.png" -f $Tag, $idx)
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  Write-Output ("WINDOW #{0} hwnd=0x{1:X} {2}x{3} class={4} title='{5}' pw={6} -> {7}" -f $idx, $w.H.ToInt64(), $w.W, $w.Hh, $w.Class, $w.Title, $ok, $path)
  $g.Dispose(); $bmp.Dispose()
}

$src = @'
using System;
using System.Runtime.InteropServices;
using System.Drawing;
public class S {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string c, string n);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int m);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  public struct RECT { public int L,T,R,B; }
}
'@
Add-Type -TypeDefinition $src
Add-Type -AssemblyName System.Drawing, System.Windows.Forms

$targets = @()
$cb = [S+EnumProc]{
  param($h, $p)
  $pid2 = 0
  [void][S]::GetWindowThreadProcessId($h, [ref]$pid2)
  if ($pid2 -eq 11260 -and [S]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 300
    [void][S]::GetWindowText($h, $sb, 300)
    $script:targets += [PSCustomObject]@{ H=$h; Title=$sb.ToString() }
  }
  return $true
}
[void][S]::EnumWindows($cb, [IntPtr]::Zero)
$targets | ForEach-Object { Write-Host ("0x{0:X}  '{1}'" -f [int64]$_.H, $_.Title) }

$main = $targets | Where-Object { $_.Title -like "*License*" } | Select-Object -First 1
if ($main) {
  [void][S]::ShowWindow($main.H, 3)
  [void][S]::SetForegroundWindow($main.H)
  Start-Sleep -Milliseconds 700
  $r = New-Object S+RECT
  [void][S]::GetWindowRect($main.H, [ref]$r)
  $w = $r.R - $r.L; $hh = $r.B - $r.T
  Write-Host "rect: $($r.L),$($r.T) ${w}x${hh}"
  $bmp = New-Object System.Drawing.Bitmap $w, $hh
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
  $bmp.Save("C:\Users\Angus\Desktop\pi\seep\ida_lic.png", [System.Drawing.Imaging.ImageFormat]::Png)
  Write-Host "saved ida_lic.png"
}

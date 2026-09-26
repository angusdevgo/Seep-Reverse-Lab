param([string]$Exe="lab\v2840\<项目A>.exe",[int]$WaitSec=15,[string]$Tag="title")
Add-Type -Namespace T -Name W -MemberDefinition @"
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
"@
$exePath=(Resolve-Path $Exe).Path; $dir=Split-Path $exePath -Parent
$p=Start-Process -FilePath $exePath -WorkingDirectory $dir -PassThru
Start-Sleep -Seconds $WaitSec
$p.Refresh(); if ($p.HasExited) { "EXITED"; exit }
$ProcId=$p.Id
function T($tag){
  $script:best=[IntPtr]::Zero; $script:area=0; $script:cap=""
  $cb=[T.W+EnumWindowsProc]{ param($h,$l)
    $pp=0; [T.W]::GetWindowThreadProcessId($h,[ref]$pp)|Out-Null
    if ($pp -eq $ProcId -and [T.W]::IsWindowVisible($h)) {
      $r=New-Object T.W+RECT; [T.W]::GetWindowRect($h,[ref]$r)|Out-Null
      $a=($r.R-$r.L)*($r.B-$r.T)
      if ($a -gt $script:area) { $script:area=$a; $sb=New-Object System.Text.StringBuilder 512; [T.W]::GetWindowText($h,$sb,512)|Out-Null; $script:cap=$sb.ToString() }
    }
    return $true }
  [T.W]::EnumWindows($cb,[IntPtr]::Zero)|Out-Null
  "[" + $tag + "] " + $script:cap
}
T "t0"
Start-Process -FilePath $exePath -ArgumentList '"C:\Windows"' -WorkingDirectory $dir | Out-Null
Start-Sleep -Seconds 6
T "after-navigate"
Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue

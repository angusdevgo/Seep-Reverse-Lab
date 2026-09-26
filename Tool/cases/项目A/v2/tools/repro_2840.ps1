# 28.40 reproduction with the self-built DLL (real install)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File repro_2840.ps1
param(
  [string]$Exe = "D:\Data\XYplorer\XYplorer.exe",
  [string]$Dll = "C:\Users\Angus\Desktop\pi\seep\project\xyplorer\dist\version.dll",
  [string]$Tag = "repro2840",
  [int]$WaitSec = 18,
  [string]$LogDir = "logs"
)
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type -Namespace P -Name W -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int a, bool b, int p);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, int s, out IntPtr r);
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
"@

function Get-Hash($p) { (Get-FileHash -Algorithm SHA256 $p).Hash.ToLower() }

Write-Output "########## STEP 1: DEPLOY ##########"
Write-Output ("TARGET EXE : " + $Exe + "  sha256=" + (Get-Hash $Exe))
$dst = Join-Path (Split-Path $Exe -Parent) "version.dll"
if (Test-Path $dst) {
  Write-Output ("EXISTING   : " + $dst + "  sha256=" + (Get-Hash $dst))
  Copy-Item $dst "$dst.bak_thirdparty" -Force
  Write-Output "BACKED UP  : version.dll.bak_thirdparty"
}
Copy-Item $Dll $dst -Force
Write-Output ("DEPLOYED   : " + $dst + "  sha256=" + (Get-Hash $dst))
Remove-Item (Join-Path (Split-Path $Exe -Parent) "version_poc.log") -Force -ErrorAction SilentlyContinue

Write-Output "########## STEP 2: RUN + READ LICENSE STATE ##########"
$p = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe -Parent) -PassThru
Start-Sleep -Seconds $WaitSec
$p.Refresh()
if ($p.HasExited) { Write-Output ("PROCESS EXITED code=" + $p.ExitCode); exit 1 }
$ProcId = $p.Id
Write-Output ("PID=" + $ProcId)

$base = $p.Modules[0].BaseAddress.ToInt64()
Write-Output ("IMAGEBASE=0x" + $base.ToString("X"))
$h = [P.W]::OpenProcess(0x0410, $false, $ProcId)
$map = @{ "0x22FD724" = "license_type"; "0x230170C" = "ver_flag"; "0x2235A88" = "license_name";
          "0x2281C70" = "license_code1"; "0x21FDDE0" = "license_code2" }
foreach ($k in @("0x22FD724","0x230170C","0x2235A88","0x2281C70","0x21FDDE0")) {
  $rva = [Convert]::ToInt64($k, 16)
  $buf = New-Object byte[] 8; $rd = [IntPtr]::Zero
  if ([P.W]::ReadProcessMemory($h, [IntPtr]($base + $rva), $buf, 8, [ref]$rd)) {
    $dw = [BitConverter]::ToUInt32($buf, 0)
    $qw = [BitConverter]::ToUInt64($buf, 0)
    $str = ""
    if ($qw -gt 0x10000 -and $qw -lt 0x7FFFFFFF0000) {
      $sb = New-Object byte[] 200; $rd2 = [IntPtr]::Zero
      $addr2 = [IntPtr]([int64]$qw)
      if ([P.W]::ReadProcessMemory($h, $addr2, $sb, 200, [ref]$rd2)) {
        $str = [System.Text.Encoding]::Unicode.GetString($sb)
        $ix = $str.IndexOf([char]0); if ($ix -ge 0) { $str = $str.Substring(0, $ix) }
      }
    }
    Write-Output ("  {0,-16} RVA {1}  dword={2,-6} qword=0x{3:X16}  str='{4}'" -f $map[$k], $k, $dw, $qw, $str)
  }
}

Write-Output "########## STEP 3: DLL LOG ##########"
$lg = Join-Path (Split-Path $Exe -Parent) "version_poc.log"
if (Test-Path $lg) { Get-Content $lg | ForEach-Object { Write-Output ("  " + $_) } } else { Write-Output "  (no log yet)" }

Write-Output "########## STEP 4: WINDOW EVIDENCE ##########"
$script:wins = @()
$cb = [P.W+EnumWindowsProc]{
  param($hw, $l)
  $pp = 0; [P.W]::GetWindowThreadProcessId($hw, [ref]$pp) | Out-Null
  if ($pp -eq $ProcId -and [P.W]::IsWindowVisible($hw)) {
    $sb = New-Object System.Text.StringBuilder 512; [P.W]::GetWindowText($hw, $sb, 512) | Out-Null
    $r = New-Object P.W+RECT; [P.W]::GetWindowRect($hw, [ref]$r) | Out-Null
    $script:wins += [pscustomobject]@{ H=$hw; Title=$sb.ToString(); W=$r.R-$r.L; Hh=$r.B-$r.T }
  }
  return $true
}
[P.W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
$i = 0
foreach ($w in $script:wins) {
  $i++
  Write-Output ("  WINDOW: '" + $w.Title + "'  (" + $w.W + "x" + $w.Hh + ")")
  if ($w.W -gt 1 -and $w.Hh -gt 1) {
    $bmp = New-Object System.Drawing.Bitmap $w.W, $w.Hh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc(); [P.W]::PrintWindow($w.H, $hdc, 2) | Out-Null; $g.ReleaseHdc($hdc)
    $out = Join-Path $LogDir ("{0}_w{1}.png" -f $Tag, $i)
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output ("    -> " + $out)
    $g.Dispose(); $bmp.Dispose()
  }
}
Write-Output ("RUNNING pid=" + $ProcId + "  (kill: Stop-Process -Id " + $ProcId + ")")

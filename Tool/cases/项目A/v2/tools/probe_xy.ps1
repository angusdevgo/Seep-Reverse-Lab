# <项目A>  (Windows x64)
# : powershell -NoProfile -ExecutionPolicy Bypass -File probe_xy.ps1 -ExePath <path> [-Seconds 12] [-Screenshot <png>] [-Kill]
param(
  [Parameter(Mandatory=$true)][string]$ExePath,
  [int]$Seconds = 12,
  [string]$Screenshot = "",
  [switch]$Kill
)

$ErrorActionPreference = "Continue"
Add-Type -Namespace Win32 -Name Mem -MemberDefinition @"
[DllImport("kernel32.dll", SetLastError=true)]
public static extern IntPtr OpenProcess(int access, bool inherit, int pid);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out IntPtr read);
[DllImport("kernel32.dll")]
public static extern bool CloseHandle(IntPtr h);
[DllImport("user32.dll")]
public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")]
public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
"@
Add-Type -AssemblyName System.Drawing

$exe = (Resolve-Path $ExePath).Path
Write-Output "=== LAUNCH $exe ==="
$p = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds $Seconds
$p.Refresh()
if ($p.HasExited) { Write-Output "PROCESS EXITED code=$($p.ExitCode)"; exit 1 }

Write-Output ("PID={0}  MainWindowTitle='{1}'" -f $p.Id, $p.MainWindowTitle)

try {
  $all = $p.Modules
  Write-Output ("MODULE-COUNT={0}" -f $all.Count)
  foreach ($m in $all) { if ($m.ModuleName -match 'version|XYcopy|kernel32|<项目A>') { Write-Output ("MODULE {0,-22} {1}" -f $m.ModuleName, $m.FileName) } }
} catch { Write-Output "MODULE-ENUM-FAILED: $($_.Exception.Message)" }

$rvas = @(0x221cef8, 0x22694a0, 0x21e52f0, 0x265e408, 0x22FD724)
$base = $p.Modules[0].BaseAddress.ToInt64()
Write-Output ("IMAGEBASE=0x{0:X}" -f $base)
$h = [Win32.Mem]::OpenProcess(0x0410, $false, $p.Id)
if ($h -ne [IntPtr]::Zero) {
  foreach ($rva in $rvas) {
    $buf = New-Object byte[] 8
    $rd = [IntPtr]::Zero
    $addr = [IntPtr]($base + $rva)
    if ([Win32.Mem]::ReadProcessMemory($h, $addr, $buf, 8, [ref]$rd)) {
      $q = [BitConverter]::ToUInt64($buf, 0)
      $d = [BitConverter]::ToUInt32($buf, 0)
      Write-Output ("RVA 0x{0:X7}  qword=0x{1:X16}  dword={2}" -f $rva, $q, $d)
    } else {
      Write-Output ("RVA 0x{0:X7}  READ-FAIL" -f $rva)
    }
  }
  [Win32.Mem]::CloseHandle($h) | Out-Null
} else { Write-Output "OpenProcess failed" }

if ($Screenshot -ne "") {
  $hwnd = $p.MainWindowHandle
  if ($hwnd -ne [IntPtr]::Zero) {
    [Win32.Mem]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 900
    $r = New-Object Win32.Mem+RECT
    [Win32.Mem]::GetWindowRect($hwnd, [ref]$r) | Out-Null
    $w = $r.R - $r.L; $hh = $r.B - $r.T
    Write-Output ("WINDOW RECT {0},{1} {2}x{3}" -f $r.L, $r.T, $w, $hh)
    if ($w -gt 0 -and $hh -gt 0) {
      $bmp = New-Object System.Drawing.Bitmap $w, $hh
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
      $bmp.Save($Screenshot, [System.Drawing.Imaging.ImageFormat]::Png)
      Write-Output "SCREENSHOT SAVED $Screenshot ($w x $hh)"
      $g.Dispose(); $bmp.Dispose()
    }
  } else { Write-Output "NO MAIN WINDOW HANDLE" }
}

if ($Kill) {
  $p | Stop-Process -Force -ErrorAction SilentlyContinue
  Write-Output "PROCESS STOPPED"
} else {
  Write-Output ("PROCESS LEFT RUNNING pid={0}" -f $p.Id)
}

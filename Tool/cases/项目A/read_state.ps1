Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M {
  [DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int a, bool b, int p);
  [DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out IntPtr read);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
}
"@
$p = Get-Process 项目A -ErrorAction Stop
$h = [M]::OpenProcess(0x10, $false, $p.Id)
$base = $p.MainModule.BaseAddress.ToInt64()

function Get-Bytes([long]$off, [int]$len) {
  $buf = New-Object byte[] $len
  $r = [IntPtr]::Zero
  [void][M]::ReadProcessMemory($h, [IntPtr]($base + $off), $buf, $len, [ref]$r)
  return $buf
}
function Get-Q([long]$off) { return [BitConverter]::ToInt64((Get-Bytes $off 8), 0) }
function Get-D([long]$off) { return [BitConverter]::ToInt32((Get-Bytes $off 4), 0) }
function Get-W([long]$off) { return [BitConverter]::ToUInt16((Get-Bytes $off 2), 0) }
function Get-BStr([long]$ptr) {
  if ($ptr -eq 0) { return "<null>" }
  $len = [BitConverter]::ToInt32((Get-Bytes ($ptr - $base) 4), 0)
  if ($len -le 0 -or $len -gt 512) { return "<len=$len>" }
  $b = Get-Bytes ($ptr - $base + 4) ($len * 2)
  return [System.Text.Encoding]::Unicode.GetString($b)
}

Write-Host "PID: $($p.Id)  base: 0x$($base.ToString('X'))"
Write-Host ""
Write-Host "=== license strings ==="
$n = Get-Q 0x221CEF8
Write-Host ("Name @0x221CEF8 -> 0x{0:X} = '{1}'" -f $n, (Get-BStr $n))
$k1 = Get-Q 0x21E52F0
Write-Host ("Key1 @0x21E52F0 -> 0x{0:X} = '{1}'" -f $k1, (Get-BStr $k1))
$k2 = Get-Q 0x22694A0
Write-Host ("Key2 @0x22694A0 -> 0x{0:X} = '{1}'" -f $k2, (Get-BStr $k2))
Write-Host ""
Write-Host "=== flags ==="
Write-Host ("regType @0x22E8D44 = {0} (0x{0:X})" -f (Get-D 0x22E8D44))
Write-Host ("keyType @0x22E4D5C = {0} (0x{0:X})" -f (Get-D 0x22E4D5C))
Write-Host ("isReg   @0x22F434A = {0} (0x{0:X})" -f (Get-W 0x22F434A))
Write-Host ""
Write-Host "=== patched code ==="
$b1 = Get-Bytes 0x66FC95 34
Write-Host ("p1 @0x66FC95: " + (($b1 | % { $_.ToString('X2') }) -join ' '))
$b2 = Get-Bytes 0x66DB7B 5
Write-Host ("p2 @0x66DB7B: " + (($b2 | % { $_.ToString('X2') }) -join ' '))
[M]::CloseHandle($h) | Out-Null

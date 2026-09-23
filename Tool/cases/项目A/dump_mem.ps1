$src = @'
using System;
using System.Runtime.InteropServices;
public class Mem2 {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern IntPtr OpenProcess(int a, bool b, int p);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out IntPtr read);
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool CloseHandle(IntPtr h);
}
'@
Add-Type -TypeDefinition $src

$p = Get-Process 项目A
$h = [Mem2]::OpenProcess(0x10, $false, $p.Id)
Write-Host "handle = $h"
function XB([long]$abs, [int]$len) {
  $buf = New-Object byte[] $len
  $r = [IntPtr]::Zero
  [void][Mem2]::ReadProcessMemory($h, [IntPtr]$abs, $buf, $len, [ref]$r)
  return $buf
}
function XQ([long]$a) { return [BitConverter]::ToInt64((XB $a 8), 0) }

$n = XQ 0x140221CEF8
Write-Host ("Name ptr = 0x{0:X}" -f $n)
if ($n -ne 0) {
  $b = XB $n 96
  for ($i=0; $i -lt 96; $i+=16) {
    $hex = ($b[$i..($i+15)] | % { $_.ToString('X2') }) -join ' '
    $asc = -join ($b[$i..($i+15)] | % { if ($_ -ge 32 -and $_ -lt 127) { [char]$_ } else { '.' } })
    Write-Host ("  +{0:X2}: {1}  {2}" -f $i, $hex, $asc)
  }
  Write-Host ("len@ptr-4 = {0}" -f [BitConverter]::ToInt32((XB ($n-4) 4),0))
  Write-Host ("len@ptr   = {0}" -f [BitConverter]::ToInt32((XB $n 4),0))
  Write-Host ("utf16@ptr = '{0}'" -f [System.Text.Encoding]::Unicode.GetString((XB $n 60)))
}
[void][Mem2]::CloseHandle($h)

param([int]$TargetPid, [string[]]$Rvas)
Add-Type -Namespace W -Name M -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int a, bool b, int p);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, int s, out IntPtr r);
"@
$p = Get-Process -Id $TargetPid
$base = $p.Modules[0].BaseAddress.ToInt64()
Write-Output ("BASE=0x{0:X}" -f $base)
$h = [W.M]::OpenProcess(0x0410, $false, $TargetPid)
foreach ($r in $Rvas) {
  $rva = [Convert]::ToInt64($r, 16)
  $buf = New-Object byte[] 8
  $rd = [IntPtr]::Zero
  if ([W.M]::ReadProcessMemory($h, [IntPtr]($base+$rva), $buf, 8, [ref]$rd)) {
    Write-Output ("RVA 0x{0:X7}  dword={1}  qword=0x{2:X16}" -f $rva, [BitConverter]::ToUInt32($buf,0), [BitConverter]::ToUInt64($buf,0))
  } else { Write-Output ("RVA 0x{0:X7}  FAIL" -f $rva) }
}

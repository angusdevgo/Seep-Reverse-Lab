$src = @'
using System;
using System.Runtime.InteropServices;
public class K {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string name);
}
'@
Add-Type -TypeDefinition $src
$p = Get-Process -Id 11260 -ErrorAction SilentlyContinue
if (-not $p) { Write-Host "IDA not running"; exit }
Write-Host "IDA MainWindowTitle: '$($p.MainWindowTitle)'"
Write-Host "hwnd: 0x$($p.MainWindowHandle.ToString('X'))"
if ($p.MainWindowHandle -ne 0) {
  [void][K]::ShowWindow($p.MainWindowHandle, 3)
  [void][K]::SetForegroundWindow($p.MainWindowHandle)
  Start-Sleep -Milliseconds 800
  # Ctrl+Alt+M
  [K]::keybd_event(0x11,0,0,[IntPtr]::Zero)  # ctrl
  [K]::keybd_event(0x12,0,0,[IntPtr]::Zero)  # alt
  [K]::keybd_event(0x4D,0,0,[IntPtr]::Zero)  # m
  Start-Sleep -Milliseconds 100
  [K]::keybd_event(0x4D,0,2,[IntPtr]::Zero)
  [K]::keybd_event(0x12,0,2,[IntPtr]::Zero)
  [K]::keybd_event(0x11,0,2,[IntPtr]::Zero)
  Write-Host "sent Ctrl+Alt+M"
}

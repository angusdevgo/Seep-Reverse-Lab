$src = @'
using System;
using System.Runtime.InteropServices;
public class Win {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string name);
  [DllImport("user32.dll")] public static extern IntPtr GetMenu(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetSubMenu(IntPtr h, int pos);
  [DllImport("user32.dll")] public static extern int GetMenuItemCount(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetMenuString(IntPtr h, uint id, System.Text.StringBuilder s, int max, uint flags);
  [DllImport("user32.dll")] public static extern uint GetMenuItemID(IntPtr h, int pos);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L, T, R, B; }
}
'@
Add-Type -TypeDefinition $src

$p = Get-Process 项目A
$hwnd = $p.MainWindowHandle
Write-Host "hwnd = 0x$($hwnd.ToString('X'))"
[void][Win]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 400

# Menu bar: enumerate top-level menus of 项目A main window
$hmenu = [Win]::GetMenu($hwnd)
$cnt = [Win]::GetMenuItemCount($hmenu)
Write-Host "top-level menu items: $cnt"
for ($i=0; $i -lt $cnt; $i++) {
  $sb = New-Object System.Text.StringBuilder 256
  [void][Win]::GetMenuString($hmenu, [uint32]$i, $sb, 256, 0x400)
  Write-Host ("  [$i] id={0} '{1}'" -f [Win]::GetMenuItemID($hmenu,$i), $sb.ToString())
}

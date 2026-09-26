<#
  apply_patch.ps1 —— 项目J 在线卡密授权客户端旁路补丁器 (PowerShell 版, 无需 Python)
  ------------------------------------------------------------------------------
  用法（必须【以管理员身份】运行 PowerShell）:
      powershell -NoProfile -ExecutionPolicy Bypass -File .\apply_patch.ps1
      powershell -NoProfile -ExecutionPolicy Bypass -File .\apply_patch.ps1 -Target "<样本目录>\target.exe"

  补丁 3 处 / 22 字节：
      0x00401290  83 7D FC 00 0F 84 4D 02 00 00  ->  C7 45 FC 01 00 00 00 90 90 90
      0x0041AC81  0F 8D 34 01 00 00               ->  E9 35 01 00 00 90
      0x0041AE05  0F 8D 34 01 00 00               ->  E9 35 01 00 00 90
#>

param(
    [string]$Target = ''
)

$ErrorActionPreference = 'Stop'

# 自动定位目标：同目录 -> 交付包内的 06_免UAC实验环境 / 03_原始样本 -> 向上回溯搜索
if ([string]::IsNullOrWhiteSpace($Target)) {
    $names = @('target_patched.exe', '实验副本.exe', 'target.exe')
    $dirs  = @($PSScriptRoot,
               (Join-Path (Split-Path -Parent $PSScriptRoot) '06_免UAC实验环境'),
               (Join-Path (Split-Path -Parent $PSScriptRoot) '03_原始样本'),
               (Join-Path (Split-Path -Parent $PSScriptRoot) 'samples'))
    foreach ($d in $dirs) {
        foreach ($n in $names) {
            $cand = Join-Path $d $n
            if (Test-Path -LiteralPath $cand) { $Target = $cand; break }
        }
        if (-not [string]::IsNullOrWhiteSpace($Target)) { break }
    }
    if ([string]::IsNullOrWhiteSpace($Target)) { $Target = Join-Path $PSScriptRoot 'target.exe' }
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class SBZPatcher
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct STARTUPINFO
    {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION
    {
        public IntPtr hProcess;
        public IntPtr hThread;
        public int dwProcessId;
        public int dwThreadId;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CreateProcessW(string lpApplicationName, string lpCommandLine,
        IntPtr lpProcessAttributes, IntPtr lpThreadAttributes, bool bInheritHandles,
        uint dwCreationFlags, IntPtr lpEnvironment, string lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo, out PROCESS_INFORMATION lpProcessInformation);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool ReadProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress,
        byte[] lpBuffer, int dwSize, out IntPtr lpNumberOfBytesRead);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool WriteProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress,
        byte[] lpBuffer, int dwSize, out IntPtr lpNumberOfBytesWritten);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool VirtualProtectEx(IntPtr hProcess, IntPtr lpAddress,
        int dwSize, uint flNewProtect, out uint lpflOldProtect);
}
"@

$PROCESS_ALL_ACCESS     = 0x1F0FFF
$PAGE_EXECUTE_READWRITE = 0x40
# 让目标脱离调用方控制台：否则 .bat 跑完、控制台关闭时目标会被 CTRL_CLOSE_EVENT 杀掉
$CREATE_DETACHED_PROCESS = 0x00000008
$HEARTBEAT_ENTRY        = 0x0041AB86     # 外壳解密完成判据锚点

# 补丁表: @(地址, 原始字节, 补丁字节, 说明)
$PATCHES = @(
    @{ Addr = 0x00401290; Orig = '837DFC000F844D020000'; New = 'C745FC01000000909090'; Desc = '登录校验: cmp [ebp-4],0 / je fail -> mov [ebp-4],1' },
    @{ Addr = 0x0041AC81; Orig = '0F8D34010000';         New = 'E93501000090';         Desc = '授权心跳复检 #1: jge 0x41ADBB -> jmp 0x41ADBB' },
    @{ Addr = 0x0041AE05; Orig = '0F8D34010000';         New = 'E93501000090';         Desc = '授权心跳复检 #2: jge 0x41AF3F -> jmp 0x41AF3F' }
)

function HexToBytes([string]$hex) {
    $b = New-Object byte[] ($hex.Length / 2)
    for ($i = 0; $i -lt $b.Length; $i++) { $b[$i] = [Convert]::ToByte($hex.Substring($i * 2, 2), 16) }
    return $b
}

function BytesToHex([byte[]]$b) {
    return (($b | ForEach-Object { $_.ToString('x2') }) -join ' ')
}

function Read-Bytes($h, [int]$addr, [int]$size) {
    $buf = New-Object byte[] $size
    $read = [IntPtr]::Zero
    if (-not [SBZPatcher]::ReadProcessMemory($h, [IntPtr]$addr, $buf, $size, [ref]$read)) { return $null }
    return $buf
}

function Write-Bytes($h, [int]$addr, [byte[]]$data) {
    $old = [uint32]0
    [SBZPatcher]::VirtualProtectEx($h, [IntPtr]$addr, $data.Length, $PAGE_EXECUTE_READWRITE, [ref]$old) | Out-Null
    $written = [IntPtr]::Zero
    $ok = [SBZPatcher]::WriteProcessMemory($h, [IntPtr]$addr, $data, $data.Length, [ref]$written)
    [SBZPatcher]::VirtualProtectEx($h, [IntPtr]$addr, $data.Length, $old, [ref]$old) | Out-Null
    return ($ok -and $written.ToInt64() -eq $data.Length)
}

# ---------------------------------------------------------------- main
if (-not (Test-Path -LiteralPath $Target)) {
    Write-Host "[!] 找不到目标: $Target" -ForegroundColor Red
    exit 1
}
$Target = (Resolve-Path -LiteralPath $Target).Path

$si = New-Object SBZPatcher+STARTUPINFO
$si.cb = [System.Runtime.InteropServices.Marshal]::SizeOf($si)
$pi = New-Object SBZPatcher+PROCESS_INFORMATION

$cwd = Split-Path -Parent $Target
$ok = [SBZPatcher]::CreateProcessW($Target, $null, [IntPtr]::Zero, [IntPtr]::Zero, $false, $CREATE_DETACHED_PROCESS, [IntPtr]::Zero, $cwd, [ref]$si, [ref]$pi)
if (-not $ok) {
    $err = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
    if ($err -eq 740) { Write-Host "[!] 需要提权(ERROR_ELEVATION_REQUIRED) —— 请以管理员身份运行本脚本" -ForegroundColor Red }
    else              { Write-Host "[!] CreateProcess 失败 err=$err" -ForegroundColor Red }
    exit 1
}

$pid2 = $pi.dwProcessId
Write-Host "[*] 已启动目标 PID=$pid2，等待外壳解密 .ev3n ..." -ForegroundColor Cyan

$h = [SBZPatcher]::OpenProcess($PROCESS_ALL_ACCESS, $false, $pid2)
if ($h -eq [IntPtr]::Zero) {
    Write-Host "[!] OpenProcess 失败(请以管理员身份运行) err=$([System.Runtime.InteropServices.Marshal]::GetLastWin32Error())" -ForegroundColor Red
    exit 1
}

# 等待解密完成: 0x41AB86 处出现 55 8B EC
$deadline = (Get-Date).AddSeconds(30)
$ready = $false
while ((Get-Date) -lt $deadline) {
    $cur = Read-Bytes $h $HEARTBEAT_ENTRY 3
    if ($cur -and $cur[0] -eq 0x55 -and $cur[1] -eq 0x8B -and $cur[2] -eq 0xEC) { $ready = $true; break }
    Start-Sleep -Milliseconds 20
}
if (-not $ready) { Write-Host "[!] 超时: .ev3n 段仍未解密" -ForegroundColor Red; exit 1 }
Write-Host "[+] .ev3n 已解密" -ForegroundColor Green

$allOk = $true
foreach ($p in $PATCHES) {
    $addr = [int]$p.Addr
    $orig = HexToBytes $p.Orig
    $new  = HexToBytes $p.New

    $cur = Read-Bytes $h $addr $orig.Length
    if ($null -eq $cur) { Write-Host ("[!] 读取失败 @0x{0:X8}" -f $addr) -ForegroundColor Red; $allOk = $false; continue }

    $curHex = (BytesToHex $cur) -replace ' ', ''
    if ($curHex -eq $p.New) { Write-Host ("[=] 已是补丁状态 @0x{0:X8}  {1}" -f $addr, $p.Desc) -ForegroundColor Yellow; continue }
    if ($curHex -ne $p.Orig) {
        Write-Host ("[!] 字节不符 @0x{0:X8}: 实际 {1} / 期望 {2}" -f $addr, (BytesToHex $cur), (BytesToHex $orig)) -ForegroundColor Red
        $allOk = $false; continue
    }

    if (Write-Bytes $h $addr $new) {
        $back = Read-Bytes $h $addr $new.Length
        Write-Host ("[+] 已打补丁 @0x{0:X8}  {1}" -f $addr, $p.Desc) -ForegroundColor Green
        Write-Host ("      {0}  ->  {1}   [回读 {2}]" -f (BytesToHex $orig), (BytesToHex $new), (BytesToHex $back))
    } else {
        Write-Host ("[!] WriteProcessMemory 失败 @0x{0:X8} err={1}" -f $addr, [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()) -ForegroundColor Red
        $allOk = $false
    }
}

if (-not $allOk) { Write-Host "[!] 部分补丁未生效" -ForegroundColor Red; exit 1 }
Write-Host "[+] DONE —— 在登录框输入任意卡密(例如 123456)点击「登陆」即可进入主界面" -ForegroundColor Green

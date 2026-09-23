# auto_activate.ps1 - 项目E 一键激活（全自动）
# 自动完成：退出进程 → 备份原件 → 应用补丁并原位替换 → 写入注册表 RN/RC → 复读校验
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File auto_activate.ps1
#   powershell -ExecutionPolicy Bypass -File auto_activate.ps1 -ExePath "<本地路径>"
#   powershell -ExecutionPolicy Bypass -File auto_activate.ps1 -Name "Pro User" -Code "XXXX-YYYY"
# 说明: 目标 exe 默认取本脚本同目录或安装探测；Name/Code 缺省自动随机生成。
#       需要替换受保护目录（如 Program Files）时请以管理员身份运行（或接受 UAC 弹窗）。

param(
    [string]$ExePath = "",
    [string]$Name = "",
    [string]$Code = "",
    [string]$BackupPath = ""
)
$ErrorActionPreference = 'Stop'

# ---------- 常量（与 src/Patcher.cs / scripts/uninstall_tool_patch.py 一致） ----------
$RegRoot  = 'HKCU:\Software\项目E Software\项目E'
$StubVa   = 0x140001622
$CallVa   = 0x140009E0F
$StubBytes = [byte[]](0xB8, 0x03, 0x00, 0x00, 0x00, 0xC3)   # mov eax,3; ret

function Log([string]$m) { Write-Host ("[" + (Get-Date -Format HH:mm:ss) + "] " + $m) }

# ---------- 1. 定位目标 exe ----------
if ($ExePath -eq "") {
    $candidates = @(
        (Join-Path $PSScriptRoot '项目E.exe'),
        '<本地路径>'
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $ExePath = $c; break } }
}
if ($ExePath -eq "" -or -not (Test-Path $ExePath)) {
    throw "找不到 项目E.exe，请用 -ExePath 指定"
}
$ExePath = (Resolve-Path $ExePath).Path
Log "目标 exe: $ExePath"

# ---------- 2. 退出进程 ----------
function Stop-UtProcess {
    Get-Process -Name '项目E','项目EHelper' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    return -not (Get-Process -Name '项目E','项目EHelper' -ErrorAction SilentlyContinue)
}
if (-not (Stop-UtProcess)) {
    Log '进程仍存在，尝试 UAC 提权结束（请在弹出的 UAC 窗口点“是”）...'
    $e1 = Start-Process taskkill.exe -ArgumentList '/F','/IM','项目E.exe','/T' -Verb RunAs -PassThru -Wait -ErrorAction SilentlyContinue
    $e2 = Start-Process taskkill.exe -ArgumentList '/F','/IM','项目EHelper.exe','/T' -Verb RunAs -PassThru -Wait -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 1500
    if (-not (Stop-UtProcess)) { throw '无法结束 项目E 进程，请手动退出后重试' }
}
Log '进程已退出'

# ---------- 3. 读取 + 内存补丁 ----------
$bytes = [System.IO.File]::ReadAllBytes($ExePath)
Log ("输入 SHA256: " + (Get-FileHash -Algorithm SHA256 $ExePath).Hash)

# 3a. 判定是否已补丁（call 目标 == stub）
function Get-CallTarget([byte[]]$data) {
    $pe = [BitConverter]::ToInt32($data, 0x3C)
    $nsec = [BitConverter]::ToUInt16($data, $pe + 6)
    $opt = $pe + 24
    $imgBase = [BitConverter]::ToInt64($data, $opt + 24)
    $secOff = $opt + [BitConverter]::ToUInt16($data, $pe + 20)
    for ($i = 0; $i -lt $nsec; $i++) {
        $so = $secOff + $i * 40
        $vsize = [BitConverter]::ToInt32($data, $so + 8)
        $vaddr = [BitConverter]::ToUInt32($data, $so + 12)
        $rsize = [BitConverter]::ToInt32($data, $so + 16)
        $raddr = [BitConverter]::ToUInt32($data, $so + 20)
        $sva = $imgBase + $vaddr
        $max = [Math]::Max($vsize, $rsize)
        if ($script:CallVa -ge $sva -and $script:CallVa -lt ($sva + $max)) {
            $off = $raddr + ($script:CallVa - $sva)
            if ($data[$off] -ne 0xE8) { throw 'call 指令校验失败（非 E8）' }
            $rel = [BitConverter]::ToInt32($data, $off + 1)
            return (($script:CallVa + 5 + $rel) -band 0xFFFFFFFFFFFF)
        }
    }
    throw 'call VA 不在任何节内'
}
function Va-Offset([byte[]]$data, [long]$va) {
    $pe = [BitConverter]::ToInt32($data, 0x3C)
    $nsec = [BitConverter]::ToUInt16($data, $pe + 6)
    $opt = $pe + 24
    $imgBase = [BitConverter]::ToInt64($data, $opt + 24)
    $secOff = $opt + [BitConverter]::ToUInt16($data, $pe + 20)
    for ($i = 0; $i -lt $nsec; $i++) {
        $so = $secOff + $i * 40
        $vsize = [BitConverter]::ToInt32($data, $so + 8)
        $vaddr = [BitConverter]::ToUInt32($data, $so + 12)
        $rsize = [BitConverter]::ToInt32($data, $so + 16)
        $raddr = [BitConverter]::ToUInt32($data, $so + 20)
        $sva = $imgBase + $vaddr
        $max = [Math]::Max($vsize, $rsize)
        if ($va -ge $sva -and $va -lt ($sva + $max)) { return ($raddr + ($va - $sva)) }
    }
    throw ("VA 0x{0:X} 不在任何节内" -f $va)
}

$alreadyPatched = $false
try { $alreadyPatched = ((Get-CallTarget $bytes) -eq $StubVa) } catch { }

if ($alreadyPatched) {
    Log '目标已是补丁版，跳过替换（保持原位）'
} else {
    # 备份
    $bak = [System.IO.Path]::ChangeExtension($ExePath, '.orig.exe')
    if (-not (Test-Path $bak)) {
        Copy-Item $ExePath $bak
        Log "已备份原件 -> $bak"
    } else {
        Log "备份已存在（保留）: $bak"
    }
    # stub
    $stubOff = Va-Offset $bytes $StubVa
    [Array]::Copy($StubBytes, 0, $bytes, $stubOff, $StubBytes.Length)
    # call 重定向
    $callOff = Va-Offset $bytes $CallVa
    if ($bytes[$callOff] -ne 0xE8) { throw 'call 指令校验失败' }
    $rel = [int](($StubVa - ($CallVa + 5)) -band 0xFFFFFFFF)
    $bytes[$callOff] = 0xE8
    $relBytes = [BitConverter]::GetBytes($rel)
    [Array]::Copy($relBytes, 0, $bytes, $callOff + 1, 4)
    # 原位写回
    [System.IO.File]::WriteAllBytes($ExePath, $bytes)
    Log '补丁已写入并原位替换'
}

# 复读校验
$check = [System.IO.File]::ReadAllBytes($ExePath)
$target2 = Get-CallTarget $check
$stubOff2 = Va-Offset $check $StubVa
$stubOk = -not (Compare-Object $StubBytes ([byte[]]$check[$stubOff2..($stubOff2 + 5)]))
if ($target2 -ne $StubVa -or -not $stubOk) { throw '补丁复读校验失败！' }
Log ("输出 SHA256: " + (Get-FileHash -Algorithm SHA256 $ExePath).Hash)
Log '补丁校验通过（IsRegistered 判定恒 3）'

# ---------- 4. 随机名/码 ----------
if ($Name -eq '') { $Name = 'Pro User ' + (Get-Random -Minimum 100 -Maximum 9999) }
if ($Code -eq '') {
    $chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
    $parts = @()
    for ($g = 0; $g -lt 4; $g++) {
        $s = ''
        for ($i = 0; $i -lt 7; $i++) { $s += $chars[(Get-Random -Maximum $chars.Length)] }
        $parts += $s
    }
    $Code = $parts -join '-'
}

# ---------- 5. 写注册表（备份原值） ----------
New-Item -Path $RegRoot -Force | Out-Null
$oldR = (Get-ItemProperty -Path $RegRoot -Name RN -ErrorAction SilentlyContinue).RN
$oldC = (Get-ItemProperty -Path $RegRoot -Name RC -ErrorAction SilentlyContinue).RC
if ($BackupPath -eq '') {
    $BackupPath = Join-Path $env:TEMP 'uninstall-tool-keygen\registry-backup.txt'
}
$bakDir = Split-Path -Parent $BackupPath
if (-not (Test-Path -LiteralPath $bakDir)) {
    New-Item -ItemType Directory -Path $bakDir -Force | Out-Null
    Log "已创建备份目录: $bakDir"
}
"RN=$oldR`r`nRC=$oldC" | Set-Content -Path $BackupPath -Encoding UTF8
Log "注册表原值已备份 -> $BackupPath"

Set-ItemProperty -Path $RegRoot -Name RN -Value $Name -Type String
Set-ItemProperty -Path $RegRoot -Name RC -Value $Code -Type String

# 复读校验
$rn2 = (Get-ItemProperty -Path $RegRoot -Name RN).RN
$rc2 = (Get-ItemProperty -Path $RegRoot -Name RC).RC
if ($rn2 -ne $Name -or $rc2 -ne $Code) { throw '注册表复读校验失败！' }
Log "注册表已写入: RN=$Name / RC=$Code（复读校验通过）"

# ---------- 完成 ----------
Write-Host ''
Write-Host '========== 一键激活完成 =========='
Write-Host ("  补丁 exe : " + $ExePath)
Write-Host ("  原件备份 : " + [System.IO.Path]::ChangeExtension($ExePath, '.orig.exe'))
Write-Host ("  注册名   : " + $Name)
Write-Host ("  注册码   : " + $Code)
Write-Host ("  注册表   : " + $RegRoot)
Write-Host '重启 项目E 后生效（About 显示已授权）。'
Write-Host '==================================='
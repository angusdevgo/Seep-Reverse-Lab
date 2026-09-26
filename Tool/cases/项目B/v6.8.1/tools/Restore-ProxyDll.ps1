# ============================================================================
#  项目B 本地化守护 —— 一键还原（移除代理 DLL，恢复原始状态）
#
#  用法：
#    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Restore-ProxyDll.ps1
#    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Restore-ProxyDll.ps1 -RestoreConfig
#    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Restore-ProxyDll.ps1 -BackupDir <路径>
#
#  行为：
#    ① 删除代理 sentry.dll / version.dll 及 version_orig.dll
#    ② 由 sentry_orig.dll 恢复原始 sentry.dll（哈希须回到原始值）
#    ③ 可选 -RestoreConfig：从备份恢复 configs\main\*.json
#    ④ 校验三个 EXE 的 SHA-256 是否回到标定基线
# ============================================================================
[CmdletBinding()]
param(
    [string]$项目BRoot = '<安装目录>',
    [string]$BackupDir = '',
    [switch]$RestoreConfig,
    [switch]$KeepLogs,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$nx     = Join-Path $项目BRoot 'nx_main'
$cfgDir = Join-Path $项目BRoot 'configs\main'

function Info($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[x] $m" -ForegroundColor Red; exit 1 }
function Get-Sha256($p) {
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower()
}

$BASE = @{
    '项目BNxMain.exe'         = 'f1f507b9fa2a43f47369904a08ff65fd18b9d61282a9e1b91eed3e976464510b'
    '项目BNxService.exe'      = '0db8d342c983b597098b7d56c05a4f3631184197f6b0114b49c66d2a514e5fdd'
    '项目BRemoteService.exe'  = '37b8bd6da12a8b08adadd0d7145453e2b7e92d17087717bb64343b98c3454d6d'
}

Write-Host "`n===== 项目B 本地化守护 · 还原 =====`n" -ForegroundColor White

# ---------------------------------------------------------------- ① 预检
Info "预检：项目B 进程 / 服务"
$procs = @('项目BNxMain','项目BNxService','项目BNxLauncher','项目BRemoteService',
           '项目BRemoteBackend','项目BRemoteHealthd','项目BNxUpdater','项目BManager')
$running = @()
foreach ($p in $procs) {
    if (Get-Process -Name $p -ErrorAction SilentlyContinue) { $running += $p }
}
if ($running.Count -gt 0) {
    if (-not $Force) { Die ("以下进程仍在运行，请先完全退出 项目B：" + ($running -join ', ')) }
    Warn ("强制模式：以下进程仍在运行 -> " + ($running -join ', '))
}

# 未指定备份目录时自动选最近一次
if (-not $BackupDir) {
    $bakRoot = Join-Path $项目BRoot 'backup_proxy_guard'
    if (Test-Path -LiteralPath $bakRoot) {
        $latest = Get-ChildItem -LiteralPath $bakRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
        if ($latest) { $BackupDir = $latest.FullName }
    }
}
if ($BackupDir -and (Test-Path -LiteralPath $BackupDir)) {
    Ok "使用备份目录：$BackupDir"
} else {
    Warn "未找到备份目录，将仅依赖 sentry_orig.dll 就地恢复"
}

# ---------------------------------------------------------------- ② 移除代理
Info "移除代理 DLL"
foreach ($f in @('sentry.dll','version.dll')) {
    $p = Join-Path $nx $f
    if (Test-Path -LiteralPath $p) {
        $sha = Get-Sha256 $p
        $isProxy = $false
        if ($BackupDir -and (Test-Path -LiteralPath (Join-Path $BackupDir 'manifest.json'))) {
            $mf = Get-Content -LiteralPath (Join-Path $BackupDir 'manifest.json') -Raw | ConvertFrom-Json
            if ($f -eq 'sentry.dll'  -and $sha -eq $mf.proxy_sentry_sha)  { $isProxy = $true }
            if ($f -eq 'version.dll' -and $sha -eq $mf.proxy_version_sha) { $isProxy = $true }
        }
        if ($isProxy) {
            Remove-Item -LiteralPath $p -Force
            Ok "已删除代理 $f"
        } else {
            Warn "$f 的哈希与代理产物不符，可能不是本方案放置的，**未删除**"
        }
    } else {
        Info "$f 不存在，跳过"
    }
}

$verOrig = Join-Path $nx 'version_orig.dll'
if (Test-Path -LiteralPath $verOrig) { Remove-Item -LiteralPath $verOrig -Force; Ok "已删除 version_orig.dll" }

# ---------------------------------------------------------------- ③ 恢复 sentry.dll
Info "恢复原始 sentry.dll"
$sentriOrig = Join-Path $nx 'sentry_orig.dll'
$sentriDst  = Join-Path $nx 'sentry.dll'
if (Test-Path -LiteralPath $sentriOrig) {
    Move-Item -LiteralPath $sentriOrig -Destination $sentriDst -Force
    Ok "sentry_orig.dll -> sentry.dll"
} elseif ($BackupDir -and (Test-Path -LiteralPath (Join-Path $BackupDir 'nx_main\sentry.dll'))) {
    Copy-Item -LiteralPath (Join-Path $BackupDir 'nx_main\sentry.dll') -Destination $sentriDst -Force
    Ok "已从备份恢复 sentry.dll"
} else {
    Warn "既无 sentry_orig.dll 也无备份，sentry.dll 缺失 —— 请修复 项目B 安装"
}

# ---------------------------------------------------------------- ④ 可选：恢复配置
if ($RestoreConfig) {
    $cfgBak = if ($BackupDir) { Join-Path $BackupDir 'configs_main' } else { '' }
    if ($cfgBak -and (Test-Path -LiteralPath $cfgBak)) {
        Info "恢复 configs\main\*.json"
        Copy-Item -Path (Join-Path $cfgBak '*.json') -Destination $cfgDir -Force
        Ok "配置已恢复"
    } else {
        Warn "备份目录内无 configs_main，跳过配置恢复"
    }
}

if (-not $KeepLogs) {
    foreach ($lg in @('项目B_guard_sentry.log','项目B_guard_version.log')) {
        $p = Join-Path $nx $lg
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; Info "已删除日志 $lg" }
    }
}

# ---------------------------------------------------------------- ⑤ 校验
Write-Host ""
Info "校验：EXE 哈希是否回到标定基线"
$allOk = $true
foreach ($name in $BASE.Keys) {
    $p = Join-Path $nx $name
    $h = Get-Sha256 $p
    $sig = (Get-AuthenticodeSignature -LiteralPath $p).Status
    if ($h -eq $BASE[$name]) {
        Ok ("{0,-24} HASH=OK  SIG={1}" -f $name, $sig)
    } else {
        Warn ("{0,-24} HASH=MISMATCH  actual={1}  SIG={2}" -f $name, $h, $sig)
        $allOk = $false
    }
}

if (Test-Path -LiteralPath (Join-Path $nx 'sentry.dll')) {
    $s = Get-Sha256 (Join-Path $nx 'sentry.dll')
    if ($BackupDir -and (Test-Path -LiteralPath (Join-Path $BackupDir 'manifest.json'))) {
        $mf = Get-Content -LiteralPath (Join-Path $BackupDir 'manifest.json') -Raw | ConvertFrom-Json
        if ($s -eq $mf.sentry_dll) { Ok "sentry.dll 已回到原始哈希" }
        else { Warn "sentry.dll 哈希 $s 与备份记录 $($mf.sentry_dll) 不一致" }
    }
}

Write-Host ""
if ($allOk) { Ok "还原完成：三个 EXE 哈希全部回到标定基线，官方签名有效。" }
else        { Warn "还原完成，但存在哈希不一致项，请人工复核。" }

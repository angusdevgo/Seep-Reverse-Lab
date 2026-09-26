# ============================================================================
#  项目B 本地化守护 —— 一键部署（DLL 代理运行时热补丁）
#
#  用法：
#    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Deploy-ProxyDll.ps1
#    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Deploy-ProxyDll.ps1 -Force
#
#  行为：
#    ① 预检：确认 项目B 相关进程/服务已退出；确认目标 EXE 哈希与标定基线一致
#    ② 备份：原始 sentry.dll + configs\main\*.json + 三 EXE 哈希清单
#    ③ 部署：sentry.dll → sentry_orig.dll（保原名转发）；放置两个代理 DLL
#    ④ 不改写任何 EXE 本体，官方 Authenticode 签名 100% 保留
# ============================================================================
[CmdletBinding()]
param(
    [string]$项目BRoot = '<安装目录>',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$root    = Split-Path -Parent $here
$nx      = Join-Path $项目BRoot 'nx_main'
$cfgDir  = Join-Path $项目BRoot 'configs\main'
$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$bakDir  = Join-Path $项目BRoot ("backup_proxy_guard\$stamp")

function Info($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[x] $m" -ForegroundColor Red; exit 1 }

function Get-Sha256($p) {
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower()
}

# ---------------------------------------------------------------- 基线
$BASE = @{
    '项目BNxMain.exe'         = 'f1f507b9fa2a43f47369904a08ff65fd18b9d61282a9e1b91eed3e976464510b'
    '项目BNxService.exe'      = '0db8d342c983b597098b7d56c05a4f3631184197f6b0114b49c66d2a514e5fdd'
    '项目BRemoteService.exe'  = '37b8bd6da12a8b08adadd0d7145453e2b7e92d17087717bb64343b98c3454d6d'
}

Write-Host "`n===== 项目B 本地化守护 · 部署 =====`n" -ForegroundColor White

# ---------------------------------------------------------------- ① 预检
Info "预检：项目B 进程 / 服务"
$procs = @('项目BNxMain','项目BNxService','项目BNxLauncher','项目BRemoteService',
           '项目BRemoteBackend','项目BRemoteHealthd','项目BNxUpdater','项目BManager')
$running = @()
foreach ($p in $procs) {
    $q = Get-Process -Name $p -ErrorAction SilentlyContinue
    if ($q) { $running += $p }
}
if ($running.Count -gt 0) {
    if (-not $Force) { Die ("以下进程仍在运行，请先完全退出 项目B：" + ($running -join ', ')) }
    Warn ("强制模式：以下进程仍在运行 -> " + ($running -join ', '))
}

Info "预检：目标 EXE 哈希与标定基线比对"
$hashOk = $true
$exeHashes = @{}
foreach ($name in $BASE.Keys) {
    $p = Join-Path $nx $name
    if (-not (Test-Path -LiteralPath $p)) { Die "缺少目标文件：$p" }
    $h = Get-Sha256 $p
    $exeHashes[$name] = $h
    if ($h -ne $BASE[$name]) {
        Warn "哈希不一致：$name`n      期望 $($BASE[$name])`n      实际 $h"
        $hashOk = $false
    } else {
        Ok "哈希一致：$name"
    }
}
if (-not $hashOk -and -not $Force) {
    Die "目标 EXE 与标定基线不符（可能已升级或已被其它补丁污染）。点位 RVA 将失效，拒绝部署。加 -Force 可强制继续。"
}

Info "预检：代理产物"
$srcSentry  = Join-Path $root 'dist\sentry.dll'
$srcVersion = Join-Path $root 'dist\version.dll'
foreach ($f in @($srcSentry, $srcVersion)) {
    if (-not (Test-Path -LiteralPath $f)) { Die "缺少代理产物：$f（请先运行 build.ps1）" }
}
Ok "sentry.dll  = $((Get-Item $srcSentry).Length) bytes"
Ok "version.dll = $((Get-Item $srcVersion).Length) bytes"

# ---------------------------------------------------------------- ② 备份
Info "备份到 $bakDir"
New-Item -ItemType Directory -Force -Path $bakDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bakDir 'nx_main') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bakDir 'configs_main') | Out-Null

$origSentry = Join-Path $nx 'sentry.dll'
Copy-Item -LiteralPath $origSentry -Destination (Join-Path $bakDir 'nx_main\sentry.dll') -Force
Ok "已备份 nx_main\sentry.dll ($((Get-Item $origSentry).Length) bytes)"

if (Test-Path -LiteralPath $cfgDir) {
    Copy-Item -Path (Join-Path $cfgDir '*.json') -Destination (Join-Path $bakDir 'configs_main') -Force -ErrorAction SilentlyContinue
    $n = (Get-ChildItem -Path (Join-Path $bakDir 'configs_main') -Filter *.json).Count
    Ok "已备份 configs\main\*.json ($n 个)"
}

$manifest = [ordered]@{
    timestamp   = $stamp
    项目B_root   = $项目BRoot
    exe_hashes  = $exeHashes
    sentry_dll  = Get-Sha256 $origSentry
    proxy_sentry_sha  = Get-Sha256 $srcSentry
    proxy_version_sha = Get-Sha256 $srcVersion
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $bakDir 'manifest.json') -Encoding UTF8
Ok "已写入 manifest.json"

# ---------------------------------------------------------------- ③ 部署
Info "部署 sentry.dll 代理（Main + Service）"
$sentriOrig = Join-Path $nx 'sentry_orig.dll'
if (Test-Path -LiteralPath $sentriOrig) {
    Warn "sentry_orig.dll 已存在，跳过改名（沿用现有真实 DLL）"
} else {
    Move-Item -LiteralPath $origSentry -Destination $sentriOrig -Force
    Ok "sentry.dll -> sentry_orig.dll"
}
Copy-Item -LiteralPath $srcSentry -Destination $origSentry -Force
Ok "已放置代理 sentry.dll"

Info "部署 version.dll 代理（RemoteService）"
$sysVersion = Join-Path $env:SystemRoot 'System32\version.dll'
$verOrig    = Join-Path $nx 'version_orig.dll'
if (-not (Test-Path -LiteralPath $verOrig)) {
    Copy-Item -LiteralPath $sysVersion -Destination $verOrig -Force
    Ok "已放置真实 version_orig.dll（来自 $sysVersion）"
} else {
    Warn "version_orig.dll 已存在，跳过"
}
Copy-Item -LiteralPath $srcVersion -Destination (Join-Path $nx 'version.dll') -Force
Ok "已放置代理 version.dll"

# ---------------------------------------------------------------- ④ 结果
Write-Host ""
Ok "部署完成。EXE 本体未被修改，官方签名保持有效："
foreach ($name in $BASE.Keys) {
    $p = Join-Path $nx $name
    $sig = (Get-AuthenticodeSignature -LiteralPath $p).Status
    Write-Host ("      {0,-24} {1}" -f $name, $sig)
}
Write-Host ""
Write-Host "日志文件（运行后生成）：" -ForegroundColor White
Write-Host "      $nx\项目B_guard_sentry.log"
Write-Host "      $nx\项目B_guard_version.log"
Write-Host ""
Write-Host "还原：powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Restore-ProxyDll.ps1" -ForegroundColor Green
Write-Host "备份目录：$bakDir" -ForegroundColor Green

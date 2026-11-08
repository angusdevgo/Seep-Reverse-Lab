#requires -Version 5
<#
.SYNOPSIS
    frida-dexdump —— 加壳 APK 的内存脱壳驱动（拿到真实 DEX 再回 JADX）。

.DESCRIPTION
    壳可以在磁盘上加密 DEX，但 App 要跑起来，DEX 必须在内存里解密成标准格式。
    frida-dexdump 在进程内存里暴力扫描 DEX magic（`dex\n035/037/038/039`），
    把解密后的真实 DEX 全部捞到本地，随后直接丢进 JADX 就能看到业务代码。

    典型触发时机（由 APKiD 判定）：
      - ApKiD 报 `packer: DexGuard` / `protector: xxx壳`
      - JADX 打开只有壳存根类（`StubApp`、`d_shell`、`Shell`、`ProxyApplication`…）
      - 类数量与 APK 体积严重不符

    前置条件：
      - 目标设备（真机 / 模拟器）已 `adb` 连通且已 root
      - 设备上 frida-server 正在运行，且**版本必须与本机 frida 一致**
        本机 frida：见脚本末尾自动打印；不匹配时脚本会给出推送命令

.PARAMETER Package
    目标包名（推荐），如 `com.example.app`。

.PARAMETER AppName
    目标进程名（包名与进程名不一致时用）。与 -Package 二选一。

.PARAMETER OutDir
    DEX 落地目录，默认 `.\dexdump_<包名>\`。

.PARAMETER Spawn
    以 spawn 方式冷启动目标再脱壳（**脱壳强烈推荐**，能抓到启动期解密的全量 DEX）。

.PARAMETER DeepSearch
    深度搜索模式，内存全量扫描，慢但更彻底。

.PARAMETER SleepSeconds
    spawn 后等待秒数（默认 frida-dexdump 自带 5s；加固壳首包解密慢可调到 10~15）。

.PARAMETER DeviceSerial
    多设备时指定 adb serial（对应 frida `-D`）。

.EXAMPLE
    powershell -File Tool\scripts\android\frida-dexdump-run.ps1 -Package com.example.app -Spawn

.EXAMPLE
    powershell -File Tool\scripts\android\frida-dexdump-run.ps1 -Package com.example.app -Spawn -DeepSearch -SleepSeconds 12
#>
[CmdletBinding(DefaultParameterSetName = 'Package')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Package')]
    [string]$Package,

    [Parameter(Mandatory = $true, ParameterSetName = 'AppName')]
    [string]$AppName,

    [string]$OutDir,
    [switch]$Spawn,
    [switch]$DeepSearch,
    [int]$SleepSeconds = 0,
    [string]$DeviceSerial
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

. (Join-Path $PSScriptRoot '..\lib\AndroidToolbox.ps1')

$adb = Resolve-AndroidTool -Name 'adb'
$frida = Resolve-AndroidTool -Name 'frida'
$fridaPs = Resolve-AndroidTool -Name 'frida-ps'
$dexDump = Resolve-AndroidTool -Name 'frida-dexdump'

foreach ($pair in @(@('adb', $adb), @('frida', $frida), @('frida-ps', $fridaPs), @('frida-dexdump', $dexDump))) {
    if (-not $pair[1]) {
        throw "$($pair[0]) 未就绪。请先执行：powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1"
    }
}

$targetLabel = if ($PSCmdlet.ParameterSetName -eq 'Package') { $Package } else { $AppName }
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path (Get-Location).Path ("dexdump_" + ($targetLabel -replace '[^A-Za-z0-9._-]', '_'))
}
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

# ---------------------------------------------------------------------------
# 1. 设备连通性
# ---------------------------------------------------------------------------
Write-Host "== [1/3] 设备连通性 ==" -ForegroundColor Cyan
$adbArgs = @('devices')
$devOut = & $adb @adbArgs 2>&1 | Out-String
Write-Host $devOut.Trim() -ForegroundColor DarkGray

$deviceLines = @($devOut -split "`r?`n" | Where-Object { $_ -match '\tdevice$' })
if ($deviceLines.Count -eq 0) {
    throw "无在线 adb 设备。请先启动模拟器 / 连接真机并确认 'adb devices' 有 device 状态（非 unauthorized / offline）"
}
Write-Host "  在线设备数: $($deviceLines.Count)" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. frida-server 与版本一致性
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "== [2/3] frida-server 检查 ==" -ForegroundColor Cyan
$hostVer = (& $frida --version 2>&1 | Out-String).Trim()
Write-Host "  本机 frida: $hostVer"

$psArgs = @()
if ($DeviceSerial) { $psArgs += @('-D', $DeviceSerial) } else { $psArgs += '-U' }
$psArgs += '-ai'
$psOut = (& $fridaPs @psArgs 2>&1 | Out-String)
if ($psOut -match 'Failed to|unable to|error|Error|timed out|not found') {
    Write-Host "  [警告] 未能从设备枚举进程（frida-server 可能未运行或版本不匹配）" -ForegroundColor Yellow
    Write-Host "        首次枚举输出：$((($psOut -split "`r?`n")[0]))" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  修复参考（版本必须与 $hostVer 完全一致）：" -ForegroundColor Yellow
    Write-Host "    1) 下载 frida-server-$hostVer-android-arm64.xz 解压后推送："
    Write-Host "       adb push frida-server-$hostVer-android-arm64 /data/local/tmp/frida-server"
    Write-Host "       adb shell `"su -c 'chmod 755 /data/local/tmp/frida-server'`""
    Write-Host "       adb shell `"su -c '/data/local/tmp/frida-server &'`""
    Write-Host "    2) 或直接：pip install frida-tools==<与设备端匹配的版本>"
    Write-Host "    3) 模拟器（MuMu / 夜神）建议用对应架构的 frida-server，x86_64 与 arm64 不要混用"
    Write-Host ""
    $ans = Read-Host "  仍要继续尝试脱壳吗? [y/N]"
    if ($ans -notmatch '^(y|Y)') { return }
}
else {
    $procCount = @($psOut -split "`r?`n" | Where-Object { $_.Trim() -ne '' }).Count
    Write-Host "  frida-server 可用（枚举到 $procCount 行进程信息）" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 3. 执行脱壳
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "== [3/3] 开始脱壳 ==" -ForegroundColor Cyan
$ddArgs = @()
if ($DeviceSerial) { $ddArgs += @('-D', $DeviceSerial) } else { $ddArgs += '-U' }

if ($Spawn) {
    if ($PSCmdlet.ParameterSetName -eq 'Package') { $ddArgs += @('-f', $Package) }
    else { $ddArgs += @('-f', $AppName) }
    if ($SleepSeconds -gt 0) { $ddArgs += @('--sleep', "$SleepSeconds") }
}
else {
    if ($PSCmdlet.ParameterSetName -eq 'Package') { $ddArgs += @('-n', $Package) }
    else { $ddArgs += @('-n', $AppName) }
}
$ddArgs += @('-o', $OutDir)
if ($DeepSearch) { $ddArgs += '-d' }

Write-Host "  命令: frida-dexdump $($ddArgs -join ' ')" -ForegroundColor DarkGray
Write-Host "  （加固壳首包解密需要时间；若只拿到壳 DEX，改用 -Spawn -SleepSeconds 12 -DeepSearch）" -ForegroundColor DarkGray
Write-Host ""

Invoke-AndroidNative -Exe $dexDump -Arguments $ddArgs

Write-Host ""
$dexFiles = @(Get-ChildItem -LiteralPath $OutDir -Recurse -File -Filter '*.dex' -ErrorAction SilentlyContinue)
if ($dexFiles.Count -eq 0) {
    Write-Warning "未产出任何 DEX。排查顺序：frida-server 版本 → 是否被反调试拦截 → 试 -Spawn -DeepSearch"
    return
}

Write-Host "[产物] 共 $($dexFiles.Count) 个 DEX：" -ForegroundColor Green
$dexFiles | Sort-Object Length -Descending | ForEach-Object {
    Write-Host ("  {0,-28} {1,8:N2} MB" -f $_.Name, ($_.Length / 1MB))
}
Write-Host ""
Write-Host "下一步：把最大的那个 DEX 拖进 JADX-GUI，或直接：" -ForegroundColor Cyan
Write-Host "  jadx -d <输出目录> $($dexFiles[0].FullName)"

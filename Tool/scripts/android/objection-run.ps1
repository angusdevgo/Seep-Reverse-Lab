#requires -Version 5
<#
.SYNOPSIS
    objection —— 运行时自动化（SSL Pinning 绕过 / Root 检测绕过 / 内存对象枚举）。

.DESCRIPTION
    objection 是 Frida 的"成品命令行封装"：不用写一行 JS 就能完成 Android 动态审计里
    最高频的五个动作。本脚本负责：设备/服务自检 → 拉起 objection REPL → 打印速查卡。

    五个最高频动作（在 objection REPL 里直接敲）：
      android sslpinning disable      # 关 SSL Pinning / 证书校验（抓包第一步）
      android root disable            # 关 root 检测
      android root simulate           # 伪装成已 root（部分目标逻辑反着写）
      android hooking list classes    # 枚举已加载类（找鉴权类）
      android hooking watch class_method <类>.<方法> --dump-args --dump-return --dump-backtrace
      env                             # 看当前 App 数据目录 / 沙盒路径
      memory list modules             # 已加载 SO（确认壳有没有解出真身）

.PARAMETER Package
    目标包名（attach 已运行进程）。

.PARAMETER Spawn
    冷启动目标再挂载（能抓住启动期的一次性校验）。

.PARAMETER DeviceId
    多设备时指定 frida 设备 ID。

.PARAMETER Command
    不进 REPL，直接执行一条 objection 命令后退出（便于自动化/取证）。

.EXAMPLE
    powershell -File Tool\scripts\android\objection-run.ps1 -Package com.example.app

.EXAMPLE
    powershell -File Tool\scripts\android\objection-run.ps1 -Package com.example.app -Spawn -Command "android sslpinning disable"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Package,

    [switch]$Spawn,
    [string]$DeviceId,
    [string]$Command
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

. (Join-Path $PSScriptRoot '..\lib\AndroidToolbox.ps1')

$objection = Resolve-AndroidTool -Name 'objection'
$adb = Resolve-AndroidTool -Name 'adb'
if (-not $objection) {
    throw "objection 未安装。请先执行：powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1 -Only frida"
}

Write-Host "== objection 速查卡 ==" -ForegroundColor Cyan
Write-Host "  android sslpinning disable               抓包第一步：关证书固定"
Write-Host "  android root disable                     关 root / 越狱检测"
Write-Host "  android hooking list classes             枚举已加载类"
Write-Host "  android hooking watch class_method <C>.<m> --dump-args --dump-return --dump-backtrace"
Write-Host "  memory list modules                      已加载 SO（判断壳是否已解出）"
Write-Host "  env                                      沙盒路径 / 数据目录"
Write-Host ""

if ($adb) {
    $devOut = & $adb devices 2>&1 | Out-String
    if (-not ($devOut -match '\tdevice$')) {
        Write-Warning "adb 无在线设备。objection 仍会尝试 USB 直连，如失败请先启动模拟器/真机。"
    }
}

$argList = @()
if ($DeviceId) { $argList += @('-S', $DeviceId) }
$argList += @('-n', $Package)
if ($Spawn) { $argList += @('-s', '-p') }

if (-not [string]::IsNullOrWhiteSpace($Command)) {
    # 一次性执行：objection ... run <命令>，不进 REPL
    $argList += @('run', $Command)
    Write-Host "执行: objection $($argList -join ' ')" -ForegroundColor DarkGray
    Invoke-AndroidNative -Exe $objection -Arguments $argList
    return
}

Write-Host "进入 REPL（输入 exit 退出）..." -ForegroundColor Green
# REPL 是交互式 TUI，必须直连终端，不能包在管道里
& $objection @argList @('start', '-s', 'android sslpinning disable') 2>&1

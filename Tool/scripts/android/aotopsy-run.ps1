#requires -Version 5
<#
.SYNOPSIS
    Aotopsy —— Flutter / Dart AOT（libapp.so）静态分析驱动脚本。

.DESCRIPTION
    Flutter 应用的业务逻辑、签名密钥、API 路由全在 `lib/app.so`（Dart AOT Snapshot）里，
    JADX 打开只能看到 Flutter 引擎壳。Aotopsy 直接解析 Snapshot 二进制语法，
    无 VM、无 SDK 编译即可还原：

      - 函数名 / 类结构 / 字段偏移 / 继承链
      - 直接与间接调用边（BL / BLR）
      - 字符串引用（哪个函数加载了哪个字符串 ← 找签名密钥的关键）
      - 行为信号（crypto / network / webview / blockchain …）
      - Dart 伪代码与整个项目的 .dart 源码重建

    本脚本把"APK → 抽 libapp.so → 分析"这条链一次跑通，避免手写解压与路径推断。

.PARAMETER Target
    APK 路径，或已抽出的 libapp.so 路径。

.PARAMETER Action
    find-libapp  定位 APK 内的 Dart AOT 库并报告 Dart 版本（默认，最快，先跑这个）
    doctor       快诊：Dart 版本 / 指针宽度 / 是否支持
    signal       全管线：反汇编 + 调用边 + 行为信号
    export-dart  重建整个 Dart 源码工程（最慢，产出最多）
    strings      字符串检索（需配合 -Find）
    decompile    原生反编译（需 -Find 或 -Func）
    extract      仅把 libapp.so 抽到 -OutDir，不做分析

.PARAMETER OutDir
    输出目录。默认在原文件同级目录下 `<basename>.aotopsy/`。

.PARAMETER Find
    按名字过滤（类名 / 方法名 / 字符串内容），如 `-Find X-Signature`、`-Find sign`。

.PARAMETER Func
    直接反编译某个函数地址（VA），如 `-Func 0x1a92728`。

.PARAMETER Decompile
    signal 动作下额外输出逐函数 Dart 伪代码（体积约为默认的 3 倍）。

.PARAMETER Graph
    signal 动作下额外生成调用图与 CFG 的 DOT 文件。

.EXAMPLE
    powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action find-libapp

.EXAMPLE
    powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action signal -Decompile

.EXAMPLE
    powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action strings -Find "Signature"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    [ValidateSet('find-libapp', 'doctor', 'signal', 'export-dart', 'strings', 'decompile', 'extract')]
    [string]$Action = 'find-libapp',

    [string]$OutDir,
    [string]$Find,
    [string]$Func,
    [switch]$Decompile,
    [switch]$Graph,
    [switch]$AppOnly
)

Set-StrictMode -Version Latest
# 注意：aotopsy / frida / apkid 会把正常进度输出写到 stderr（并带 ANSI 颜色），
# 因此这里必须用 Continue；真正的异常用显式 throw 抛。
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

. (Join-Path $PSScriptRoot '..\lib\AndroidToolbox.ps1')

$aotopsy = Resolve-AndroidTool -Name 'aotopsy'
if (-not $aotopsy) {
    throw "Aotopsy 未部署。请先执行：powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1 -Only aotopsy"
}

$targetFull = (Resolve-Path -LiteralPath $Target).Path
$leaf = [System.IO.Path]::GetFileNameWithoutExtension($targetFull)
$baseDir = Split-Path -Parent $targetFull
if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path $baseDir "$leaf.aotopsy" }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

function Test-IsApk {
    param([string]$Path)
    return ($Path.ToLowerInvariant().EndsWith('.apk') -or $Path.ToLowerInvariant().EndsWith('.aab') -or $Path.ToLowerInvariant().EndsWith('.apks'))
}

# ---------------------------------------------------------------------------
# 1. APK 场景：先定位 libapp.so
# ---------------------------------------------------------------------------
$libPath = $targetFull
$libappJson = $null

if (Test-IsApk -Path $targetFull) {
    Write-Host "[find-libapp] 扫描 APK 内的 Dart AOT 库 ..." -ForegroundColor Cyan
    Invoke-AndroidNative -Exe $aotopsy -Arguments @('find-libapp', '-apk', $targetFull, '-out', $OutDir)

    $jsonFile = Get-ChildItem -LiteralPath $OutDir -Filter '*_find_libapp.json' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $jsonFile) {
        throw "Aotopsy 未生成 find_libapp.json，无法定位 libapp.so（该 APK 可能不是 Flutter 应用）"
    }
    $libappJson = Get-Content -LiteralPath $jsonFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json

    if (-not $libappJson.found) {
        Write-Warning "该 APK 未检出 Dart AOT 快照（不是 Flutter，或已被加固剥离）"
        Write-Host "  reason: $($libappJson.reason)"
        return
    }

    Write-Host ""
    Write-Host "[命中] $($libappJson.best.path_in_apk)" -ForegroundColor Green
    Write-Host "        Dart 版本 : $($libappJson.best.dart_version)"
    Write-Host "        Snapshot  : $($libappJson.best.snapshot_hash)"
    Write-Host "        SHA256    : $($libappJson.best.sha256)"
    Write-Host "        Size      : $([math]::Round($libappJson.best.size / 1MB, 2)) MB"
    Write-Host ""

    if ($Action -eq 'find-libapp') { return }

    # 抽出 libapp.so
    $entryName = $libappJson.best.path_in_apk
    $libPath = Join-Path $OutDir 'libapp.so'
    if (-not (Test-Path -LiteralPath $libPath)) {
        Write-Host "[extract] 抽出 $entryName -> $libPath" -ForegroundColor Cyan
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [System.IO.Compression.ZipFile]::OpenRead($targetFull)
        try {
            $entry = $zip.Entries | Where-Object { $_.FullName -eq $entryName } | Select-Object -First 1
            if (-not $entry) { throw "APK 内未找到条目: $entryName" }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $libPath, $true)
        }
        finally { $zip.Dispose() }
    }
}

if ($Action -eq 'extract') {
    Write-Host "[extract] libapp.so 就绪: $libPath" -ForegroundColor Green
    return
}

if (-not (Test-Path -LiteralPath $libPath)) { throw "目标不存在: $libPath" }

# ---------------------------------------------------------------------------
# 2. 按动作分发
# ---------------------------------------------------------------------------
switch ($Action) {
    'doctor' {
        Write-Host "[doctor] 快诊 libapp.so ..." -ForegroundColor Cyan
        Invoke-AndroidNative -Exe $aotopsy -Arguments @('doctor', $libPath)
    }

    'signal' {
        $sigArgs = @('signal', $libPath, '--out', (Join-Path $OutDir 'signal'))
        if ($Decompile) { $sigArgs += '--decompile' }
        if ($Graph) { $sigArgs += '--graph' }
        Write-Host "[signal] 全管线分析（可能需要数分钟）..." -ForegroundColor Cyan
        Invoke-AndroidNative -Exe $aotopsy -Arguments $sigArgs
        Write-Host ""
        Write-Host "[产物] $OutDir\signal" -ForegroundColor Green
        Write-Host "       functions.jsonl / call_edges.jsonl / classes.jsonl / string_refs.jsonl / signal.html"
    }

    'export-dart' {
        $edArgs = @('export-dart', '--lib', $libPath, '--out', (Join-Path $OutDir 'dart_src'))
        if ($AppOnly) { $edArgs += '--app-only' }
        if (-not [string]::IsNullOrWhiteSpace($Find)) { $edArgs += @('--filter', $Find) }
        Write-Host "[export-dart] 重建 Dart 源码工程（最慢，耐心等）..." -ForegroundColor Cyan
        Invoke-AndroidNative -Exe $aotopsy -Arguments $edArgs
        Write-Host ""
        Write-Host "[产物] $OutDir\dart_src" -ForegroundColor Green
    }

    'strings' {
        if ([string]::IsNullOrWhiteSpace($Find)) { throw "action=strings 需要 -Find <关键词>" }
        Write-Host "[strings] 检索 '$Find' 及其引用函数 ..." -ForegroundColor Cyan
        Invoke-AndroidNative -Exe $aotopsy -Arguments @('_debug', 'strings', '--lib', $libPath, '--find', $Find, '--xref')
    }

    'decompile' {
        $dcArgs = @('_debug', 'decompile-native', '--lib', $libPath)
        if (-not [string]::IsNullOrWhiteSpace($Func)) { $dcArgs += @('--func', $Func) }
        elseif (-not [string]::IsNullOrWhiteSpace($Find)) { $dcArgs += @('--find', $Find) }
        else { throw "action=decompile 需要 -Find <类名/函数名> 或 -Func <0x地址>" }
        Write-Host "[decompile] 原生反编译 ..." -ForegroundColor Cyan
        Invoke-AndroidNative -Exe $aotopsy -Arguments $dcArgs
    }
}

Write-Host ""
Write-Host "提示：找签名密钥 / API 路由的最短路径 =" -ForegroundColor Cyan
Write-Host "  aotopsy-run.ps1 -Target app.apk -Action strings -Find `"X-Sign`"   # 定位字符串加载点"
Write-Host "  aotopsy-run.ps1 -Target app.apk -Action decompile -Find `"Sign`"    # 反编译相关函数"

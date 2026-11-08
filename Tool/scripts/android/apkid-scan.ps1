#requires -Version 5
<#
.SYNOPSIS
    APKiD 查壳 / 反调试 / 反模拟器 / 混淆器指纹扫描（Android 逆向第一道 Recon 门）。

.DESCRIPTION
    在啃代码之前先回答四个问题：
      1. 有没有加壳？哪家壳？(packer / protector)
      2. 有没有反调试 / 反模拟器？(anti_debug / anti_vm / anti_hook)
      3. 用什么混淆器？(obfuscator / compiler)
      4. 有没有可疑的资源操纵？(manipulator)

    这些结论直接决定后续路线：
      - 命中 packer/protector  → 先走 frida-dexdump 内存脱壳，别硬啃 JADX
      - 命中 anti_vm/anti_debug → 先走 objection / frida 环境伪装
      - 命中 Flutter 特征      → 转 aotopsy 分析 libapp.so

.PARAMETER ApkPath
    目标 APK / AAB / DEX / SO 路径，可传多个。

.PARAMETER OutDir
    把 JSON 原始结果落到该目录（默认不落盘）。

.PARAMETER Raw
    直接输出 APKiD 原生可读报告（默认输出结构化归类摘要）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Tool\scripts\android\apkid-scan.ps1 -ApkPath .\target.apk

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Tool\scripts\android\apkid-scan.ps1 -ApkPath .\target.apk -OutDir .\recon
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $false)]
    [string[]]$ApkPath,

    [string]$OutDir,

    [switch]$Raw
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

. (Join-Path $PSScriptRoot '..\lib\AndroidToolbox.ps1')

$apkid = Resolve-AndroidTool -Name 'apkid'
if (-not $apkid) {
    throw "APKiD 未安装。请先执行：powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1 -Only apkid"
}

$targets = @()
foreach ($p in $ApkPath) {
    $full = Resolve-Path -LiteralPath $p -ErrorAction SilentlyContinue
    if (-not $full) { throw "目标不存在: $p" }
    $targets += $full.Path
}

if (-not [string]::IsNullOrWhiteSpace($OutDir)) {
    if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
}

if ($Raw) {
    Invoke-AndroidNative -Exe $apkid -Arguments $targets
    return
}

foreach ($t in $targets) {
    Write-Host ""
    Write-Host "=== APKiD :: $(Split-Path -Leaf $t) ===" -ForegroundColor Cyan

    $jsonArgs = @('-j') + @($t)
    $rawText = (Invoke-AndroidNative -Exe $apkid -Arguments $jsonArgs -Quiet) -join "`n"
    # APKiD 可能把提示信息也混进 stdout，取第一个 '{'
    $start = $rawText.IndexOf('{')
    if ($start -lt 0) {
        Write-Warning "APKiD 未返回可解析 JSON，回落到原生输出："
        & $apkid @t 2>&1
        continue
    }
    $payload = $rawText.Substring($start).Trim()
    try { $doc = $payload | ConvertFrom-Json } catch {
        Write-Warning "APKiD JSON 解析失败：$_"
        Write-Output $payload
        continue
    }

    foreach ($f in $doc.files) {
        $name = $f.filename
        $short = if ($name -like '*!*') { ($name -split '!')[-1] } else { Split-Path -Leaf $name }
        if (-not $f.matches) {
            continue
        }
        Write-Host "  [$( $short )]" -ForegroundColor Yellow
        foreach ($prop in $f.matches.PSObject.Properties) {
            $vals = @($prop.Value) -join ', '
            Write-Host ("    {0,-14}: {1}" -f $prop.Name, $vals)
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($OutDir)) {
        $leaf = [System.IO.Path]::GetFileNameWithoutExtension($t)
        $outFile = Join-Path $OutDir "$leaf.apkid.json"
        $payload | Set-Content -LiteralPath $outFile -Encoding utf8
        Write-Host "  -> $outFile" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "判定指引：" -ForegroundColor Cyan
Write-Host "  packer / protector 命中  -> 先脱壳：Tool\scripts\android\frida-dexdump-run.ps1"
Write-Host "  anti_vm / anti_debug 命中 -> 先伪装环境：objection -g <pkg> explore  (android root disable)"
Write-Host "  Flutter 特征 / 无 Java 逻辑 -> 转 Flutter：Tool\scripts\android\aotopsy-run.ps1"

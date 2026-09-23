#Requires -Version 5.1
<#
  Seep 工作台 —— 工具修复器（可选）
  ----------------------------------------------------------------
  工具已随包内置在 Tool\mcp\Tool\safe\，正常无需运行本脚本。
  仅当内置工具损坏/缺失时，用本脚本重新下载。
  官方源优先，失败自动回退国内镜像。
#>
[CmdletBinding()]
param(
    [string[]]$Only = @(),          # 只装指定工具，如 -Only jadx,radare2
    [switch]$Force                  # 已存在也重新下载
)

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
# seep MCP 硬编码要求：TOOL_DIR = <脚本目录>/Tool → 工具必须落在 Tool\mcp\Tool\safe\
$ToolsDir  = Join-Path $Root 'Tool\mcp\Tool\safe'
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

$Mirrors = @(
    '',                                  # 官方源
    'https://ghproxy.net/',
    'https://gh-proxy.com/'
)

function Write-Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "    [!!] $m" -ForegroundColor Yellow }
function Write-Info($m) { Write-Host "    [..] $m" -ForegroundColor Gray }

# 带镜像回退的下载
function Get-FileWithMirror {
    param([string]$Url, [string]$OutFile)
    foreach ($m in $Mirrors) {
        $u = if ($m -eq '' -or $Url -notmatch '^https?://github') { $Url } else { "$m$Url" }
        $tag = if ($m -eq '') { 'official' } else { $m.TrimEnd('/') }
        try {
            Write-Info "尝试 $tag ..."
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $u -OutFile $OutFile -TimeoutSec 300 -UseBasicParsing
            if ((Test-Path $OutFile) -and (Get-Item $OutFile).Length -gt 1024) {
                Write-Ok "下载成功 ($tag)"
                return $true
            }
        } catch {
            Write-Info "失败: $($_.Exception.Message.Split([Environment]::NewLine)[0])"
        }
    }
    return $false
}

# 取 GitHub 最新 release 的 asset 下载地址
function Get-GitHubAsset {
    param([string]$Repo, [string]$Pattern)
    try {
        $api = "https://api.github.com/repos/$Repo/releases/latest"
        $rel = Invoke-RestMethod -Uri $api -TimeoutSec 60 -Headers @{ 'User-Agent' = 'seep-setup' }
        $asset = $rel.assets | Where-Object { $_.name -match $Pattern } | Select-Object -First 1
        if ($asset) { return @{ Url = $asset.browser_download_url; Name = $asset.name; Tag = $rel.tag_name } }
    } catch {
        Write-Warn "GitHub API 失败 ($Repo): $($_.Exception.Message.Split([Environment]::NewLine)[0])"
    }
    return $null
}

function Expand-ZipTo {
    param([string]$Zip, [string]$Dest)
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $Dest -Force
}

function Should-Run($name) {
    if ($Only.Count -eq 0) { return $true }
    return ($Only -contains $name)
}

$results = @{}

# ---------------------------------------------------------------- jadx
if (Should-Run 'jadx') {
    Write-Host "`n  [1/6] jadx (Java 反编译)" -ForegroundColor Cyan
    $dst = Join-Path $ToolsDir 'jadx'
    if ((Test-Path $dst) -and -not $Force) { Write-Ok '已存在，跳过'; $results['jadx'] = $true }
    else {
        $a = Get-GitHubAsset -Repo 'skylot/jadx' -Pattern '^jadx-[\d.]+\.zip$'
        if ($a) {
            $zip = Join-Path $env:TEMP $a.Name
            if (Get-FileWithMirror -Url $a.Url -OutFile $zip) {
                if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
                Expand-ZipTo -Zip $zip -Dest $dst
                Remove-Item $zip -Force -ErrorAction SilentlyContinue
                Write-Ok "jadx $($a.Tag) -> tools\jadx"
                $results['jadx'] = $true
            } else { Write-Warn 'jadx 下载失败'; $results['jadx'] = $false }
        } else { Write-Warn 'jadx: 无法获取 release 信息'; $results['jadx'] = $false }
    }
}

# ---------------------------------------------------------------- radare2
if (Should-Run 'radare2') {
    Write-Host "`n  [2/6] radare2 (二进制逆向)" -ForegroundColor Cyan
    $dst = Join-Path $ToolsDir 'radare2'
    if ((Test-Path $dst) -and -not $Force) { Write-Ok '已存在，跳过'; $results['radare2'] = $true }
    else {
        $a = Get-GitHubAsset -Repo 'radareorg/radare2' -Pattern '^radare2-.*-w64\.zip$'
        if ($a) {
            $zip = Join-Path $env:TEMP $a.Name
            if (Get-FileWithMirror -Url $a.Url -OutFile $zip) {
                if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
                Expand-ZipTo -Zip $zip -Dest $dst
                Remove-Item $zip -Force -ErrorAction SilentlyContinue
                Write-Ok "radare2 $($a.Tag) -> tools\radare2"
                $results['radare2'] = $true
            } else { Write-Warn 'radare2 下载失败'; $results['radare2'] = $false }
        } else { Write-Warn 'radare2: 无法获取 release 信息'; $results['radare2'] = $false }
    }
}

# ---------------------------------------------------------------- apktool
if (Should-Run 'apktool') {
    Write-Host "`n  [3/6] apktool (APK 解包/重打包)" -ForegroundColor Cyan
    $dst = Join-Path $ToolsDir 'apktool'
    if ((Test-Path $dst) -and -not $Force) { Write-Ok '已存在，跳过'; $results['apktool'] = $true }
    else {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        $a = Get-GitHubAsset -Repo 'iBotPeaches/Apktool' -Pattern '^apktool_[\d.]+\.jar$'
        if ($a) {
            $jar = Join-Path $dst 'apktool.jar'
            if (Get-FileWithMirror -Url $a.Url -OutFile $jar) {
                $bat = @'
@echo off
if "%JAVA_HOME%"=="" (set JAVA=java) else (set JAVA="%JAVA_HOME%\bin\java.exe")
%JAVA% -jar -Duser.language=en "%~dp0apktool.jar" %*
'@
                Set-Content -Path (Join-Path $dst 'apktool.bat') -Value $bat -Encoding ASCII
                Write-Ok "apktool $($a.Tag) -> tools\apktool"
                $results['apktool'] = $true
            } else { Write-Warn 'apktool 下载失败'; $results['apktool'] = $false }
        } else { Write-Warn 'apktool: 无法获取 release 信息'; $results['apktool'] = $false }
    }
}

# ---------------------------------------------------------------- playwright-mcp
if (Should-Run 'playwright-mcp') {
    Write-Host "`n  [4/6] playwright-mcp (浏览器自动化)" -ForegroundColor Cyan
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Warn '未找到 npm，跳过'; $results['playwright-mcp'] = $false
    } else {
        $dst = Join-Path $ToolsDir 'playwright-mcp'
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Push-Location $dst
        try {
            if (-not (Test-Path (Join-Path $dst 'package.json'))) {
                '{ "name": "playwright-mcp-local", "private": true }' | Set-Content -Path 'package.json' -Encoding UTF8
            }
            Write-Info 'npm install @playwright/mcp ...'
            & npm install '@playwright/mcp' --no-audit --no-fund 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Ok 'playwright-mcp -> tools\playwright-mcp'; $results['playwright-mcp'] = $true }
            else { Write-Warn 'npm install 失败（可改用 npx 方式）'; $results['playwright-mcp'] = $false }
        } finally { Pop-Location }
    }
}

# ---------------------------------------------------------------- js-reverse-mcp
if (Should-Run 'js-reverse-mcp') {
    Write-Host "`n  [5/6] js-reverse-mcp (JS 逆向)" -ForegroundColor Cyan
    # 官方推荐 npx 免安装方式：无需下载，仅在 mcp.json 注册即可
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Warn '未找到 npm，跳过（js-reverse-mcp 依赖 npx）'
        $results['js-reverse-mcp'] = $false
    } else {
        Write-Info 'js-reverse-mcp 采用官方推荐的 npx 方式（无需本地下载）'
        Write-Info '注册方式：mcp.json 中 command=npx, args=["js-reverse-mcp"]'
        Write-Info '可选本地安装：git clone https://github.com/zhizhuodemao/js-reverse-mcp + npm i + npm run build'
        Write-Ok 'js-reverse-mcp -> 走 npx（已在 mcp.json.template 中预置）'
        $results['js-reverse-mcp'] = $true
    }
}

# ---------------------------------------------------------------- ida-pro-mcp
if (Should-Run 'ida-pro-mcp') {
    Write-Host "`n  [6/6] ida-pro-mcp (IDA 桥接)" -ForegroundColor Cyan
    $dst = Join-Path $ToolsDir 'ida-pro-mcp'
    if ((Test-Path $dst) -and -not $Force) { Write-Ok '已存在，跳过'; $results['ida-pro-mcp'] = $true }
    else {
        Write-Info 'pip install ida-pro-mcp ...'
        & python -m pip install --quiet ida-pro-mcp 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Write-Ok 'ida-pro-mcp 已装入 Python 环境'
            Write-Info '（IDA 本体需你自备，见 MANUAL\IDA-PRO.md）'
            $results['ida-pro-mcp'] = $true
        } else { Write-Warn 'ida-pro-mcp 安装失败'; $results['ida-pro-mcp'] = $false }
    }
}

# ---------------------------------------------------------------- PATH
Write-Host "`n  [PATH] 加入工具目录" -ForegroundColor Cyan
$addPaths = @()
foreach ($p in @('radare2', 'jadx\bin', 'apktool')) {
    $full = Join-Path $ToolsDir $p
    if (Test-Path $full) { $addPaths += $full }
}
if ($addPaths.Count -gt 0) {
    $old = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = $old -split ';' | Where-Object { $_ -ne '' }
    $added = 0
    foreach ($p in $addPaths) {
        if ($parts -notcontains $p) { $parts += $p; $added++ }
    }
    if ($added -gt 0) {
        [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
        Write-Ok "已向用户 PATH 追加 $added 个目录（原 PATH 未备份，如需回滚请手动移除）"
    } else { Write-Ok 'PATH 已包含这些目录' }
} else { Write-Warn '未发现可加入 PATH 的目录' }

# ---------------------------------------------------------------- 汇总
Write-Host "`n  ---------- 工具下载汇总 ----------" -ForegroundColor White
foreach ($k in $results.Keys | Sort-Object) {
    $v = $results[$k]
    $mark = if ($v -eq $true) { '[OK]  ' } elseif ($v -eq $false) { '[FAIL]' } else { '[SKIP]' }
    Write-Host ("    {0} {1}" -f $mark, $k)
}

$failed = @($results.Keys | Where-Object { $results[$_] -eq $false })
if ($failed.Count -gt 0) {
    Write-Host "`n    失败项: $($failed -join ', ')" -ForegroundColor Yellow
    Write-Host '    可重跑本脚本，或按 MANUAL\PREREQUISITES.md 手动下载' -ForegroundColor Yellow
    exit 1
}
exit 0

#Requires -Version 5.1
<#
  install-web-scanners.ps1 —— Web 渗透扫描器安装器（nuclei / ffuf / whatweb）
  ----------------------------------------------------------------
  装什么：
    nuclei  ：模板化漏扫（CMS 配置错配 / 暴露备份 / Actuator / Swagger 泄露 / 技术指纹）
    ffuf    ：路径与参数爆破（找 api.php / 后台 / .env / 备份文件）
    whatweb ：CMS 指纹（**Ruby 脚本，无 Ruby 时自动跳过并给出替代方案**）

  装哪里：<root>\bin  （root 默认 D:\Tool\Web，可用 SEEP_WEB_TOOLBOX 覆盖）
  重复跑：已存在则跳过（-Force 强制重装）

  用法：
    powershell -File Tool\scripts\web\install-web-scanners.ps1
    powershell -File Tool\scripts\web\install-web-scanners.ps1 -CheckOnly
    powershell -File Tool\scripts\web\install-web-scanners.ps1 -Only nuclei
#>
[CmdletBinding()]
param(
    [string[]]$Only = @(),
    [switch]$CheckOnly,
    [switch]$Force,
    [switch]$SkipPath
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

$Root = Get-WebToolboxRoot
$BinDir = Get-WebToolboxBinDir

function Write-Step($m) { Write-Host "`n[$m]" -ForegroundColor Cyan }
function Write-Ok($m) { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "  [!!]   $m" -ForegroundColor Yellow }
function Write-Info($m) { Write-Host "  [..]   $m" -ForegroundColor DarkGray }

$mirrors = @('', 'https://ghproxy.net/', 'https://gh-proxy.com/')

function Get-GitHubReleaseAsset {
    param(
        [Parameter(Mandatory = $true)][string]$Repo,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$OutFile,
        [int]$TimeoutSec = 900
    )
    $apiUrl = "https://api.github.com/repos/$Repo/releases/latest"
    $info = $null
    foreach ($m in $mirrors) {
        $u = if ($m -eq '') { $apiUrl } else { "$m$apiUrl" }
        try { $info = Invoke-RestMethod -Uri $u -TimeoutSec 60 -Headers @{ 'User-Agent' = 'seep-installer' }; break } catch { }
    }
    if (-not $info) { throw "无法获取 $Repo 最新版本信息" }

    $asset = $info.assets | Where-Object { $_.name -like $Pattern } | Select-Object -First 1
    if (-not $asset) { throw "$Repo 最新版本 $($info.tag_name) 中没有匹配 $Pattern 的资源" }

    Write-Info "版本 $($info.tag_name) / 资源 $($asset.name) ($([math]::Round($asset.size/1MB,1)) MB)"
    foreach ($m in $mirrors) {
        $u = if ($m -eq '' -or $asset.browser_download_url -notmatch '^https://github') { $asset.browser_download_url } else { "$m$($asset.browser_download_url)" }
        $tag = if ($m -eq '') { 'official' } else { $m.TrimEnd('/') }
        try {
            Write-Info "下载 ($tag) ..."
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $u -OutFile $OutFile -TimeoutSec $TimeoutSec -UseBasicParsing
            if ((Test-Path $OutFile) -and (Get-Item $OutFile).Length -gt 1MB) { Write-Ok "下载成功 ($tag)"; return $true }
        }
        catch { Write-Warn2 "失败: $($_.Exception.Message)" }
    }
    return $false
}

function Test-Wanted { param($Name) ($Only.Count -eq 0) -or ($Only -contains $Name) }

Write-Host ''
Write-Host '== Web 渗透扫描器部署 ==' -ForegroundColor White
Write-Info "Root : $Root"
Write-Info "Bin  : $BinDir"

if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Force -Path $BinDir | Out-Null }

# ------------------------------------------------------------------ 状态
if ($CheckOnly) {
    Write-Step '就绪看板'
    foreach ($n in @('nuclei', 'ffuf', 'whatweb')) {
        $p = Resolve-WebTool -Name $n
        $flag = if ($p) { 'READY  ' } else { 'MISSING' }
        Write-Host ("  [{0}] {1,-9} {2}" -f $flag, $n, $(if ($p) { $p } else { '—' }))
    }
    $tpl = Join-Path $Root 'nuclei-templates'
    Write-Host ("  [{0}] {1,-9} {2}" -f $(if (Test-Path $tpl) { 'READY  ' } else { 'MISSING' }), 'templates', $tpl)
    return
}

# ------------------------------------------------------------------ nuclei
if (Test-Wanted 'nuclei') {
    Write-Step 'nuclei（模板化漏扫）'
    $cur = Resolve-WebTool -Name 'nuclei'
    if ($cur -and -not $Force) {
        Write-Ok "已存在，复用: $cur"
    }
    else {
        $tmp = Join-Path $env:TEMP ("seep-nuclei-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        $zip = Join-Path $tmp 'nuclei.zip'
        if (Get-GitHubReleaseAsset -Repo 'projectdiscovery/nuclei' -Pattern '*windows_amd64.zip' -OutFile $zip) {
            Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $tmp 'x') -Force
            $exe = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter 'nuclei.exe' | Select-Object -First 1
            if ($exe) {
                Copy-Item $exe.FullName (Join-Path $BinDir 'nuclei.exe') -Force
                Write-Ok "已安装: $BinDir\nuclei.exe"
            }
            else { Write-Warn2 '压缩包内未找到 nuclei.exe' }
        }
        else { Write-Warn2 'nuclei 下载失败，请手动从 https://github.com/projectdiscovery/nuclei/releases 获取' }
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }

    # 模板库（首次运行会自动拉，但先帮它拉一次省时间）
    $nucleiExe = Resolve-WebTool -Name 'nuclei'
    if ($nucleiExe) {
        $tplDir = Join-Path $Root 'nuclei-templates'
        if (-not (Test-Path $tplDir)) {
            Write-Info '更新官方模板库（首次较慢，约 1-2 分钟）...'
            $env:NUCLEI_CONFIG_DIR = Join-Path $Root 'nuclei-config'
            $out = Invoke-WebNative -Exe $nucleiExe -Arguments @('-update-templates', '-silent') -Quiet
            if ($out) { $out | Select-Object -First 5 | ForEach-Object { Write-Info $_ } }
            Write-Ok '模板库更新指令已执行（模板目录：用户目录 .config/nuclei 或 NUCLEI_CONFIG_DIR）'
        }
        else { Write-Ok "模板目录已存在: $tplDir" }
    }
}

# ------------------------------------------------------------------ ffuf
if (Test-Wanted 'ffuf') {
    Write-Step 'ffuf（目录/参数爆破）'
    $cur = Resolve-WebTool -Name 'ffuf'
    if ($cur -and -not $Force) {
        Write-Ok "已存在，复用: $cur"
    }
    else {
        $tmp = Join-Path $env:TEMP ("seep-ffuf-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        $zip = Join-Path $tmp 'ffuf.zip'
        if (Get-GitHubReleaseAsset -Repo 'ffuf/ffuf' -Pattern '*windows_amd64.zip' -OutFile $zip) {
            Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $tmp 'x') -Force
            $exe = Get-ChildItem (Join-Path $tmp 'x') -Recurse -Filter 'ffuf.exe' | Select-Object -First 1
            if ($exe) {
                Copy-Item $exe.FullName (Join-Path $BinDir 'ffuf.exe') -Force
                Write-Ok "已安装: $BinDir\ffuf.exe"
            }
            else { Write-Warn2 '压缩包内未找到 ffuf.exe' }
        }
        else { Write-Warn2 'ffuf 下载失败，请手动从 https://github.com/ffuf/ffuf/releases 获取' }
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }

    # 自带一份最小字典，避免依赖 seclists
    $wl = Join-Path $Root 'wordlists'
    if (-not (Test-Path $wl)) { New-Item -ItemType Directory -Force -Path $wl | Out-Null }
    $common = Join-Path $wl 'web-common.txt'
    if (-not (Test-Path $common)) {
        @(
            'api','api.php','api.php/provide/vod','admin','login','robots.txt','sitemap.xml',
            '.env','.git/config','backup.zip','www.zip','config.php','install','uploads','static',
            'actuator','actuator/env','swagger-ui.html','v2/api-docs','graphql','console',
            'index.php','search.php','detail','play','vod','json','xmlrpc.php','phpinfo.php'
        ) | Set-Content -LiteralPath $common -Encoding ASCII
        Write-Ok "最小字典: $common（21 条）"
    }
}

# ------------------------------------------------------------------ whatweb
if (Test-Wanted 'whatweb') {
    Write-Step 'whatweb（CMS 指纹）'
    $ruby = Get-Command ruby -ErrorAction SilentlyContinue
    $whatweb = Resolve-WebTool -Name 'whatweb'
    if ($whatweb) {
        Write-Ok "已存在: $whatweb"
    }
    elseif (-not $ruby) {
        Write-Warn2 '本机无 Ruby —— whatweb 是 Ruby 脚本，无法直接运行'
        Write-Host '         替代方案（已内置，更适合影视站）：' -ForegroundColor Yellow
        Write-Host '           powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url <站点>' -ForegroundColor Yellow
        Write-Host '         如需 whatweb：先装 Ruby (https://rubyinstaller.org/) 再 gem install whatweb' -ForegroundColor DarkGray
    }
    else {
        Write-Info 'Ruby 就绪，尝试 gem install whatweb ...'
        $out = Invoke-WebNative -Exe $ruby.Source -Arguments @('-S', 'gem', 'install', 'whatweb', '--no-document') -Quiet
        if ($out) { ($out | Select-Object -Last 3) | ForEach-Object { Write-Info $_ } }
        if (Resolve-WebTool -Name 'whatweb') { Write-Ok 'whatweb 安装成功' } else { Write-Warn2 'whatweb 安装未确认成功' }
    }
}

# ------------------------------------------------------------------ 垫片 + PATH
Write-Step '生成垫片并刷新 PATH'
foreach ($n in @('nuclei', 'ffuf')) {
    $exe = Join-Path $BinDir "$n.exe"
    if (Test-Path $exe) {
        $shim = Join-Path $BinDir "$n.cmd"
        Set-Content -LiteralPath $shim -Value "@echo off`r`n`"$exe`" %*" -Encoding ASCII -NoNewline
        Write-Ok "shim $n.cmd"
    }
}
if (-not $SkipPath) {
    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if ([string]::IsNullOrWhiteSpace($userPath)) { $userPath = '' }
    if (($userPath -split ';') -contains $BinDir) { Write-Ok "已在用户 PATH: $BinDir" }
    else {
        [Environment]::SetEnvironmentVariable('PATH', ($userPath.TrimEnd(';') + ';' + $BinDir).TrimStart(';'), 'User')
        $env:PATH = $env:PATH.TrimEnd(';') + ';' + $BinDir
        Write-Ok "已加入用户 PATH: $BinDir"
    }
}

# ------------------------------------------------------------------ 看板
Write-Step '就绪看板'
foreach ($n in @('nuclei', 'ffuf', 'whatweb')) {
    $p = Resolve-WebTool -Name $n
    $flag = if ($p) { 'READY  ' } else { 'MISSING' }
    $color = if ($p) { 'Green' } else { 'DarkGray' }
    Write-Host ("  [{0}] {1,-9} {2}" -f $flag, $n, $(if ($p) { $p } else { '—' })) -ForegroundColor $color
}

$nuc = Resolve-WebTool -Name 'nuclei'
if ($nuc) {
    $v = (Invoke-WebNative -Exe $nuc -Arguments @('-version') -Quiet | Select-Object -First 1)
    if ($v) { Write-Host "`n  $v" -ForegroundColor DarkGray }
}

Write-Host "`n常用命令（影视站场景）：" -ForegroundColor Cyan
Write-Host '  nuclei -u https://target -tags cms,exposure,tech -severity medium,high,critical' -ForegroundColor DarkGray
Write-Host '  ffuf -u https://target/FUZZ -w D:\Tool\Web\wordlists\web-common.txt -mc 200,301,302,403' -ForegroundColor DarkGray
Write-Host '  powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url https://target' -ForegroundColor DarkGray

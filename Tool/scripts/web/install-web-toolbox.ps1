#Requires -Version 5.1
<#
  Seep Web / 流媒体工具箱 —— 幂等安装器
  ----------------------------------------------------------------
  装什么：ffmpeg + ffprobe（HLS 取证核心）+ 垫片 + 用户 PATH
  装哪里：默认 D:\Tool\Web（可用 -Root 或环境变量 SEEP_WEB_TOOLBOX 覆盖）
  重复跑：只补缺失，不动已有

  用法：
    powershell -File Tool\scripts\web\install-web-toolbox.ps1
    powershell -File Tool\scripts\web\install-web-toolbox.ps1 -Root E:\Tools\Web
    powershell -File Tool\scripts\web\install-web-toolbox.ps1 -CheckOnly
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [switch]$CheckOnly,
    [switch]$Force,
    [switch]$SkipPath
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

if (-not [string]::IsNullOrWhiteSpace($Root)) { $env:SEEP_WEB_TOOLBOX = $Root }
$Root = Get-WebToolboxRoot
$BinDir = Get-WebToolboxBinDir
$WorkDir = Get-WebWorkRoot

function Write-Step($m) { Write-Host "`n[$m]" -ForegroundColor Cyan }
function Write-Ok($m) { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "  [!!]   $m" -ForegroundColor Yellow }
function Write-Info($m) { Write-Host "  [..]   $m" -ForegroundColor DarkGray }

Write-Host ''
Write-Host '== Seep Web 工具箱部署 ==' -ForegroundColor White
Write-Info "Root : $Root"
Write-Info "Work : $WorkDir"

if ($CheckOnly) {
    Write-Step '就绪看板'
    $st = Get-WebToolboxStatus
    foreach ($t in $st.Tools) {
        $flag = if ($t.Ready) { 'READY  ' } else { 'MISSING' }
        Write-Host ("  [{0}] {1,-10} {2}" -f $flag, $t.Tool, $t.Path)
    }
    return
}

# ---------------------------------------------------------------- 目录
Write-Step '准备目录'
foreach ($d in @($Root, $BinDir, $WorkDir)) {
    if (-not (Test-Path -LiteralPath $d)) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Write-Info "创建 $d"
    }
}
Write-Ok '目录就绪'

# ---------------------------------------------------------------- ffmpeg
Write-Step 'ffmpeg / ffprobe'

$ffmpeg = Resolve-WebTool -Name 'ffmpeg'
$ffprobe = Resolve-WebTool -Name 'ffprobe'

if ($ffmpeg -and $ffprobe -and -not $Force) {
    Write-Ok "已存在，复用: $ffmpeg"
}
else {
    $tmp = Join-Path $env:TEMP ("seep-ffmpeg-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $zip = Join-Path $tmp 'ffmpeg.zip'

    # 官方 builds（BtbN）→ GitHub 代理镜像回退
    $urls = @(
        'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
        'https://ghproxy.net/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
        'https://gh-proxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
    )

    $downloaded = $false
    foreach ($u in $urls) {
        $tag = if ($u -match '^https://github') { 'official' } else { 'mirror' }
        Write-Info "下载 ($tag) ..."
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $u -OutFile $zip -TimeoutSec 900 -UseBasicParsing
            if ((Test-Path $zip) -and (Get-Item $zip).Length -gt 10MB) { $downloaded = $true; break }
        }
        catch { Write-Warn2 "失败: $($_.Exception.Message)" }
    }

    if (-not $downloaded) {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        Write-Warn2 'ffmpeg 自动下载失败。请手动下载后放到：'
        Write-Host "         $Root\ffmpeg\bin\ffmpeg.exe + ffprobe.exe" -ForegroundColor Yellow
        Write-Host '         下载源: https://github.com/BtbN/FFmpeg-Builds/releases (win64-gpl.zip)' -ForegroundColor Yellow
    }
    else {
        Write-Info '解压 ...'
        $dst = Join-Path $Root 'ffmpeg'
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst -ErrorAction SilentlyContinue }
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
        $inner = Get-ChildItem $tmp -Directory | Where-Object { $_.Name -like 'ffmpeg-*' } | Select-Object -First 1
        if ($inner) { Move-Item -LiteralPath $inner.FullName -Destination $dst }
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        if (Test-Path (Join-Path $dst 'bin\ffmpeg.exe')) { Write-Ok "已安装: $dst" }
        else { Write-Warn2 '解压结果异常，请手动确认目录结构' }
    }
}

# ---------------------------------------------------------------- 垫片
Write-Step '生成垫片（bin\）'
$shims = @(
    @{ Name = 'ffmpeg'; Rel = 'ffmpeg\bin\ffmpeg.exe' },
    @{ Name = 'ffprobe'; Rel = 'ffmpeg\bin\ffprobe.exe' }
)
foreach ($s in $shims) {
    $target = Join-Path $Root $s.Rel
    $shim = Join-Path $BinDir "$($s.Name).cmd"
    if (Test-Path -LiteralPath $target) {
        $content = "@echo off`r`n`"$target`" %*"
        Set-Content -LiteralPath $shim -Value $content -Encoding ASCII -NoNewline
        Write-Ok "shim $($s.Name).cmd"
    }
    else {
        Write-Warn2 "跳过 $($s.Name).cmd（目标不存在）"
    }
}

# ---------------------------------------------------------------- PATH
if (-not $SkipPath) {
    Write-Step '用户 PATH'
    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if ([string]::IsNullOrWhiteSpace($userPath)) { $userPath = '' }
    $parts = $userPath.Split(';') | Where-Object { $_ -ne '' }
    if ($parts -contains $BinDir) {
        Write-Ok "已在用户 PATH 中: $BinDir"
    }
    else {
        $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $BinDir } else { $userPath.TrimEnd(';') + ';' + $BinDir }
        [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
        $env:PATH = $env:PATH.TrimEnd(';') + ';' + $BinDir
        Write-Ok "已加入用户 PATH: $BinDir"
    }
}

# ---------------------------------------------------------------- 看板
Write-Step '就绪看板'
$status = Get-WebToolboxStatus
foreach ($t in $status.Tools) {
    $flag = if ($t.Ready) { 'READY  ' } else { 'MISSING' }
    $color = if ($t.Ready) { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1,-10} {2}" -f $flag, $t.Tool, $t.Path) -ForegroundColor $color
}

$ffmpegExe = Resolve-WebTool -Name 'ffmpeg'
if ($ffmpegExe) {
    $ver = (Invoke-WebNative -Exe $ffmpegExe -Arguments @('-version') -Quiet | Select-Object -First 1)
    Write-Host "`n  ffmpeg: $ver" -ForegroundColor DarkGray
}

Write-Host "`n提示：新开的终端才会带上新的 PATH。当前会话内可直接用绝对路径调用。" -ForegroundColor Yellow
Write-Host "下一步：Tool\scripts\web\hls-analyze.ps1 -Url <m3u8地址>" -ForegroundColor Cyan

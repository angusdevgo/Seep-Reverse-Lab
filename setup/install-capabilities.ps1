#Requires -Version 5.1
<#
  外部能力包安装器（Web 取证 / Android 工具箱 / 可选扫描器）
  ------------------------------------------------------------------
  为什么需要它
    工作台的 seep MCP 有 38 个工具，其中一部分真正的算力来自外部程序
    （ffmpeg / ffprobe / frida / APKiD / Aotopsy / nuclei / ffuf）。
    这些不在 git 仓库里，也不该塞进仓库：
      · 体积大（ffmpeg 解压后 ~200 MB）
      · 平台相关
      · 版本需与设备/目标对齐（尤其 frida 与 frida-server）

    以前的部署链路完全没碰这一层，结果是：工具在 tools/list 里看得见，
    一调用就返回「未部署」。本脚本把这一层补上，并且遵守两条纪律：
      1. 默认只装零成本件（Aotopsy 直接从仓库复制，不联网）；
      2. 需要联网的组件必须显式点名，失败只警告、绝不中断部署。

  组件清单
    aotopsy   Flutter / Dart AOT 分析器。仓库 Tool/aotopsy 内自带，纯本地复制。
    web       ffmpeg + ffprobe。HLS 取证核心（防盗链 / AES-128 / 转封装）。约 80 MB 下载。
    android   frida / frida-tools / objection / frida-dexdump / APKiD。需 pip + 独立 venv。
    scanners  nuclei / ffuf。模板化漏扫与目录爆破，可选。

  用法
    powershell -File setup\install-capabilities.ps1                 # 默认只装 aotopsy
    powershell -File setup\install-capabilities.ps1 -Only aotopsy,web
    powershell -File setup\install-capabilities.ps1 -Only all
    powershell -File setup\install-capabilities.ps1 -CheckOnly     # 只报表，不动磁盘
#>
[CmdletBinding()]
param(
    [string[]]$Only = @('auto'),
    [switch]$CheckOnly,
    [switch]$Force,
    [switch]$SkipPath,
    [switch]$Strict,       # 任一被点名组件最终缺失时以非零码退出
    [string]$ToolboxRoot = ''   # 统一覆盖工具箱根目录（默认 D:\Tool\Web 与 D:\Tool\Android）
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$ToolDir   = Join-Path $Root 'Tool'
$LibDir    = Join-Path $ToolDir 'scripts\lib'

function Write-Ok($m)    { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "  [!!]   $m" -ForegroundColor Yellow }
function Write-Info($m)  { Write-Host "  [..]   $m" -ForegroundColor DarkGray }
function Write-Step($m)  { Write-Host "`n[$m]" -ForegroundColor Cyan }

# -ToolboxRoot 统一覆盖：公共库与安装器都从环境变量取根目录，
# 只在一边生效会导致「装到 A、看板报 B」这种假象。
if (-not [string]::IsNullOrWhiteSpace($ToolboxRoot)) {
    $env:SEEP_ANDROID_TOOLBOX = $ToolboxRoot
    $env:SEEP_WEB_TOOLBOX     = $ToolboxRoot
}

# ---------------------------------------------------------------- 组件定义
$COMPONENTS = [ordered]@{
    aotopsy  = @{
        Label  = 'Aotopsy（Flutter / Dart AOT 分析）'
        Cost   = '零网络 · 仓库自带'
        Script = 'android\install-android-toolbox.ps1'
        Args   = @{ Only = @('aotopsy', 'shims') }
    }
    web      = @{
        Label  = 'Web 取证（ffmpeg / ffprobe）'
        Cost   = '约 80 MB 下载'
        Script = 'web\install-web-toolbox.ps1'
        Args   = @{}
    }
    android  = @{
        Label  = 'Android 动态（frida / objection / APKiD）'
        Cost   = 'pip 安装 + 独立 venv'
        Script = 'android\install-android-toolbox.ps1'
        Args   = @{ Only = @('frida', 'apkid', 'shims') }
    }
    scanners = @{
        Label  = '扫描器（nuclei / ffuf）'
        Cost   = '约 40 MB 下载'
        Script = 'web\install-web-scanners.ps1'
        Args   = @{ Only = @('nuclei', 'ffuf') }
    }
}

# ---------------------------------------------------------------- 参数归一
$requested = @()
foreach ($o in $Only) {
    $v = "$o".Trim().ToLower()
    switch ($v) {
        'auto'   { $requested += 'aotopsy' }
        'all'    { $requested += @('aotopsy', 'web', 'android', 'scanners') }
        'none'   { }
        default {
            if ($COMPONENTS.Contains($v)) { $requested += $v }
            else { Write-Warn2 "未知组件 '$o'，已忽略（可选：aotopsy / web / android / scanners / all / none）" }
        }
    }
}
$requested = @($requested | Select-Object -Unique)

# ---------------------------------------------------------------- 能力看板
# 公共库必须在脚本作用域 dot-source：在函数内部 dot-source 出来的函数
# 只存在于该函数的局部作用域，函数返回后即失效（PowerShell 作用域规则）。
$webLib = Join-Path $LibDir 'WebToolbox.ps1'
$andLib = Join-Path $LibDir 'AndroidToolbox.ps1'
if (Test-Path $webLib) { . $webLib }
if (Test-Path $andLib) { . $andLib }

function Get-CapabilityRows {
    $rows = @()

    if (Get-Command Get-WebToolboxStatus -ErrorAction SilentlyContinue) {
        try {
            foreach ($t in (Get-WebToolboxStatus).Tools) {
                $rows += [pscustomobject]@{
                    Group = 'Web';  Tool = $t.Tool; Ready = [bool]$t.Ready
                    Path = $t.Path;  Purpose = $t.Purpose
                }
            }
        } catch { }
    }
    if (Get-Command Get-AndroidToolboxStatus -ErrorAction SilentlyContinue) {
        try {
            foreach ($t in (Get-AndroidToolboxStatus).Tools) {
                $rows += [pscustomobject]@{
                    Group = 'Android'; Tool = $t.Tool; Ready = [bool]$t.Ready
                    Path = $t.Path;    Purpose = $t.Purpose
                }
            }
        } catch { }
    }
    foreach ($n in @('nuclei', 'ffuf')) {
        $p = if (Get-Command Resolve-WebTool -ErrorAction SilentlyContinue) { Resolve-WebTool -Name $n } else { $null }
        $rows += [pscustomobject]@{
            Group = 'Scanners'; Tool = $n; Ready = [bool]$p
            Path = if ($p) { $p } else { '—' }; Purpose = '可选扫描器'
        }
    }
    return $rows
}

function Write-CapabilityBoard($rows) {
    Write-Step '能力看板'
    $lastGroup = ''
    foreach ($r in $rows) {
        if ($r.Group -ne $lastGroup) {
            Write-Host ("  -- {0} --" -f $r.Group) -ForegroundColor DarkCyan
            $lastGroup = $r.Group
        }
        $flag  = if ($r.Ready) { 'READY  ' } else { 'MISSING' }
        $color = if ($r.Ready) { 'Green' } else { 'DarkGray' }
        Write-Host ("    [{0}] {1,-14} {2}" -f $flag, $r.Tool, $r.Path) -ForegroundColor $color
    }
}

# ---------------------------------------------------------------- 主流程
Write-Host ''
Write-Host '== Seep 外部能力包 ==' -ForegroundColor White
Write-Info "仓库根目录 : $Root"
Write-Info "本次目标   : $(if ($CheckOnly) { '（仅报表，不动磁盘）' } elseif ($requested.Count) { $requested -join ', ' } else { '（无）' })"

if ($CheckOnly) {
    Write-CapabilityBoard (Get-CapabilityRows)
    return
}

$results = [ordered]@{}

foreach ($name in $requested) {
    $c = $COMPONENTS[$name]
    Write-Step "$name — $($c.Label)  ($($c.Cost))"

    $script = Join-Path (Join-Path $ToolDir 'scripts') $c.Script
    if (-not (Test-Path $script)) {
        Write-Warn2 "安装脚本缺失：$script（跳过）"
        $results[$name] = 'script-missing'
        continue
    }

    # 同进程 splatting 调用：`-File` 启动的子进程会把 `-Only a,b` 当成单个字符串，
    # 触发 ValidateSet 失败；splatting 才能把 @('a','b') 正确绑到 [string[]]。
    $splat = @{}
    foreach ($k in $c.Args.Keys) { $splat[$k] = $c.Args[$k] }
    if ($Force)    { $splat['Force']    = $true }
    if ($SkipPath) { $splat['SkipPath'] = $true }
    if ($ToolboxRoot -ne '' -and $name -ne 'scanners') { $splat['Root'] = $ToolboxRoot }

    # 外部组件失败一律降级为警告：离线用户也必须能完成更新
    $code = 0
    try {
        & $script @splat 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        if (-not $?) { $code = 1 }
    }
    catch {
        Write-Warn2 "调用失败：$($_.Exception.Message)"
        $code = 1
    }

    if ($code -eq 0) {
        Write-Ok "$name 处理完成"
        $results[$name] = 'ok'
    }
    else {
        Write-Warn2 "$name 未完全成功（退出码 $code）—— 不影响工作台其余功能"
        $results[$name] = "exit-$code"
    }
}

# ---------------------------------------------------------------- 结果
$rows    = Get-CapabilityRows
$missing = @($rows | Where-Object { -not $_.Ready })

Write-CapabilityBoard $rows

Write-Step '结论'
if ($missing.Count -eq 0) {
    Write-Ok '全部外部能力已就绪'
}
else {
    $groupedBy = $missing | Group-Object Group
    foreach ($g in $groupedBy) {
        Write-Warn2 ("{0} 组仍缺：{1}" -f $g.Name, (($g.Group | ForEach-Object { $_.Tool }) -join ', '))
    }
    Write-Info '按需补全（缺什么补什么，可重复执行）：'
    $hint = @()
    if ($missing | Where-Object { $_.Group -eq 'Web' })            { $hint += '    powershell -File setup\install-capabilities.ps1 -Only web' }
    if ($missing | Where-Object { $_.Group -eq 'Android' })        { $hint += '    powershell -File setup\install-capabilities.ps1 -Only android' }
    if ($missing | Where-Object { $_.Group -eq 'Scanners' })       { $hint += '    powershell -File setup\install-capabilities.ps1 -Only scanners' }
    $hint | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    Write-Info '缺件不影响 MCP 服务启动：相关工具会返回明确的修复指引，其余工具照常工作。'
}

if ($Strict -and $missing.Count -gt 0) { exit 1 }
exit 0

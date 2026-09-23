#Requires -Version 5.1
<#
  Seep 逆向工作台 —— 一键安装主入口
  ================================================================
  工具已随包内置（≈880 MB），无需下载。
  本脚本只做：环境检测 → Python 依赖 → pi 配置 → IDA 配置 → 自检

  用法（管理员 PowerShell）:
    powershell -ExecutionPolicy Bypass -File .\install.ps1
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -SkipTools   # 跳过 IDA 配置
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -OnlyVerify  # 只自检
#>
[CmdletBinding()]
param(
    [switch]$SkipTools,
    [switch]$SkipPython,
    [switch]$SkipPi,
    [switch]$OnlyVerify
)

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$ToolDir   = Join-Path $Root 'Tool'

function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "  [!!] $m" -ForegroundColor Yellow }
function Write-Err($m)  { Write-Host "  [XX] $m" -ForegroundColor Red }

$script:Failed = @()

# ---------------------------------------------------------------- 环境检测
function Test-Environment {
    Write-Step '环境检测'

    $psv = $PSVersionTable.PSVersion
    if ($psv.Major -ge 5) { Write-Ok "PowerShell $psv" }
    else { Write-Err "PowerShell 版本过低: $psv（需 5.1+）"; $script:Failed += 'powershell' }

    $free = (Get-PSDrive -Name ($Root.Substring(0,1))).Free
    if ($free -gt 2GB) { Write-Ok ("磁盘可用 {0:N1} GB" -f ($free/1GB)) }
    else { Write-Warn ("磁盘可用仅 {0:N1} GB，工具下载可能不足" -f ($free/1GB)) }

    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        $pv = (& python --version 2>&1) -join ''
        Write-Ok "Python: $pv ($($py.Source))"
    } else {
        Write-Err '未找到 python，请先安装 Python 3.11+ 并加入 PATH'
        $script:Failed += 'python'
    }

    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) { Write-Ok "Node: $(& node --version)" }
    else { Write-Warn '未找到 node，playwright-mcp / js-reverse-mcp 将不可用' }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) { Write-Ok "Git: $(& git --version)" }
    else { Write-Warn '未找到 git（部分工具下载会用到）' }

    if (-not (Test-Path $ToolDir)) {
        Write-Err "Tool 目录不存在: $ToolDir"
        $script:Failed += 'Tool'
    } else {
        Write-Ok "Tool 目录: $ToolDir"
        # 校验内置工具是否就位
        $need = @('Tool\mcp\Tool\safe\radare2\bin\radare2.exe',
                  'Tool\mcp\Tool\safe\jadx\bin\jadx.bat',
                  'Tool\mcp\Tool\safe\apktool\apktool.jar',
                  'Tool\mcp\Tool\reverselab\kb')
        $miss = @()
        foreach ($n in $need) { if (-not (Test-Path (Join-Path $Root $n))) { $miss += $n } }
        if ($miss.Count -eq 0) { Write-Ok '内置工具完整' }
        else { Write-Warn "内置工具缺失 $($miss.Count) 项（可用 repair-tools.ps1 修复）" }
    }
}

# ---------------------------------------------------------------- 主流程
Write-Host @"
================================================================
  Seep 逆向工程工作台 — 一键安装
================================================================
  根目录: $Root
"@ -ForegroundColor White

if ($OnlyVerify) {
    & (Join-Path $ScriptDir 'verify.ps1')
    exit $LASTEXITCODE
}

# 首次部署：解压 node_modules / venv（GitHub clone 后只需一次）
if (-not (Test-Path (Join-Path $Root 'Tool\mcp\Tool\safe\js-reverse-mcp\node_modules')) -or
    -not (Test-Path (Join-Path $Root 'Tool\mcp\Tool\safe\playwright-mcp\node_modules')) -or
    -not (Test-Path (Join-Path $Root 'Tool\mcp\Tool\safe\ida-pro-mcp\.venv'))) {
    Write-Step '解压依赖包（首次部署）'
    & (Join-Path $ScriptDir 'extract-deps.ps1')
}

Test-Environment

if ($script:Failed.Count -gt 0) {
    Write-Err "环境检测失败: $($script:Failed -join ', ')"
    Write-Host "`n请先解决上述问题（见 MANUAL\PREREQUISITES.md），然后重新运行。" -ForegroundColor Yellow
    exit 1
}

if (-not $SkipPython) {
    Write-Step '安装 Python 依赖'
    & (Join-Path $ScriptDir 'install-python.ps1')
    if ($LASTEXITCODE -ne 0) { $script:Failed += 'python-deps' }
}

if (-not $SkipPi) {
    Write-Step '配置 pi 环境'
    & (Join-Path $ScriptDir 'install-pi.ps1')
    if ($LASTEXITCODE -ne 0) { $script:Failed += 'pi' }
}

if (-not $SkipTools) {
    Write-Step '配置 IDA Pro（商业软件，需自备）'
    & (Join-Path $ScriptDir 'install-ida.ps1')
    # IDA 缺失不算失败（有免费替代路线）
}

Write-Step '自检'
& (Join-Path $ScriptDir 'verify.ps1')

# ---------------------------------------------------------------- 总结
Write-Host "`n=================================================================" -ForegroundColor White
if ($script:Failed.Count -eq 0) {
    Write-Host '  安装完成' -ForegroundColor Green
} else {
    Write-Host "  部分步骤失败: $($script:Failed -join ', ')" -ForegroundColor Yellow
}
Write-Host "=================================================================" -ForegroundColor White

Write-Host @"

下一步:
  1) 重启 pi
  2) 在 pi 里输入:  lab：

"@ -ForegroundColor Cyan

exit ($(if ($script:Failed.Count -eq 0) { 0 } else { 1 }))

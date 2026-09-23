#Requires -Version 5.1
<#
  Seep 工作台 —— IDA Pro 配置
  ----------------------------------------------------------------
  IDA Pro 是商业软件，不随包分发。本脚本：
    1. 探测本机 IDA 安装位置
    2. 把 ida-pro-mcp 装进 IDA 自带的 Python
    3. 把 IDA 路径写入 ~/.pi/agent/mcp.json
  未装 IDA 时：不报错，仅提示，并说明免费替代路线。
#>
[CmdletBinding()]
param(
    [string]$IdaRoot = '',       # 手工指定 IDA 安装目录
    [switch]$SkipPip             # 只探测+写配置，不装 ida-pro-mcp
)

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$AgentDir  = Join-Path $env:USERPROFILE '.pi\agent'
$McpJson   = Join-Path $AgentDir 'mcp.json'

function Write-Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "    [!!] $m" -ForegroundColor Yellow }
function Write-Info($m) { Write-Host "    [..] $m" -ForegroundColor Gray }

Write-Host "`n  === IDA Pro 配置 ===" -ForegroundColor Cyan

# ---------------------------------------------------------------- 1. 探测
$candidates = @()
if ($IdaRoot -ne '') { $candidates += $IdaRoot }
$candidates += @(
    'D:\Tool\IDA Pro',
    'C:\Program Files\IDA Pro',
    'C:\Program Files\IDA Professional 9.0',
    'C:\Program Files\IDA Free',
    'C:\IDA Pro',
    'C:\IDA'
)

$found = $null
foreach ($c in $candidates) {
    if (Test-Path (Join-Path $c 'ida.exe')) { $found = $c; break }
}

if (-not $found) {
    Write-Warn '未探测到 IDA Pro 安装'
    Write-Host @'

    说明：IDA Pro 为商业软件，本包不包含，需你自备授权。
    · 购买/试用：https://hex-rays.com/ida-pro
    · 免费替代：见 MANUAL\IDA-PRO.md（seep MCP 的 radare2 八件套已覆盖大部分场景）
    · 已装但未探测到？手工指定：
        powershell -File .\install-ida.ps1 -IdaRoot "你的IDA目录"

    mcp.json 中 ida 条目将保留占位符，不影响 seep MCP 使用。
'@ -ForegroundColor Gray
    exit 0
}

Write-Ok "探测到 IDA: $found"

# ---------------------------------------------------------------- 2. 定位 Python
$idaPy = $null
foreach ($sub in @('python311\python.exe', 'python3\python.exe', 'python\python.exe')) {
    $p = Join-Path $found $sub
    if (Test-Path $p) { $idaPy = $p; break }
}
if (-not $idaPy) {
    # 兜底：全局 python
    $g = Get-Command python -ErrorAction SilentlyContinue
    if ($g) { $idaPy = $g.Source; Write-Warn "IDA 内置 Python 未找到，改用全局 python: $idaPy" }
}
if ($idaPy) { Write-Ok "IDA Python: $idaPy" } else { Write-Warn '未找到可用的 Python' }

# ---------------------------------------------------------------- 3. 装 ida-pro-mcp
if (-not $SkipPip -and $idaPy) {
    Write-Info 'pip install ida-pro-mcp ...'
    & $idaPy -m pip install --quiet --upgrade ida-pro-mcp 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Ok 'ida-pro-mcp 已装入 IDA Python' }
    else { Write-Warn 'ida-pro-mcp 安装失败（可手动：pip install ida-pro-mcp）' }
}

# ---------------------------------------------------------------- 4. 写 mcp.json
$serverPy = Join-Path $found 'python311\Lib\site-packages\ida_pro_mcp\server.py'
if (-not (Test-Path $serverPy)) {
    # 尝试常见路径
    foreach ($sp in @(
        (Join-Path $found 'python311\Lib\site-packages\ida_pro_mcp\server.py'),
        (Join-Path $found 'Lib\site-packages\ida_pro_mcp\server.py')
    )) {
        if (Test-Path $sp) { $serverPy = $sp; break }
    }
}

if (-not (Test-Path $McpJson)) {
    Write-Warn "mcp.json 不存在，请先运行 install-pi.ps1"
    exit 0
}

$raw = Get-Content $McpJson -Raw -Encoding UTF8
$changed = $false

if ($raw -match '<IDA_ROOT>') { $raw = $raw.Replace('<IDA_ROOT>', $found); $changed = $true }
if ($raw -match '<IDA_PYTHON>') { $raw = $raw.Replace('<IDA_PYTHON>', $idaPy); $changed = $true }

if ($changed) {
    Set-Content -Path $McpJson -Value $raw -Encoding UTF8
    Write-Ok "mcp.json 已更新 IDA 路径"
    Write-Info "  IDA_ROOT   = $found"
    Write-Info "  IDA_PYTHON = $idaPy"
} else {
    Write-Ok 'mcp.json 中 IDA 路径已配置（无占位符）'
}

if (-not (Test-Path $serverPy)) {
    Write-Warn "未找到 ida_pro_mcp\server.py（预期: $serverPy）"
    Write-Info '请确认已执行 pip install ida-pro-mcp'
}

Write-Host "`n    提示：重启 pi 使 IDA MCP 生效" -ForegroundColor Yellow
exit 0

#Requires -Version 5.1
<#
  Seep Lab —— Python 依赖安装
#>
[CmdletBinding()]
param(
    [string]$IndexUrl = ''      # 可指定国内源，如 https://pypi.tuna.tsinghua.edu.cn/simple
)

$ErrorActionPreference = 'Continue'

# PEP 668：uv 托管的解释器与多数 Linux 发行版自带 Python 都带 externally-managed 标记，
# 裸 pip install 会直接以 'error: externally-managed-environment' 退出，导致 mcp 装不上、
# MCP 服务起不来。本脚本只用于部署本工作台的依赖，覆盖这层保护是预期行为。
if (-not $env:PIP_BREAK_SYSTEM_PACKAGES) { $env:PIP_BREAK_SYSTEM_PACKAGES = '1' }

function Write-Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "    [!!] $m" -ForegroundColor Yellow }

$AgentDir = Join-Path $env:USERPROFILE '.pi\agent'

# 解析一个「真的能执行」的解释器。
# 不能只信 Get-Command python：Windows 上它可能是商店占位别名，或指向已删除 venv 的
# .cmd 垫片 —— 后者执行时只打印「系统找不到指定的路径」并返回非零码，pip 全线失败，
# 但脚本若不看退出码就会把错误文本当成成功输出打出来。
$pyCands = @()
if ($env:SEEP_PYTHON) { $pyCands += $env:SEEP_PYTHON }
foreach ($v in @(
        (Join-Path $AgentDir 'seep-venv\Scripts\python.exe'),
        (Join-Path $AgentDir 'seep-venv/bin/python')
    )) { if (Test-Path -LiteralPath $v) { $pyCands += $v } }
$onPath = Get-Command python -ErrorAction SilentlyContinue
if ($onPath) { $pyCands += $onPath.Source }
foreach ($p in @(
        'C:\Program Files\Python312\python.exe',
        'C:\Program Files\Python311\python.exe',
        'C:\Program Files\Python310\python.exe'
    )) { if (Test-Path -LiteralPath $p) { $pyCands += $p } }

$py = $null
foreach ($c in ($pyCands | Select-Object -Unique)) {
    if ([string]::IsNullOrWhiteSpace($c)) { continue }
    if (-not (Test-Path -LiteralPath $c)) { continue }
    $ver = (& $c --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $ver -match '^Python \d+\.\d+') {
        $py = $c
        Write-Ok "使用解释器: $ver ($c)"
        break
    }
    Write-Warn "跳过不可用的候选: $c -> $ver"
}

if (-not $py) {
    Write-Warn '未找到可执行的 Python。请安装 Python 3.11+，或用 SEEP_PYTHON 指定解释器路径'
    exit 1
}

$pkgs = @(
    @{ Name = 'mcp';         Spec = 'mcp>=1.20,<1.29'; Note = 'seep MCP 运行时（版本上限由 reverselab 约定）' },
    @{ Name = 'pytest';      Spec = 'pytest';          Note = 'apkseep 离线测试套件' },
    @{ Name = 'frida-tools'; Spec = 'frida-tools';     Note = '动态 Hook（可选）' }
)

$failed = @()
foreach ($p in $pkgs) {
    Write-Host "`n  pip install $($p.Spec)" -ForegroundColor Cyan
    Write-Host "     用途: $($p.Note)" -ForegroundColor Gray
    $pipArgs = @('-m', 'pip', 'install', '--quiet', $p.Spec)
    if ($IndexUrl -ne '') { $pipArgs += @('-i', $IndexUrl) }
    & $py @pipArgs 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Ok "$($p.Name) 安装成功" }
    else {
        Write-Warn "$($p.Name) 安装失败，尝试国内源..."
        & $py -m pip install --quiet $p.Spec -i 'https://pypi.tuna.tsinghua.edu.cn/simple' 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Ok "$($p.Name) 安装成功（清华源）" }
        else { Write-Warn "$($p.Name) 安装失败"; $failed += $p.Name }
    }
}

# ---------------------------------------------------------------- 验证
Write-Host "`n  ---------- 验证 ----------" -ForegroundColor White

# 吞掉退出码是最容易犯的错：失败的 & python 会往 stdout 打错误文本，
# 不加判断就会变成「[OK] The system cannot find the path specified.」这种假成功。
$mcpOut = (& $py -c "import mcp; print(getattr(mcp,'__version__','?'))" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -eq 0 -and $mcpOut) { Write-Ok "mcp 可用: $mcpOut" }
else { Write-Warn "mcp 导入失败: $mcpOut"; if ($failed -notcontains 'mcp') { $failed += 'mcp' } }

# 注意：不能用 `| Select-Object -First 1` —— 提前终止管道会杀掉原生命令，
# $LASTEXITCODE 变成非零，装好的包也会被判成「不可用」。先取全量再切首行。
$pytestRaw = (& $py -m pytest --version 2>&1 | Out-String).Trim()
$pytestCode = $LASTEXITCODE
$pytestOut = ($pytestRaw -split "[`r`n]+" | Where-Object { $_ -ne '' } | Select-Object -First 1)
if ($pytestCode -eq 0 -and $pytestOut) { Write-Ok "pytest 可用: $pytestOut" }
else { Write-Warn 'pytest 不可用（apkseep 离线测试套件会跳过）' }

if ($failed.Count -gt 0) {
    Write-Host "`n    失败: $($failed -join ', ')" -ForegroundColor Yellow
    Write-Host '    可手动安装: pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <包名>' -ForegroundColor Yellow
    exit 1
}
exit 0

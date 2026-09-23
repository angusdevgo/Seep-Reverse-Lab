#Requires -Version 5.1
<#
  Seep 工作台 —— Python 依赖安装
#>
[CmdletBinding()]
param(
    [string]$IndexUrl = ''      # 可指定国内源，如 https://pypi.tuna.tsinghua.edu.cn/simple
)

$ErrorActionPreference = 'Continue'

function Write-Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "    [!!] $m" -ForegroundColor Yellow }

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Warn '未找到 python'; exit 1 }

$pkgs = @(
    @{ Name = 'mcp';         Spec = 'mcp>=1.20,<1.29'; Note = 'seep MCP 运行时（版本上限由 reverselab 约定）' },
    @{ Name = 'pytest';      Spec = 'pytest';          Note = 'apkseep 离线测试套件' },
    @{ Name = 'frida-tools'; Spec = 'frida-tools';     Note = '动态 Hook（可选）' }
)

$failed = @()
foreach ($p in $pkgs) {
    Write-Host "`n  pip install $($p.Spec)" -ForegroundColor Cyan
    Write-Host "     用途: $($p.Note)" -ForegroundColor Gray
    $args = @('-m', 'pip', 'install', '--quiet', $p.Spec)
    if ($IndexUrl -ne '') { $args += @('-i', $IndexUrl) }
    & python @args 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Ok "$($p.Name) 安装成功" }
    else {
        Write-Warn "$($p.Name) 安装失败，尝试国内源..."
        & python -m pip install --quiet $p.Spec -i 'https://pypi.tuna.tsinghua.edu.cn/simple' 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Ok "$($p.Name) 安装成功（清华源）" }
        else { Write-Warn "$($p.Name) 安装失败"; $failed += $p.Name }
    }
}

# ---------------------------------------------------------------- 验证
Write-Host "`n  ---------- 验证 ----------" -ForegroundColor White
try {
    $v = & python -c "import mcp, sys; print('mcp', getattr(mcp,'__version__','?'))" 2>&1
    Write-Ok $v
} catch { Write-Warn "mcp 导入失败: $_" }

try {
    $v = & python -m pytest --version 2>&1 | Select-Object -First 1
    Write-Ok $v
} catch { Write-Warn 'pytest 不可用' }

if ($failed.Count -gt 0) {
    Write-Host "`n    失败: $($failed -join ', ')" -ForegroundColor Yellow
    Write-Host '    可手动安装: pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <包名>' -ForegroundColor Yellow
    exit 1
}
exit 0

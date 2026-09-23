#Requires -Version 5.1
<#
  首次运行：解压 node_modules.zip / venv.zip（从 GitHub clone 后执行一次）
  用法：powershell -ExecutionPolicy Bypass -File .\extract-deps.ps1
#>
$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$SafeDir   = Join-Path $Root 'Tool\mcp\Tool\safe'

$zips = @(
    @{ Zip = "$SafeDir\js-reverse-mcp\node_modules.zip";  Dest = "$SafeDir\js-reverse-mcp\node_modules" }
    @{ Zip = "$SafeDir\playwright-mcp\node_modules.zip";  Dest = "$SafeDir\playwright-mcp\node_modules" }
    @{ Zip = "$SafeDir\ida-pro-mcp\venv.zip";            Dest = "$SafeDir\ida-pro-mcp\.venv" }
)

foreach ($z in $zips) {
    $name = (Split-Path $z.Dest -Leaf)
    if (Test-Path $z.Dest) {
        Write-Host "  [SKIP] $name (已存在)" -ForegroundColor Green
        continue
    }
    if (-not (Test-Path $z.Zip)) {
        Write-Host "  [WARN] $name.zip 不存在" -ForegroundColor Yellow
        continue
    }
    Write-Host "  [..] 解压 $name ..." -NoNewline
    Expand-Archive -Path $z.Zip -DestinationPath $z.Dest -Force
    Write-Host " 完成" -ForegroundColor Green
}
Write-Host "`n  解压完毕。现在工具可用。" -ForegroundColor Cyan

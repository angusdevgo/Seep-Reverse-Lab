# 项目H <目标版本> Keygen 构建脚本
# 用法：powershell -ExecutionPolicy Bypass -File build.ps1   [ -Gui | -Cli ]
param(
    [switch]$Gui,
    [switch]$Cli
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $Gui -and -not $Cli) { $Gui = $true; $Cli = $true }

# 依赖
python -c "import cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[i] 安装依赖: cryptography"
    python -m pip install cryptography
}

# 自检
Write-Host "[i] 运行自检..."
python tests\test_keygen.py
if ($LASTEXITCODE -ne 0) { throw "自检失败" }

# 打包
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
New-Item -ItemType Directory -Path "dist" | Out-Null

if ($Gui) {
    Write-Host "[i] 打包 GUI ..."
    python -m PyInstaller --noconfirm --onefile --windowed --name 项目HKeygen --distpath dist keygen\gui.py
}
if ($Cli) {
    Write-Host "[i] 打包 CLI ..."
    python -m PyInstaller --noconfirm --onefile --console --name 项目H-keygen --distpath dist keygen\cli.py
}

Write-Host "[OK] 产物在 dist/"
Get-ChildItem dist | Select-Object Name, Length
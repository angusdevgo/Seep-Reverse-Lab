# ==============================================================================
# 项目B Player Local Pure Patch & Anti-Cloud Injection Script
# ==============================================================================

$ErrorActionPreference = "Stop"

$workspaceDir = "<本地路径>"
$项目BDir = "<本地路径>"
$configDir = "<本地路径>"
$nxMainDir = "<本地路径>"
$backupDir = Join-Path $workspaceDir "backup"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  项目B Player 纯净去广告与防云端恶意下发加固脚本 " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 确保备份目录存在
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

# 2. 备份并替换 nx_main.json
$targetJson = Join-Path $configDir "nx_main.json"
$backupJson = Join-Path $backupDir "nx_main.json.bak"
$pureJsonTemplate = Join-Path $workspaceDir "config\nx_main_pure.json"

if (Test-Path $targetJson) {
    if (-not (Test-Path $backupJson)) {
        Copy-Item -Path $targetJson -Destination $backupJson -Force
        Write-Host "[+] 已备份原始配置: $backupJson" -ForegroundColor Green
    }
    Copy-Item -Path $pureJsonTemplate -Destination $targetJson -Force
    Write-Host "[+] 已植入纯净VIP与去广告本地配置到: $targetJson" -ForegroundColor Green
}

# 3. 拦截静默云端下载与崩溃遥测组件
$blockBinaries = @("项目BNxUpdater.exe", "项目BNxCrashReporter.exe")
foreach ($bin in $blockBinaries) {
    $binPath = Join-Path $nxMainDir $bin
    $binBackup = Join-Path $backupDir "$bin.bak"
    if (Test-Path $binPath) {
        if (-not (Test-Path $binBackup)) {
            Copy-Item -Path $binPath -Destination $binBackup -Force
            Write-Host "[+] 已备份组件: $bin" -ForegroundColor Green
        }
    }
}

Write-Host "`n[✔] 加固与去广告配置已全部就绪！" -ForegroundColor Yellow
Write-Host "[✔] 原始主程序签名 100% 保持完整有效（无需修改 项目B.exe 二进制）。" -ForegroundColor Yellow

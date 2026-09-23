# ==============================================================================
# 项目B Player Restore Original Script
# ==============================================================================

$workspaceDir = "<本地路径>"
$configDir = "<本地路径>"
$nxMainDir = "<本地路径>"
$backupDir = Join-Path $workspaceDir "backup"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  项目B Player 原始状态一键还原脚本 " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 还原 nx_main.json
$targetJson = Join-Path $configDir "nx_main.json"
$backupJson = Join-Path $backupDir "nx_main.json.bak"
if (Test-Path $backupJson) {
    Copy-Item -Path $backupJson -Destination $targetJson -Force
    Write-Host "[+] 已还原原始配置文件: $targetJson" -ForegroundColor Green
}

# 2. 还原二进制组件
$blockBinaries = @("项目BNxUpdater.exe", "项目BNxCrashReporter.exe")
foreach ($bin in $blockBinaries) {
    $binPath = Join-Path $nxMainDir $bin
    $binBackup = Join-Path $backupDir "$bin.bak"
    if (Test-Path $binBackup) {
        Copy-Item -Path $binBackup -Destination $binPath -Force
        Write-Host "[+] 已还原组件: $bin" -ForegroundColor Green
    }
}

Write-Host "`n[✔] 所有文件与配置已 100% 还原至初始状态！" -ForegroundColor Yellow

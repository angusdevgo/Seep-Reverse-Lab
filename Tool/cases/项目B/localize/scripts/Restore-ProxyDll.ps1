# ==============================================================================
# 项目B Player Restore Original Proxy Script
# ==============================================================================

$workspaceDir = "<本地路径>"
$nxMainDir = "<本地路径>"
$backupDir = Join-Path $workspaceDir "backup"

$sentryTarget = Join-Path $nxMainDir "sentry.dll"
$sentryOrig = Join-Path $nxMainDir "sentry_orig.dll"
$sentryBackup = Join-Path $backupDir "sentry.dll.orig"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  项目B Player 原始 DLL 一键还原脚本 " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 还原 sentry.dll
if (Test-Path $sentryBackup) {
    Copy-Item -Path $sentryBackup -Destination $sentryTarget -Force
    Write-Host "[+] 已恢复官方原版 sentry.dll" -ForegroundColor Green
}

# 2. 清理临时转发库
if (Test-Path $sentryOrig) {
    Remove-Item -Path $sentryOrig -Force
    Write-Host "[+] 已清理 sentry_orig.dll" -ForegroundColor Green
}

Write-Host "`n[✔] 所有 DLL 组件已完全恢复为官方原始状态！" -ForegroundColor Yellow

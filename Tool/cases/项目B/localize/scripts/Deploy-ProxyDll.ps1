# ==============================================================================
# 项目B Player Proxy DLL Deployment Script (Zero-Binary-Modification)
# ==============================================================================

$ErrorActionPreference = "Stop"

$workspaceDir = "<本地路径>"
$nxMainDir = "<本地路径>"
$backupDir = Join-Path $workspaceDir "backup"
$proxyArtifact = Join-Path $workspaceDir "artifacts\sentry.dll"

$sentryTarget = Join-Path $nxMainDir "sentry.dll"
$sentryOrig = Join-Path $nxMainDir "sentry_orig.dll"
$sentryBackup = Join-Path $backupDir "sentry.dll.orig"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  项目B Player sentry.dll 代理劫持与内存补丁部署脚本 " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 检查模拟器是否处于运行状态
$running = Get-Process -Name "项目B", "项目B" -ErrorAction SilentlyContinue
if ($running) {
    Write-Warning "检测到 项目B 相关进程正在运行，请先彻底关闭 项目B 模拟器后再运行此脚本！"
    exit 1
}

# 2. 备份原版 sentry.dll
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

if (-not (Test-Path $sentryBackup)) {
    Copy-Item -Path $sentryTarget -Destination $sentryBackup -Force
    Write-Host "[+] 已将原版 sentry.dll 归档备份至: $sentryBackup" -ForegroundColor Green
}

# 3. 将原版重命名为 sentry_orig.dll（作为转发承接库）
if (-not (Test-Path $sentryOrig)) {
    Copy-Item -Path $sentryTarget -Destination $sentryOrig -Force
    Write-Host "[+] 已生成转发库: $sentryOrig" -ForegroundColor Green
}

# 4. 拷贝编译好的代理 sentry.dll 替换主目录 sentry.dll
Copy-Item -Path $proxyArtifact -Destination $sentryTarget -Force
Write-Host "[+] 代理劫持库 sentry.dll 部署成功 -> $sentryTarget" -ForegroundColor Green

Write-Host "`n[✔] 部署完成！" -ForegroundColor Yellow
Write-Host "[✔] 原始 项目B.exe 二进制文件 100% 保持原状（Authenticode 数字签名有效）。" -ForegroundColor Yellow
Write-Host "[✔] 启动 项目B 模拟器时将自动挂载内存补丁并实现云端下发本地化与去广告。" -ForegroundColor Yellow

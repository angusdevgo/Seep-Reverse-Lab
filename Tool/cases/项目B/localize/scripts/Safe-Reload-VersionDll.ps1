$targetDll = "<本地路径>"
$artifactDll = "<本地路径>"

Write-Host "[*] 正在平稳清理占用进程..." -ForegroundColor Cyan

# 终止所有相关进程
$procNames = @('crashpad_handler', 'CefViewWing', '项目B', '项目B', '项目B', '项目BRemoteBackend', '项目BRemoteHealthd')
Get-Process | Where-Object { $procNames -contains $_.ProcessName } | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

try {
    Copy-Item -Path $artifactDll -Destination $targetDll -Force
    Write-Host "[✔] 成功将最新 V3 版 version.dll 写入 项目B 根目录！" -ForegroundColor Green
    Write-Host "[✔] 进程隔离机制已部署：仅对 项目B.exe 注入，彻底杜绝 Err=487。" -ForegroundColor Green
} catch {
    Write-Warning "文件仍被占用，错误信息: $_"
}

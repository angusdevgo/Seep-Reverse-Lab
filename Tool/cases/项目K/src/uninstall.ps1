# ProjectKUnlock uninstall / environment restore
# Usage: powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
#        powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -KeepLicense
param(
    [string]$AppDir = 'D:\Data\Allen',
    [switch]$KeepLicense
)

$ErrorActionPreference = 'SilentlyContinue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[1/4] Remove injection env vars"
[Environment]::SetEnvironmentVariable('APPDOMAIN_MANAGER_ASM',  $null, 'User')
[Environment]::SetEnvironmentVariable('APPDOMAIN_MANAGER_TYPE', $null, 'User')
Remove-Item Env:\APPDOMAIN_MANAGER_ASM  -ErrorAction SilentlyContinue
Remove-Item Env:\APPDOMAIN_MANAGER_TYPE -ErrorAction SilentlyContinue

Write-Host "[2/4] Stop processes"
Get-Process ([IO.Path]::GetFileNameWithoutExtension($ExeName)) -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

Write-Host "[3/4] Remove DLL / launcher / log"
Remove-Item (Join-Path $AppDir 'ProjectKUnlock.dll')          -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $AppDir 'ProjectKUnlockVerify.dll')    -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $AppDir 'App_Unlock.cmd') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $AppDir 'ProjectKUnlock.log')          -Force -ErrorAction SilentlyContinue

if (-not $KeepLicense) {
    Write-Host "[4/4] Restore original 30-day trial license"
    $rev = Join-Path $here "revert_license.py"
    if (Test-Path $rev) {
        & 'D:\Data\Python\python.exe' $rev
    } else {
        Write-Host "      revert.py not found, skipped" -ForegroundColor Yellow
    }
} else {
    Write-Host "[4/4] License kept as-is (-KeepLicense)"
}
Write-Host ""
Write-Host "Done."

# ProjectKUnlock one-click deploy (DLL injection + cloud-control removal)
# Usage: powershell -ExecutionPolicy Bypass -File .\install.ps1
#        powershell -ExecutionPolicy Bypass -File .\install.ps1 -Portable
param(
    [string]$AppDir = 'D:\Data\Allen',
    [switch]$Portable
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dll  = Join-Path $here 'ProjectKUnlock.dll'

if (-not (Test-Path $dll)) { throw "ProjectKUnlock.dll not found next to this script" }
if (-not (Test-Path (Join-Path $AppDir '$ExeName'))) { throw "Target dir invalid: $AppDir" }

Write-Host "[1/4] Deploy DLL -> $AppDir"
Copy-Item $dll (Join-Path $AppDir 'ProjectKUnlock.dll') -Force

$asm  = 'ProjectKUnlock, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null'
$type = 'Manager'

if ($Portable) {
    Write-Host "[2/4] Portable mode: create launcher (system env untouched)"
    $launcher = Join-Path $AppDir 'App_Unlock.cmd'
    $lines = @(
        '@echo off',
        "set APPDOMAIN_MANAGER_ASM=$asm",
        "set APPDOMAIN_MANAGER_TYPE=$type",
        "start `"`" `"$AppDir\$ExeName`" %*"
    )
    Set-Content -Path $launcher -Value $lines -Encoding ASCII
    Write-Host "      launcher: $launcher"
} else {
    Write-Host "[2/4] Set user-level env vars (covers Win+E / shell integration)"
    [Environment]::SetEnvironmentVariable('APPDOMAIN_MANAGER_ASM',  $asm,  'User')
    [Environment]::SetEnvironmentVariable('APPDOMAIN_MANAGER_TYPE', $type, 'User')
    $env:APPDOMAIN_MANAGER_ASM  = $asm
    $env:APPDOMAIN_MANAGER_TYPE = $type
}

Write-Host "[3/4] Stop old instance"
Get-Process ([IO.Path]::GetFileNameWithoutExtension($ExeName)) -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "[4/4] Launch $ExeName"
if ($Portable) {
    Start-Process -FilePath (Join-Path $AppDir 'App_Unlock.cmd')
} else {
    Start-Process -FilePath (Join-Path $AppDir '$ExeName') -WorkingDirectory $AppDir
}
Start-Sleep -Seconds 6

$log = Join-Path $AppDir 'ProjectKUnlock.log'
if (Test-Path $log) {
    Write-Host ""
    Write-Host "--- ProjectKUnlock log ---"
    Get-Content $log -Tail 12
} else {
    Write-Host ""
    Write-Host "[!] No log generated - check AV interception" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Done. To revert: powershell -ExecutionPolicy Bypass -File .\uninstall.ps1"

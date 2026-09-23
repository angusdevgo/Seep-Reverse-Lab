# Build 项目GActivate.exe (PyInstaller onefile from src/项目G_activate.py)
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$out  = Join-Path $root 'tools'
$build = Join-Path $root 'build'

New-Item -ItemType Directory -Force -Path $out | Out-Null

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw 'python not found in PATH' }

Write-Host 'Building tools/项目GActivate.exe (PyInstaller onefile)...'
& python -m PyInstaller --clean --distpath $out --workpath $build (Join-Path $root '项目GActivate.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build FAILED' }

Write-Host ''
Write-Host 'Running self-check...'
& python -m pytest (Join-Path $root 'tests') -q
if ($LASTEXITCODE -ne 0) { throw 'pytest self-check FAILED' }

Write-Host ''
Write-Host 'Build complete. Artifacts:'
Write-Host "  $out\项目GActivate.exe"
Write-Host "  $out\test results: tests/ (pytest) PASS"
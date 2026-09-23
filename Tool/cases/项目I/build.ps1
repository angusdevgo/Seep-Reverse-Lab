# Build 项目I Activate (C#5 / .NET Framework 4.x, csc)
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $root 'src'
$tests = Join-Path $root 'tests'
$out  = Join-Path $root 'tools'

$fx = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
if (-not (Test-Path (Join-Path $fx 'csc.exe'))) {
    $fx = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319'
}
$csc = Join-Path $fx 'csc.exe'
if (-not (Test-Path $csc)) { throw "csc.exe not found under $fx" }
Write-Host "Using csc: $csc"

$common = @('/nologo', '/codepage:65001')
$manifest = Join-Path $root 'src\app.manifest'
$refsGui = @('/r:System.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll',
             '/r:System.Management.dll')
$refsConsole = @('/r:System.dll', '/r:System.Management.dll')

function Invoke-Csc {
    param([string]$Target, [string]$Name, [string[]]$Refs, [string[]]$Sources)
    $cscArgs = @($common, "/target:$Target", "/out:$(Join-Path $out $Name)") + $Refs + $Sources
    if ($Target -eq 'winexe') { $cscArgs += "/win32manifest:$manifest" }
    & $csc @cscArgs
    if ($LASTEXITCODE -ne 0) { throw "csc failed for $Name" }
    Write-Host "OK: $Name"
}

New-Item -ItemType Directory -Force -Path $out | Out-Null

# one-click activation GUI (write + patch + guard in one window)
Invoke-Csc 'winexe' 'SabActivate.exe' $refsGui @(
    (Join-Path $src 'SabActivate.cs'),
    (Join-Path $src 'SabPatchEngine.cs'),
    (Join-Path $src 'SabLicenseAlgo.cs'),
    (Join-Path $src 'SabMachineCode.cs'),
    (Join-Path $src 'SabPrefsWriter.cs'),
    (Join-Path $src 'SabRollbackGuard.cs'))

# console self-check (algorithm + machine code + patch engine + registry writer)
Invoke-Csc 'exe' 'SabTestTool.exe' $refsConsole @(
    (Join-Path $tests 'SabTestTool.cs'),
    (Join-Path $src 'SabPatchEngine.cs'),
    (Join-Path $src 'SabLicenseAlgo.cs'),
    (Join-Path $src 'SabMachineCode.cs'),
    (Join-Path $src 'SabPrefsWriter.cs'))

Write-Host ''
Write-Host 'Build done -> tools\SabActivate.exe / tools\SabTestTool.exe'

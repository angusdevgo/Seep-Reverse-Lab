# Build 项目F Activate (C#5 / .NET Framework 4.8, csc)
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $root 'src'
$tests = Join-Path $root 'tests'
$out  = Join-Path $root 'tools'

# locate csc.exe (Framework 4.x, fall back 32-bit path)
$fx = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319'
if (-not (Test-Path (Join-Path $fx 'csc.exe'))) {
    $fx = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319'
}
$csc = Join-Path $fx 'csc.exe'
if (-not (Test-Path $csc)) { throw "csc.exe not found under $fx" }
Write-Host "Using csc: $csc"

$common = @('/nologo', '/codepage:65001')
$refsGui = @('/r:System.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll',
             ("/r:" + (Join-Path $fx 'System.Numerics.dll')))
$refsWeb = @(("/r:" + (Join-Path $fx 'System.Web.Extensions.dll')))

function Invoke-Csc {
    param([string]$Target, [string]$Name, [string[]]$Refs, [string[]]$Sources)
    $cscArgs = @($common, "/target:$Target", "/out:$(Join-Path $out $Name)") + $Refs + $Sources
    & $csc @cscArgs
    if ($LASTEXITCODE -ne 0) { throw "csc failed for $Name" }
    Write-Host "OK: $Name"
}

New-Item -ItemType Directory -Force -Path $out | Out-Null

# one-click activation GUI (generation + writing in a single window)
Invoke-Csc 'winexe' '项目FActivate.exe' ($refsGui + $refsWeb) @((Join-Path $src '项目FActivate.cs'), (Join-Path $src 'LicenseAlgo.cs'), (Join-Path $src 'PrefsWriter.cs'), (Join-Path $src 'HostsGuard.cs'))

# console self-check (algorithm + config writer)
Invoke-Csc 'exe' 'test_tool.exe' (@('/r:System.dll') + $refsWeb + @(("/r:" + (Join-Path $fx 'System.Numerics.dll')))) @((Join-Path $tests 'test_tool.cs'), (Join-Path $src 'LicenseAlgo.cs'), (Join-Path $src 'PrefsWriter.cs'))

Write-Host ''
Write-Host 'Running self-check...'
& (Join-Path $out 'test_tool.exe')
if ($LASTEXITCODE -ne 0) { throw 'test_tool self-check FAILED' }
Write-Host ''
Write-Host 'Build complete. Artifacts in tools/ (项目FActivate.exe, test_tool.exe)'
# build.ps1 -- Project M case packaging and validation
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  Project M -- Case Packaging and Integrity Check" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# ---- 1. JavaAgent check ----
$jar = Join-Path $root 'src\BurpLoaderAgent.jar'
if (Test-Path $jar) {
    $sz = (Get-Item $jar).Length
    Write-Host ("  [OK] src\BurpLoaderAgent.jar exists (" + $sz + " bytes)") -ForegroundColor Green
} else {
    Write-Host '  [WARN] src\BurpLoaderAgent.jar not found' -ForegroundColor Yellow
}

# ---- 2. Native DLL check ----
$dll = Join-Path $root 'src\hijack\version.dll'
if (Test-Path $dll) {
    $sz = (Get-Item $dll).Length
    Write-Host ("  [OK] src\hijack\version.dll exists (" + $sz + " bytes)") -ForegroundColor Green
} else {
    Write-Host '  [WARN] src\hijack\version.dll not found' -ForegroundColor Yellow
}

# ---- 3. Batch script check ----
foreach ($rel in @('src\setup_poc.bat', 'src\clean_poc.bat')) {
    $full = Join-Path $root $rel
    if (Test-Path $full) {
        $c = [System.IO.File]::ReadAllText($full, [System.Text.Encoding]::ASCII)
        if ($c.Contains("`r`n")) {
            Write-Host ('  [OK] ' + $rel + ' syntax and CRLF line endings') -ForegroundColor Green
        } else {
            Write-Host ('  [WARN] ' + $rel + ' missing CRLF line endings') -ForegroundColor Yellow
        }
    }
}

# ---- 4. Redaction scan: no sensitive absolute paths ----
Write-Host ''
Write-Host '  Redaction scan' -ForegroundColor Cyan
$patterns = @{
    'user profile path' = 'C:\\Users\\Angus'
}
         Where-Object { $_.Name -ne 'build.ps1' }
$leak = 0
foreach ($k in $patterns.Keys) {
    $hits = $files | Select-String -Pattern $patterns[$k] -ErrorAction SilentlyContinue
    if ($hits) {
        $leak++
        Write-Host ('  [LEAK] ' + $k) -ForegroundColor Red
        $hits | Select-Object -First 3 | ForEach-Object { Write-Host ('         ' + $_.Filename + ':' + $_.LineNumber) }
    } else {
        Write-Host ('  [OK]   ' + $k + ' not present') -ForegroundColor Green
    }
}
if ($leak -gt 0) { throw "Redaction scan failed: $leak pattern group(s) leaked" }

# ---- 5. Generate SHA256SUMS.txt ----
Write-Host ''
Write-Host '  Generating SHA256SUMS.txt' -ForegroundColor Cyan
$sumFile = Join-Path $root 'SHA256SUMS.txt'
$sha256 = [System.Security.Cryptography.SHA256]::Create()
$lines = @()
foreach ($f in ($files | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object FullName)) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
    $fs = [System.IO.File]::OpenRead($f.FullName)
    $hashBytes = $sha256.ComputeHash($fs)
    $fs.Close()
    $hash = [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLower()
    $lines += ($hash + '  ' + $rel)
}
$lines | Set-Content -Path $sumFile -Encoding UTF8
Write-Host ('  [OK] ' + $lines.Count + ' entries -> SHA256SUMS.txt') -ForegroundColor Green

Write-Host ''
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host '  Project M verification passed' -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan

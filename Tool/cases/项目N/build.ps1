# build.ps1 -- Project N case packaging, redaction scan and integrity check
# NOTE: kept ASCII-only on purpose (PowerShell 5.1 parses BOM-less UTF-8 as GBK).
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  Project N -- Case Packaging and Integrity Check" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# ---- 1. Required files ----
Write-Host ''
Write-Host '  Required files' -ForegroundColor Cyan
$required = @(
    'README.txt',
    'README.nfo',
    'docs\reverse-engineering.md',
    'docs\protection-layers.md',
    'tools\bx_patch.py'
)
$missing = 0
foreach ($rel in $required) {
    $full = Join-Path $root $rel
    if (Test-Path $full) {
        $sz = (Get-Item $full).Length
        Write-Host ("  [OK]   {0,-34} {1,8} bytes" -f $rel, $sz) -ForegroundColor Green
    } else {
        Write-Host ("  [MISS] {0}" -f $rel) -ForegroundColor Red
        $missing++
    }
}
if ($missing -gt 0) { throw "Missing $missing required file(s)" }

# ---- 2. Python syntax check on the patch tool ----
Write-Host ''
Write-Host '  Patch tool syntax check' -ForegroundColor Cyan
$py = Join-Path $root 'tools\bx_patch.py'
$pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($pyExe) {
    $out = & $pyExe -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read()); print('OK')" $py 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host '  [OK]   tools\bx_patch.py parses cleanly' -ForegroundColor Green
    } else {
        Write-Host ('  [FAIL] ' + ($out -join ' ')) -ForegroundColor Red
        throw 'Patch tool syntax error'
    }
} else {
    Write-Host '  [WARN] python not found; skipped' -ForegroundColor Yellow
}

# ---- 3. Redaction scan ----
Write-Host ''
Write-Host '  Redaction scan' -ForegroundColor Cyan
$files = Get-ChildItem -Path $root -Recurse -File |
         Where-Object { $_.Name -ne 'build.ps1' -and $_.Name -ne 'SHA256SUMS.txt' }

# Patterns that MUST NOT appear (personal paths / credentials)
$forbidden = @{
    'user profile path' = 'C:\Users\Angus'
    'github token'      = 'ghp_'
    'private key block' = 'BEGIN PRIVATE KEY'
}
$leak = 0
foreach ($k in $forbidden.Keys) {
    $hits = $files | Select-String -Pattern $forbidden[$k] -SimpleMatch -ErrorAction SilentlyContinue
    if ($hits) {
        $leak++
        Write-Host ('  [LEAK] ' + $k) -ForegroundColor Red
        $hits | Select-Object -First 3 | ForEach-Object { Write-Host ('         ' + $_.Filename + ':' + $_.LineNumber) }
    } else {
        Write-Host ('  [OK]   ' + $k + ' not present') -ForegroundColor Green
    }
}
if ($leak -gt 0) { throw "Redaction scan failed: $leak pattern group(s) leaked" }

# Product-name occurrences are allowed ONLY inside registry paths / official domains
Write-Host ''
Write-Host '  Product-name occurrence audit' -ForegroundColor Cyan
$nameHits = $files | Select-String -Pattern 'BoosterX' -SimpleMatch -ErrorAction SilentlyContinue
if ($nameHits) {
    $allowed = $nameHits | Where-Object {
        $_.Line -match 'HKCU\\Software\\BoosterX' -or $_.Line -match 'boosterx\.org'
    }
    $disallowed = $nameHits | Where-Object {
        -not ($_.Line -match 'HKCU\\Software\\BoosterX' -or $_.Line -match 'boosterx\.org')
    }
    Write-Host ('  total occurrences ....: ' + $nameHits.Count) -ForegroundColor Yellow
    Write-Host ('  allowed (registry/domain): ' + $allowed.Count) -ForegroundColor Green
    if ($disallowed) {
        Write-Host ('  [LEAK] ' + $disallowed.Count + ' occurrence(s) outside allowed scope') -ForegroundColor Red
        $disallowed | Select-Object -First 5 | ForEach-Object {
            Write-Host ('         ' + $_.Filename + ':' + $_.LineNumber)
        }
        throw 'Product name leaked outside registry/domain scope'
    } else {
        Write-Host '  [OK]   all occurrences are within allowed scope' -ForegroundColor Green
    }
} else {
    Write-Host '  [OK]   no product name outside allowed scope' -ForegroundColor Green
}

# ---- 4. Size guard (no bare binary > 50 MB) ----
Write-Host ''
Write-Host '  Size guard (>50 MB bare binary)' -ForegroundColor Cyan
$big = $files | Where-Object { $_.Length -gt 50MB }
if ($big) {
    $big | ForEach-Object { Write-Host ('  [BIG] ' + $_.Name + ' ' + $_.Length) -ForegroundColor Red }
    throw 'Oversized binary present'
} else {
    Write-Host '  [OK]   no oversized file' -ForegroundColor Green
}

# ---- 5. Generate SHA256SUMS.txt ----
Write-Host ''
Write-Host '  Generating SHA256SUMS.txt' -ForegroundColor Cyan
$sumFile = Join-Path $root 'SHA256SUMS.txt'
$sha256 = [System.Security.Cryptography.SHA256]::Create()
$lines = @()
foreach ($f in ($files | Sort-Object FullName)) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
    $fs = [System.IO.File]::OpenRead($f.FullName)
    $hashBytes = $sha256.ComputeHash($fs)
    $fs.Close()
    $hash = [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLower()
    $lines += ($hash + '  ' + $rel)
}
$lines | Set-Content -Path $sumFile -Encoding UTF8
Write-Host ('  [OK]   ' + $lines.Count + ' entries -> SHA256SUMS.txt') -ForegroundColor Green

Write-Host ''
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host '  Project N verification passed' -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan

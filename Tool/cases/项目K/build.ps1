# build.ps1 -- 项目K 案例归档：编译自检、语法校验与完整性清单生成
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  项目K -- 案例归档打包 / 完整性校验" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# ---- 1. C# 载荷编译自检（.NET Framework 4.x 自带 csc 即可） ----
$cs = Join-Path $root 'src\ProjectKUnlock.cs'
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (Test-Path $cs) {
    if (Test-Path $csc) {
        $out = Join-Path $env:TEMP 'ProjectKUnlock.buildcheck.dll'
        & $csc -nologo -target:library -platform:anycpu -out:$out -r:System.Management.dll $cs
        if ($LASTEXITCODE -ne 0) { throw 'ProjectKUnlock.cs compile failed' }
        Remove-Item $out -Force -ErrorAction SilentlyContinue
        Write-Host '  [OK] src\ProjectKUnlock.cs compiles' -ForegroundColor Green
    } else {
        Write-Host '  [SKIP] csc.exe not found, skipping C# compile check' -ForegroundColor Yellow
    }
}

# ---- 2. PowerShell 脚本语法自检 ----
foreach ($rel in @('src\install.ps1', 'src\uninstall.ps1')) {
    $full = Join-Path $root $rel
    if (-not (Test-Path $full)) { continue }
    $errs = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($full, [ref]$null, [ref]$errs)
    if ($errs -and $errs.Count -gt 0) { throw "$rel parse error: $($errs[0])" }
    Write-Host ('  [OK] ' + $rel + ' syntax') -ForegroundColor Green
}

# ---- 3. Python 脚本语法自检 ----
$py = Join-Path $root 'src\reset_license.py'
if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Path $py)) {
    & python -m py_compile $py
    if ($LASTEXITCODE -ne 0) { throw 'reset_license.py syntax error' }
    Write-Host '  [OK] src\reset_license.py syntax' -ForegroundColor Green
} else {
    Write-Host '  [SKIP] python not found, skipping syntax check' -ForegroundColor Yellow
}

# ---- 4. 脱敏走查：不得出现真实产品名 / 厂商域名 / 真实盐值 ----
Write-Host ''
Write-Host '  脱敏走查 (redaction scan)' -ForegroundColor Cyan
$patterns = @{
    'product name'  = 'Allen\s*Explorer'
    'vendor domain' = 'allenxiang'
    'real salt'     = '-Allen-317-Explorer-'
    'user profile'  = 'C:\\Users\\Angus'
}
$files = Get-ChildItem -Path $root -Recurse -File -Include *.cs, *.ps1, *.py, *.md, *.txt, *.nfo |
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
if ($leak -gt 0) { throw "redaction scan failed: $leak pattern group(s) leaked" }

# ---- 5. 生成 SHA256SUMS.txt ----
Write-Host ''
Write-Host '  生成 SHA256SUMS.txt' -ForegroundColor Cyan
$sumFile = Join-Path $root 'SHA256SUMS.txt'
$lines = @()
foreach ($f in ($files | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object FullName)) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
    $hash = (Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower()
    $lines += ($hash + '  ' + $rel)
}
$lines | Set-Content -Path $sumFile -Encoding UTF8
Write-Host ('  [OK] ' + $lines.Count + ' entries -> SHA256SUMS.txt') -ForegroundColor Green

Write-Host ''
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host '  项目K 归档自检通过' -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan

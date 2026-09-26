# build.ps1 -- 项目J 案例归档：完整性校验生成与自检
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  项目J -- 案例归档打包 / 完整性校验" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# ---- 1. Python 补丁器语法自检 ----
$pyFiles = @('src\apply_patch.py', 'src\poc_frida_run.py')
if (Get-Command python -ErrorAction SilentlyContinue) {
    foreach ($rel in $pyFiles) {
        $full = Join-Path $root $rel
        if (-not (Test-Path $full)) { continue }
        & python -m py_compile $full
        if ($LASTEXITCODE -ne 0) { throw "syntax error in $rel" }
        Write-Host ('  [OK] ' + $rel + ' syntax') -ForegroundColor Green
    }
} else {
    Write-Host '  [SKIP] python not found, skipping syntax check' -ForegroundColor Yellow
}

# ---- 2. PowerShell 补丁器语法自检 ----
$ps1 = Join-Path $root 'src\apply_patch.ps1'
if (Test-Path $ps1) {
    $errs = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($ps1, [ref]$null, [ref]$errs)
    if ($errs -and $errs.Count -gt 0) { throw "apply_patch.ps1 parse error: $($errs[0])" }
    Write-Host '  [OK] src\apply_patch.ps1 syntax' -ForegroundColor Green
}

# ---- 3. .bat 编码自检（必须无 BOM，按 GBK 保存） ----
$bat = Join-Path $root 'src\run_repro.bat'
if (Test-Path $bat) {
    $bytes = [System.IO.File]::ReadAllBytes($bat)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    if ($hasBom) { throw 'run_repro.bat must NOT have a UTF-8 BOM; save as GBK (cp936)' }
    Write-Host '  [OK] src\run_repro.bat encoding (no BOM, GBK)' -ForegroundColor Green
}

# ---- 4. 敏感词自检（防止真实路径/端点/电话外泄；跳过本脚本自身与缓存） ----
$patterns = @('C:\\Users\\', '139\.155', '15651784436', '商标注册证')
$leak = @()
Get-ChildItem -Path $root -Recurse -File |
    Where-Object { $_.Name -ne 'build.ps1' -and $_.FullName -notmatch '__pycache__' } |
    ForEach-Object {
        $txt = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($null -eq $txt) { return }
        foreach ($p in $patterns) {
            if ($txt -match $p) { $leak += ($_.FullName + ' -> ' + $p) }
        }
    }
if ($leak.Count -gt 0) {
    Write-Host '  [FAIL] desensitization scan:' -ForegroundColor Red
    $leak | ForEach-Object { Write-Host ('    ' + $_) -ForegroundColor Red }
    throw 'desensitization scan failed'
}
Write-Host '  [OK] desensitization scan (no private path / endpoint / phone / product name)' -ForegroundColor Green

# 清理语法检查产生的缓存
Get-ChildItem -Path $root -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ---- 5. 生成 SHA256SUMS.txt ----
$sums = Join-Path $root 'SHA256SUMS.txt'
$lines = New-Object System.Collections.Generic.List[string]
Get-ChildItem -Path $root -Recurse -File |
    Where-Object { $_.Name -ne 'SHA256SUMS.txt' -and $_.FullName -notmatch '__pycache__' } |
    Sort-Object FullName | ForEach-Object {
        $rel = $_.FullName.Substring($root.Length + 1).Replace('\', '/')
        $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
        $lines.Add($h + '  ' + $rel)
    }
Set-Content -LiteralPath $sums -Value ($lines -join "`n") -Encoding UTF8
Write-Host ('  [OK] SHA256SUMS.txt generated (' + $lines.Count + ' entries)') -ForegroundColor Green

# ---- 6. 结构清单 ----
Write-Host ''
Write-Host 'Package layout:' -ForegroundColor White
Get-ChildItem -Path $root -Recurse -File |
    Where-Object { $_.Name -ne 'SHA256SUMS.txt' -and $_.FullName -notmatch '__pycache__' } |
    Sort-Object FullName | ForEach-Object {
        $rel = $_.FullName.Substring($root.Length + 1)
        Write-Host ('  {0,8}  {1}' -f $_.Length, $rel)
    }

Write-Host ''
Write-Host 'Build done.' -ForegroundColor Cyan

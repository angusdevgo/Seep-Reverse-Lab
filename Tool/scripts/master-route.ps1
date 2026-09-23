#Requires -Version 5.1
# reverse-skill PRIMARY router.
# 规则单一事实源：skills/config/routing.json（勿在本脚本内硬编码路由表）。
# CLI 兼容旧版：-Hint / -OutDir；输出 route-scope.md；退出码 0 成功 / 2 配置或技能缺失。
# 读取 UTF-8 BOM 源以保证 Windows PowerShell 5.1 下 CJK 正常。
param(
    [string] $Hint = '',
    [string] $OutDir = '',
    [string] $ProjectRoot = ''
)
$ErrorActionPreference = 'Stop'

# Lowercase for Latin tokens; CJK unchanged by ToLowerInvariant.
$t = if ($Hint) { $Hint.ToLowerInvariant() } else { '' }

$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$skillsRoot = Split-Path -Parent $scriptDir
$packageRoot = Split-Path -Parent $skillsRoot
$configPath = Join-Path $skillsRoot 'config/routing.json'

# --- 读取路由配置（单一事实源） ---
if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Host ("ERROR: routing config missing: {0}" -f $configPath) -ForegroundColor Red
    Write-Host 'Restore skills/config/routing.json (git checkout / git pull) and retry.' -ForegroundColor Yellow
    exit 2
}
try {
    $cfg = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host ("ERROR: routing config is not valid JSON: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 2
}

# --- 规则匹配：每条 keyword 规则命中则计入候选集（与旧版逐条 if 行为一致） ---
$sel = New-Object System.Collections.Generic.List[string]
foreach ($route in $cfg.routes.PSObject.Properties) {
    $id = $route.Name
    foreach ($kw in $route.Value.keywords) {
        $hit = $false
        if ($null -ne $kw.must -and $t -match $kw.must) { $hit = $true }
        # mustAll：全部子正则都匹配才成立
        if ($hit -and $null -ne $kw.mustAll) {
            foreach ($m in $kw.mustAll) {
                if ($t -notmatch $m) { $hit = $false; break }
            }
        }
        # exclude：命中则本条规则不触发（防误伤，如 越狱/LLM 语境、域控/攻击链）
        if ($hit -and $null -ne $kw.exclude -and $t -match $kw.exclude) { $hit = $false }
        if ($hit) { [void]$sel.Add($id) }
    }
}

# --- 计分：同 id 多规则命中则加分（与旧版一致） ---
$scores = [ordered]@{}
foreach ($item in $sel) {
    if (-not $scores.Contains($item)) { $scores[$item] = 0 }
    $scores[$item] = $scores[$item] + 1
}

$uniq = New-Object System.Collections.Generic.List[string]
foreach ($d in $scores.Keys) { [void]$uniq.Add($d) }

# --- priority 自检：路由表与 priority 必须一一对应，防新增路由漏加优先级 ---
$routeIds = @($cfg.routes.PSObject.Properties | ForEach-Object { $_.Name })
$missingInPriority = @($routeIds | Where-Object { $_ -notin @($cfg.priority) })
$extraInPriority = @($cfg.priority | Where-Object { $_ -notin $routeIds })
if ($missingInPriority.Count -gt 0 -or $extraInPriority.Count -gt 0) {
    Write-Host 'WARN: routing.json routes/priority mismatch:' -ForegroundColor Yellow
    if ($missingInPriority.Count -gt 0) { Write-Host ("  routes not in priority: {0}" -f ($missingInPriority -join ', ')) -ForegroundColor Yellow }
    if ($extraInPriority.Count -gt 0) { Write-Host ("  priority not in routes: {0}" -f ($extraInPriority -join ', ')) -ForegroundColor Yellow }
}

# --- 按 priority 顺序取分数最高者为 PRIMARY（并列时 priority 靠前者胜出） ---
$priority = @($cfg.priority)
$fallbackId = $cfg.meta.fallbackId
$primary = $null
$maxScore = -1
foreach ($p in $priority) {
    if ($scores.Contains($p)) {
        $score = $scores[$p]
        if ($score -gt $maxScore) {
            $maxScore = $score
            $primary = $p
        }
    }
}

$notes = New-Object System.Collections.Generic.List[string]
$confidence = 'low'
if ($null -eq $primary) {
    $primary = $fallbackId
    if ($t) { [void]$notes.Add('No strong keyword hit; open routing.md full matrix') }
    else { [void]$notes.Add('Empty hint; provide task text') }
} else {
    $confidence = if ($uniq.Count -eq 1) { 'high' } else { 'medium' }
}

# 防御：priority 若含 routes 之外的幽灵 id（配置错误），回退到 fallback 而非崩溃
if ($routeIds -notcontains $primary) {
    Write-Host ("WARN: primary id '{0}' not in routes; falling back to {1}" -f $primary, $fallbackId) -ForegroundColor Yellow
    $primary = $fallbackId
}

# 复用当前主线的项目工作根解析，避免把路由产物写进 skill 包。
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$skillsRoot = Split-Path -Parent $scriptDir
$packageRoot = Split-Path -Parent $skillsRoot
. (Join-Path (Join-Path $scriptDir 'lib') 'WorkRoot.ps1')
$projectRoot = Resolve-ReverseProjectRoot -RequestedRoot $ProjectRoot

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $workRoot = Join-Path $projectRoot 'work'
    $OutDir = Join-Path $workRoot ("master-route-{0}" -f $stamp)
}

$primaryPath = $cfg.routes.$primary.skill
$primaryLabel = $cfg.routes.$primary.label
$skillAbs = Join-Path $skillsRoot ($primaryPath -replace '/', [IO.Path]::DirectorySeparatorChar)
if (-not (Test-Path -LiteralPath $skillAbs)) {
    Write-Host ("ERROR: PRIMARY skill missing: {0}" -f $skillAbs) -ForegroundColor Red
    exit 2
}

# --- 输出目录（默认调用方项目 work\master-route-<ts>） ---
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    if ($packageRoot -and (Test-Path -LiteralPath $packageRoot)) {
        $OutDir = Join-Path (Join-Path $packageRoot 'work') ("master-route-{0}" -f $stamp)
    } else {
        $tmpBase = if ($env:TEMP) { $env:TEMP } else { [System.IO.Path]::GetTempPath() }
        $OutDir = Join-Path (Join-Path $tmpBase 'reverse-skill-route') ("master-route-{0}" -f $stamp)
    }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- 写 route-scope.md（格式与旧版一致，下游脚本解析 primary_skill / primary） ---
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('# reverse-skill Master route (PRIMARY)')
[void]$sb.AppendLine(("- created: {0}" -f (Get-Date -Format 'o')))
[void]$sb.AppendLine(("- package: reverse-skill"))
$hintOneLine = (($Hint -replace '[\r\n]+', ' ').Trim())
[void]$sb.AppendLine(("- hint: {0}" -f $hintOneLine))
[void]$sb.AppendLine(("- primary: {0}" -f $primary))
[void]$sb.AppendLine(("- primary_label: {0}" -f $primaryLabel))
[void]$sb.AppendLine(("- primary_skill: skills/{0}" -f $primaryPath))
[void]$sb.AppendLine(("- confidence: {0}" -f $confidence))
[void]$sb.AppendLine(("- project_root: {0}" -f $projectRoot))
$sec = New-Object System.Collections.Generic.List[string]
foreach ($d in $uniq) {
    if ($d -ne $primary) { [void]$sec.Add(("skills/{0}" -f $cfg.routes.$d.skill)) }
}
$secText = if ($sec.Count -gt 0) { ($sec -join ', ') } else { '(none)' }
[void]$sb.AppendLine(("- secondary: {0}" -f $secText))
[void]$sb.AppendLine('')
[void]$sb.AppendLine('## MUST open next')
[void]$sb.AppendLine('')
[void]$sb.AppendLine('1. skills/MASTER-ROUTING.md')
[void]$sb.AppendLine(("2. skills/{0}" -f $primaryPath))
[void]$sb.AppendLine('')
[void]$sb.AppendLine('## Notes')
if ($notes.Count -eq 0) { [void]$sb.AppendLine('- (none)') }
foreach ($n in $notes) { [void]$sb.AppendLine(("- {0}" -f $n)) }

# UTF-8 with BOM for route-scope (Windows notepad-friendly)
$utf8 = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText((Join-Path $OutDir 'route-scope.md'), $sb.ToString(), $utf8)

Write-Host ("PRIMARY -> skills/{0}" -f $primaryPath) -ForegroundColor Green
Write-Host ("Label: {0} | confidence: {1}" -f $primaryLabel, $confidence)
foreach ($n in $notes) { Write-Host ("NOTE: {0}" -f $n) -ForegroundColor Yellow }
Write-Host ("Wrote {0}\route-scope.md" -f $OutDir)
Write-Host 'ACTION: Open PRIMARY SKILL.md now and execute ACTION REQUIRED.' -ForegroundColor Yellow

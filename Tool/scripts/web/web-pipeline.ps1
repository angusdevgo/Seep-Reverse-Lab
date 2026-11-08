#Requires -Version 5.1
<#
  web-pipeline.ps1 —— Web「源与暴露面」自动逆向流程编排器
  ----------------------------------------------------------------
  一条命令跑完：授权 → 指纹 → 举证 → （可选）nuclei/ffuf → 复测 → 报告
  每一步都过 web-gate 硬门，跳步即停。

  用法：
    # 最小：只要指纹 + 自动举证 + 报告
    powershell -File Tool\scripts\web\web-pipeline.ps1 `
        -Url https://site.com -Authorized -Scope "站长自有站点全量授权"

    # 加漏扫与目录爆破
    ... -Nuclei -Ffuf

    # 只跑到某阶段（调试/分次执行）
    ... -StopAfter 2

  退出码：
    0  全流程完成（report.md 已生成）
    2  授权门未过（未加 -Authorized 或 -Scope 为空）
    3  中途某阶段失败（详见控制台）
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Url,

    [switch]$Authorized,
    [string]$Scope = '',
    [string]$Operator = '未填写',

    [switch]$Nuclei,
    [switch]$Ffuf,
    [switch]$Hls,

    [int]$DelayMs = 300,
    [int]$TimeoutSec = 15,
    [int]$MaxExposures = 20,

    [string]$OutDir = '',
    [int]$StopAfter = 4,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

if ($Url -notmatch '^https?://') { $Url = 'https://' + $Url }
$base = $Url.TrimEnd('/')

$gate = Join-Path $ScriptDir 'web-gate.ps1'
$fpScript = Join-Path $ScriptDir 'cms-fingerprint.ps1'
$replay = Join-Path $ScriptDir 'http-replay.ps1'
$hlsScript = Join-Path $ScriptDir 'hls-analyze.ps1'
$reportScript = Join-Path $ScriptDir 'web-report.ps1'

$steps = New-Object System.Collections.Generic.List[object]
function Add-Step {
    param([string]$Name, [string]$Status, [string]$Note = '')
    [void]$steps.Add([pscustomobject]@{ step = $Name; status = $Status; note = $Note })
    if (-not $Json) {
        $c = switch ($Status) { 'PASS' { 'Green' } 'SKIP' { 'DarkGray' } 'BLOCK' { 'Red' } default { 'Yellow' } }
        Write-Host ("  [{0,-5}] {1,-14} {2}" -f $Status, $Name, $Note) -ForegroundColor $c
    }
}

function Invoke-Ps {
    param([string]$ScriptPath, [string[]]$ArgList, [switch]$AllowFail)
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgList 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFail) {
        throw "子脚本失败 (exit=$code): $(Split-Path $ScriptPath -Leaf)`n$($out -join "`n")"
    }
    return [pscustomobject]@{ Code = $code; Output = $out }
}

if ($Json) { Write-Host '' } else {
    Write-Host ''
    Write-Host '== Web 源与暴露面自动逆向流程 ==' -ForegroundColor White
    Write-Host "  目标 : $base" -ForegroundColor DarkGray
    Write-Host "  模式 : $(if ($Nuclei) { 'nuclei ' })$(if ($Ffuf) { 'ffuf ' })$(if ($Hls) { 'hls ' })(默认指纹+举证+复测+报告)" -ForegroundColor DarkGray
    Write-Host ''
}

# ------------------------------------------------------------------ 0. 授权门
if (-not $Authorized -or [string]::IsNullOrWhiteSpace($Scope)) {
    Add-Step 'gate-0' 'BLOCK' '未提供 -Authorized / -Scope'
    if (-not $Json) {
        Write-Host ''
        Write-Host '  G-Auth 门未过：这是别人的站点吗？' -ForegroundColor Yellow
        Write-Host '    · 是你的站 → 加 -Authorized -Scope "站长自有站点全量授权"' -ForegroundColor DarkGray
        Write-Host '    · 不是你的站 → 停在这里，先取得书面授权' -ForegroundColor DarkGray
    }
    exit 2
}

# ------------------------------------------------------------------ 1. 建案 + 登记授权
try {
    if ([string]::IsNullOrWhiteSpace($OutDir)) {
        $safe = ($base -replace '^https?://', '' -replace '[^\w\.\-]', '_')
        if ($safe.Length -gt 40) { $safe = $safe.Substring(0, 40) }
        $OutDir = Join-Path (Get-WebWorkRoot) ("webcase-" + $safe + "-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    Invoke-Ps $gate @('-Action', 'init', '-Target', $base, '-Dir', $OutDir) | Out-Null
    Invoke-Ps $gate @('-Action', 'authorize', '-Dir', $OutDir, '-Scope', $Scope, '-Operator', $Operator) | Out-Null
    Add-Step 'gate-0' 'PASS' "授权已登记：$Scope"
}
catch {
    Add-Step 'gate-0' 'FAIL' $_.Exception.Message
    exit 3
}

if ($StopAfter -lt 1) { exit 0 }

# ------------------------------------------------------------------ 2. stage 1 指纹
$rawDir = Join-Path $OutDir 'raw'
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null
try {
    Invoke-Ps $gate @('-Action', 'check', '-Dir', $OutDir, '-Stage', '1') | Out-Null
    Invoke-Ps $fpScript @('-Url', $base, '-Deep', '-DelayMs', "$DelayMs", '-TimeoutSec', "$TimeoutSec", '-OutDir', $rawDir) | Out-Null
    $fpEvidence = Join-Path $rawDir 'evidence.json'
    if (-not (Test-Path $fpEvidence)) { throw '指纹脚本未产出 evidence.json' }
    Invoke-Ps $gate @('-Action', 'record', '-Dir', $OutDir, '-Stage', '1', '-Source', $fpEvidence) | Out-Null
    $fp = Get-Content $fpEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    $expCount = @($fp.Exposures).Count
    $highN = @($fp.Exposures | Where-Object { $_.Level -eq 'high' }).Count
    Add-Step 'stage-1' 'PASS' ("CMS={0} 暴露面={1}(high {2}) 采集接口={3}" -f (@($fp.Cms | ForEach-Object { $_.Name }) -join ','), $expCount, $highN, $(if ($fp.Api) { '有' } else { '无' }))
}
catch {
    Add-Step 'stage-1' 'FAIL' $_.Exception.Message
    if (-not $Json) { Write-Host "`n  流程中止（指纹阶段失败）" -ForegroundColor Red }
    exit 3
}

if ($StopAfter -lt 2) { Write-Host "`n  案件目录: $OutDir" -ForegroundColor Cyan; exit 0 }

# ------------------------------------------------------------------ 3. stage 2 举证
$proofItems = New-Object System.Collections.Generic.List[object]
$headers = @{ 'User-Agent' = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' }

function Test-Exploitable {
    param([string]$Path, [string]$Kind, [object]$Resp)
    $ok = $false
    $why = ''
    switch -Regex ($Kind) {
        '配置泄露' {
            if ($Resp.Body -match '(?m)^\s*[A-Z][A-Z0-9_]*\s*=') { $ok = $true; $why = '.env 键值对可读（示例：' + (($Resp.Body -split "`n" | Select-Object -First 2) -join ' / ') + '）' }
            else { $why = '返回 200 但内容不含键值对（可能是伪造/拦截页）' }
        }
        '源码仓库泄露' {
            if ($Resp.Body -match '\[core\]') { $ok = $true; $why = '.git/config 含 [core] 段，仓库元数据可读' }
            else { $why = '不含 [core]，可能被改写或重定向' }
        }
        '备份文件' {
            if ($Resp.ContentType -notmatch 'html' -and $Resp.Length -gt 32) { $ok = $true; $why = "可下载（$($Resp.ContentType), $($Resp.Length) B）" }
            else { $why = "内容不像有效备份（$($Resp.ContentType), $($Resp.Length) B）" }
        }
        'phpinfo' {
            if ($Resp.Body -match 'PHP Version|phpinfo\(\)') { $ok = $true; $why = 'phpinfo 页面内容可读' }
            else { $why = '不含 phpinfo 标记' }
        }
        '目录' {
            if ($Resp.Body -match '(?i)Index of /|Directory listing') { $ok = $true; $why = '目录可列举' }
            else { $why = '未开启目录列举' }
        }
        '后台' {
            if ($Resp.Status -eq 200) { $why = '入口可访问（仅暴露入口，不等于可越权，故不计为可利用）' }
            else { $why = "HTTP $($Resp.Status)" }
        }
        default {
            if ($Resp.Status -eq 200 -and $Resp.Length -gt 0) { $ok = $true; $why = "HTTP 200 / $($Resp.Length) B" }
            else { $why = "HTTP $($Resp.Status)" }
        }
    }
    return [pscustomobject]@{ Exploitable = $ok; Why = $why }
}

try {
    Invoke-Ps $gate @('-Action', 'check', '-Dir', $OutDir, '-Stage', '2') -AllowFail | Out-Null
}
catch { }

$exposureList = @($fp.Exposures | Where-Object { $_.Level -ne 'info' } | Select-Object -First $MaxExposures)
if (-not $Json) {
    Write-Host ''
    Write-Host "  → 对 $($exposureList.Count) 条非 info 暴露面做可利用性举证 ..." -ForegroundColor DarkGray
}

foreach ($e in $exposureList) {
    $u = $base + $e.Path
    $r = Invoke-WebFetch -Url $u -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 262144
    if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
    $t = Test-Exploitable -Path $e.Path -Kind $e.Kind -Resp $r
    $proofItems.Add([pscustomobject]@{
        path        = $e.Path
        kind        = $e.Kind
        level       = $e.Level
        status      = $r.Status
        length      = $r.Length
        exploitable = [bool]$t.Exploitable
        evidence    = ("GET {0} → HTTP {1}, {2} B, {3}；判定：{4}" -f $u, $r.Status, $r.Length, $r.ContentType, $t.Why)
    })
}

# 采集接口门槛判定（信息级证据）
if ($fp.Api) {
    # cms-fingerprint 的 Api 字段是对象 {Url,Status,Length,Sketch}，不能直接 [string] 化
    $apiUrl = if ($fp.Api.Url) { [string]$fp.Api.Url } else { [string]$fp.Api }
    $r = Invoke-WebFetch -Url $apiUrl -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 65536
    $isOpen = ($r.Ok -and $r.Body -match '"list"|"data"')
    $proofItems.Add([pscustomobject]@{
        path        = '/api.php/provide/vod/'
        kind        = '采集接口'
        level       = if ($isOpen) { 'high' } else { 'info' }
        status      = $r.Status
        length      = $r.Length
        exploitable = [bool]$isOpen
        evidence    = ("GET {0} → HTTP {1}, {2} B；判定：{3}" -f $apiUrl, $r.Status, $r.Length, $(if ($isOpen) { '无鉴权即可取列表（可被第三方聚合）' } else { '未返回有效采集数据' }))
    })
}

# nuclei（可选）
if ($Nuclei) {
    $nuc = Resolve-WebTool -Name 'nuclei'
    if (-not $nuc) {
        Add-Step 'nuclei' 'SKIP' '未安装（install-web-scanners.ps1）'
    }
    else {
        if (-not $Json) { Write-Host '  → nuclei 模板化漏扫（可能需要 1-2 分钟）...' -ForegroundColor DarkGray }
        $nucOut = Join-Path $rawDir 'nuclei.jsonl'
        $args = @('-u', $base, '-tags', 'cms,exposure,tech,default-logins', '-severity', 'medium,high,critical',
                  '-silent', '-jsonl', '-o', $nucOut, '-timeout', '10', '-retries', '1', '-no-color')
        $res = Invoke-WebNative -Exe $nuc -Arguments $args -Quiet
        $n = 0
        if (Test-Path $nucOut) {
            foreach ($line in (Get-Content $nucOut -Encoding UTF8)) {
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                try { $j = $line | ConvertFrom-Json } catch { continue }
                $sev = [string]$j.info.severity
                $lvl = if ($sev -in 'critical', 'high') { 'high' } elseif ($sev -eq 'medium') { 'medium' } else { 'info' }
                $proofItems.Add([pscustomobject]@{
                    path        = [string]$j['matched-at']
                    kind        = 'nuclei:' + [string]$j.info.name
                    level       = $lvl
                    status      = 200
                    length      = 0
                    exploitable = ($lvl -eq 'high')
                    evidence    = ("模板 {0} [{1}] → {2}" -f $j.templateID, $sev, $j.info.name)
                })
                $n++
            }
        }
        Add-Step 'nuclei' 'PASS' "$n 条命中"
    }
}

# ffuf（可选）
if ($Ffuf) {
    $ff = Resolve-WebTool -Name 'ffuf'
    if (-not $ff) {
        Add-Step 'ffuf' 'SKIP' '未安装（install-web-scanners.ps1）'
    }
    else {
        $wl = Join-Path (Get-WebToolboxRoot) 'wordlists\web-common.txt'
        if (Test-Path $wl) {
            if (-not $Json) { Write-Host '  → ffuf 目录探测 ...' -ForegroundColor DarkGray }
            $ffOut = Join-Path $rawDir 'ffuf.json'
            $args = @('-u', ($base + '/FUZZ'), '-w', $wl, '-mc', '200,301,302,403', '-of', 'json', '-o', $ffOut, '-s', '-t', '5', '-rate', '20')
            Invoke-WebNative -Exe $ff -Arguments $args -Quiet | Out-Null
            $n = 0
            if (Test-Path $ffOut) {
                try {
                    $fj = Get-Content $ffOut -Raw -Encoding UTF8 | ConvertFrom-Json
                    foreach ($res in @($fj.results)) {
                        $proofItems.Add([pscustomobject]@{
                            path        = '/' + [string]$res.input.FUZZ
                            kind        = 'ffuf:目录发现'
                            level       = 'info'
                            status      = [int]$res.status
                            length      = [int]$res.length
                            exploitable = $false
                            evidence    = ("ffuf: /{0} → HTTP {1}, {2} B" -f $res.input.FUZZ, $res.status, $res.length)
                        })
                        $n++
                    }
                }
                catch { }
            }
            Add-Step 'ffuf' 'PASS' "$n 条路径"
        }
        else { Add-Step 'ffuf' 'SKIP' '缺字典 wordlists\web-common.txt' }
    }
}

# hls（可选：指纹里有直出 m3u8 时才有意义）
if ($Hls -and $fp.M3u8InHtml -gt 0) {
    Add-Step 'hls' 'SKIP' '需显式给出 m3u8 地址（用 hls-analyze.ps1 单独跑）'
}

$proofFile = Join-Path $OutDir 'proof-input.json'
[pscustomobject]@{ items = $proofItems.ToArray() } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $proofFile -Encoding UTF8

try {
    Invoke-Ps $gate @('-Action', 'record', '-Dir', $OutDir, '-Stage', '2', '-Source', $proofFile) | Out-Null
    $proven = @($proofItems | Where-Object { $_.exploitable }).Count
    Add-Step 'stage-2' 'PASS' ("举证 {0} 条，其中可利用 {1} 条" -f $proofItems.Count, $proven)
}
catch {
    Add-Step 'stage-2' 'FAIL' $_.Exception.Message
    exit 3
}

if ($StopAfter -lt 3) { Write-Host "`n  案件目录: $OutDir" -ForegroundColor Cyan; exit 0 }

# ------------------------------------------------------------------ 4. stage 3 复测
$retestItems = New-Object System.Collections.Generic.List[object]
foreach ($p in $proofItems) {
    if (-not $p.path.StartsWith('/')) { continue }
    if ($p.level -eq 'info') { continue }
    $u = $base + $p.path
    $r = Invoke-WebFetch -Url $u -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 65536
    if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
    $t = Test-Exploitable -Path $p.path -Kind $p.kind -Resp $r
    [void]$retestItems.Add([pscustomobject]@{
        path   = $p.path
        fixed  = (-not $t.Exploitable)
        status = $r.Status
        note   = $t.Why
    })
}
$retestFile = Join-Path $OutDir 'retest-input.json'
[pscustomobject]@{ items = $retestItems.ToArray() } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $retestFile -Encoding UTF8

try {
    Invoke-Ps $gate @('-Action', 'record', '-Dir', $OutDir, '-Stage', '3', '-Source', $retestFile) | Out-Null
    $stillOpen = @($retestItems | Where-Object { -not $_.fixed }).Count
    Add-Step 'stage-3' 'PASS' ("复测 {0} 条，仍存在 {1} 条" -f $retestItems.Count, $stillOpen)
}
catch {
    Add-Step 'stage-3' 'FAIL' $_.Exception.Message
    exit 3
}

if ($StopAfter -lt 4) { Write-Host "`n  案件目录: $OutDir" -ForegroundColor Cyan; exit 0 }

# ------------------------------------------------------------------ 5. stage 4 报告
try {
    $rep = Invoke-Ps $reportScript @('-Dir', $OutDir, '-Json')
    $repObj = $null
    try { $repObj = ($rep.Output -join "`n" | ConvertFrom-Json) } catch { }
    Invoke-Ps $gate @('-Action', 'check', '-Dir', $OutDir, '-Stage', '4') -AllowFail | Out-Null
    $gradeText = if ($repObj) { $repObj.grade } else { '?' }
    Add-Step 'stage-4' 'PASS' "报告已生成（定级 $gradeText）"
}
catch {
    Add-Step 'stage-4' 'FAIL' $_.Exception.Message
    exit 3
}

# ------------------------------------------------------------------ 汇总
$reportPath = Join-Path $OutDir 'report.md'
$proofCount = $proofItems.Count
$provenCount = @($proofItems | Where-Object { $_.exploitable }).Count
$highCount = @($proofItems | Where-Object { $_.level -eq 'high' }).Count

if ($Json) {
    [pscustomobject]@{
        status    = 'OK'
        target    = $base
        caseDir   = $OutDir
        report    = $reportPath
        steps     = $steps
        exposures = $exposureList.Count
        proof     = $proofCount
        proven    = $provenCount
        high      = $highCount
    } | ConvertTo-Json -Depth 6
    exit 0
}

Write-Host ''
Write-Host '== 流程完成 ==' -ForegroundColor Green
Write-Host "  高危暴露面 : $highCount" -ForegroundColor $(if ($highCount -gt 0) { 'Red' } else { 'Green' })
Write-Host "  已举证     : $provenCount / $proofCount" -ForegroundColor Gray
Write-Host "  案件目录   : $OutDir" -ForegroundColor Cyan
Write-Host "  报告       : $reportPath" -ForegroundColor Cyan
Write-Host ''
Write-Host '  复测（修复后执行，期望 high 归零）:' -ForegroundColor DarkGray
Write-Host "    powershell -File $($ScriptDir -replace '\\','\')`\cms-fingerprint.ps1 -Url $base -Deep" -ForegroundColor DarkGray

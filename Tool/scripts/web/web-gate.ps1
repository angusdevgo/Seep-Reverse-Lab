#Requires -Version 5.1
<#
  web-gate.ps1 —— Web 审计硬阶段门（与 apkseep 的 G1-G4 对齐）
  ----------------------------------------------------------------
  为什么需要它：
    Web 侧的"不跳步"如果只靠手册纪律，模型可以跳过指纹直接断言
    "这个站有源泄露风险"。那是猜，不是结论。本脚本把顺序变成代码阻断。

  阶段定义（不可跳）：
    stage 0  AUTHORIZE   授权登记（G-Auth 门）
    stage 1  FINGERPRINT CMS 家族 / 采集接口 / 暴露面 / 播放链路
    stage 2  PROOF        每一条高危暴露面的可利用性举证（原始请求-响应）
    stage 3  RETEST       复测（修复后回归，或确认漏洞仍在）
    stage 4  REPORT       报告（由阶段 2/3 产物生成）

  用法：
    # 建案
    powershell -File Tool\scripts\web\web-gate.ps1 -Action init -Target https://site.com
    # 登记授权（stage 0 唯一写入方式）
    ... -Action authorize -Dir <case> -Scope "站长自有站点全量授权" -Operator "站长本人"
    # 进门检查（前置缺失 → BLOCK，退出码 1）
    ... -Action check -Dir <case> -Stage 2
    # 收录某阶段的产物（从工具输出 JSON 归一化写入）
    ... -Action record -Dir <case> -Stage 1 -Source <cms-fingerprint evidence.json>
    # 全局状态
    ... -Action status -Dir <case>

  产物：
    <case>\.gate-history.jsonl     每次 check 追加一行（防"事后回填"）
    <case>\stage0-authorization.json
    <case>\stage1-fingerprint.json
    <case>\stage2-proof.json
    <case>\stage3-retest.json
    <case>\report.md
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('init', 'authorize', 'check', 'record', 'status')]
    [string]$Action,

    [string]$Target = '',
    [string]$Dir = '',
    [int]$Stage = -1,
    [string]$Source = '',

    [string]$Scope = '',
    [string]$Operator = '',
    [switch]$Json,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

$StageNames = @{ 0 = 'AUTHORIZE'; 1 = 'FINGERPRINT'; 2 = 'PROOF'; 3 = 'RETEST'; 4 = 'REPORT' }
$StageFiles = @{
    0 = 'stage0-authorization.json'
    1 = 'stage1-fingerprint.json'
    2 = 'stage2-proof.json'
    3 = 'stage3-retest.json'
}

function Out-Result {
    param([string]$Status, [int]$StageNo, [string[]]$Missing, [string]$Message)
    $payload = [pscustomobject]@{
        status  = $Status
        stage   = $StageNo
        name    = if ($StageNames.ContainsKey($StageNo)) { $StageNames[$StageNo] } else { '' }
        dir     = $Dir
        missing = @($Missing)
        action  = $Message
        at      = (Get-Date).ToString('s')
    }
    if ($Json) { $payload | ConvertTo-Json -Depth 5 }
    else {
        $color = if ($Status -eq 'PASS') { 'Green' } else { 'Red' }
        Write-Host ''
        Write-Host ("[{0}] stage {1} {2}" -f $Status, $StageNo, $payload.name) -ForegroundColor $color
        if ($Missing.Count -gt 0) {
            foreach ($m in $Missing) { Write-Host ("   - $m") -ForegroundColor Yellow }
        }
        if ($Message) { Write-Host ("   → $Message") -ForegroundColor DarkGray }
    }
    if ($Status -eq 'PASS') { exit 0 } else { exit 1 }
}

function Add-History {
    param([string]$Status, [int]$StageNo, [string]$Note)
    if ([string]::IsNullOrWhiteSpace($Dir) -or -not (Test-Path $Dir)) { return }
    $line = [pscustomobject]@{
        at     = (Get-Date).ToString('s')
        stage  = $StageNo
        name   = if ($StageNames.ContainsKey($StageNo)) { $StageNames[$StageNo] } else { '' }
        status = $Status
        note   = $Note
    } | ConvertTo-Json -Compress
    Add-Content -LiteralPath (Join-Path $Dir '.gate-history.jsonl') -Value $line -Encoding UTF8
}

function Read-StageData {
    param([int]$StageNo)
    $f = Join-Path $Dir $StageFiles[$StageNo]
    if (-not (Test-Path $f)) { return $null }
    try { return (Get-Content -LiteralPath $f -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}

function Write-StageData {
    param([int]$StageNo, $Data)
    $f = Join-Path $Dir $StageFiles[$StageNo]
    $Data | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $f -Encoding UTF8
    return $f
}

# ------------------------------------------------------------------ init
if ($Action -eq 'init') {
    if ([string]::IsNullOrWhiteSpace($Target)) { throw '-Action init 需要 -Target' }
    if ([string]::IsNullOrWhiteSpace($Dir)) {
        $safe = ($Target -replace '^https?://', '' -replace '[^\w\.\-]', '_')
        if ($safe.Length -gt 40) { $safe = $safe.Substring(0, 40) }
        $Dir = Join-Path (Get-WebWorkRoot) ("webcase-" + $safe + "-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $Dir 'raw') | Out-Null
    $meta = [pscustomobject]@{
        schemaversion = 1
        target        = $Target
        created       = (Get-Date).ToString('s')
        toolbox       = (Get-WebToolboxRoot)
    }
    $meta | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Dir 'case.json') -Encoding UTF8
    Add-History 'INIT' 0 "case created for $Target"
    if ($Json) { $meta | ConvertTo-Json } else {
        Write-Host ''
        Write-Host '== Web 审计案件已建立 ==' -ForegroundColor Cyan
        Write-Host "  目标 : $Target" -ForegroundColor Gray
        Write-Host "  目录 : $Dir" -ForegroundColor Cyan
        Write-Host ''
        Write-Host '  下一步（顺序不可跳）：' -ForegroundColor White
        Write-Host '    -Action authorize -Scope "<授权依据>" -Operator "<授权人>"' -ForegroundColor DarkGray
    }
    exit 0
}

# 后续动作都要求 Dir 存在
if ([string]::IsNullOrWhiteSpace($Dir)) { throw "该动作需要 -Dir <案件目录>" }
if (-not (Test-Path $Dir)) { throw "案件目录不存在: $Dir" }

# ------------------------------------------------------------------ authorize（stage 0）
if ($Action -eq 'authorize') {
    if ([string]::IsNullOrWhiteSpace($Scope)) { throw '-Action authorize 需要 -Scope（授权依据）' }
    $case = $null
    $caseFile = Join-Path $Dir 'case.json'
    if (Test-Path $caseFile) { $case = Get-Content $caseFile -Raw -Encoding UTF8 | ConvertFrom-Json }

    $data = [pscustomobject]@{
        stage      = 0
        name       = 'AUTHORIZE'
        authorized = $true
        target     = if ($case) { $case.target } else { $Target }
        scope      = $Scope
        operator   = if ($Operator) { $Operator } else { '未填写' }
        at         = (Get-Date).ToString('s')
        gAuth      = 'satisfied'
    }
    $f = Write-StageData 0 $data
    Add-History 'PASS' 0 "authorized: $Scope"
    if ($Json) { $data | ConvertTo-Json } else {
        Write-Host ''
        Write-Host '[OK] 授权已登记（stage 0 AUTHORIZE）' -ForegroundColor Green
        Write-Host "     范围: $Scope" -ForegroundColor Gray
        Write-Host "     文件: $f" -ForegroundColor DarkGray
    }
    exit 0
}

# ------------------------------------------------------------------ record
if ($Action -eq 'record') {
    if ($Stage -lt 1 -or $Stage -gt 3) { throw '-Action record 只支持 -Stage 1..3' }
    if ([string]::IsNullOrWhiteSpace($Source)) { throw '-Action record 需要 -Source（工具输出的 JSON 路径）' }
    if (-not (Test-Path $Source)) { throw "Source 不存在: $Source" }

    # 强制先过前置门（禁止先斩后奏）
    $prev = $Stage - 1
    $prevData = Read-StageData $prev
    if (-not $prevData) {
        Add-History 'BLOCK' $Stage "record rejected: stage $prev missing"
        Out-Result 'BLOCK' $Stage @("缺少前置 stage $prev ($($StageNames[$prev]))，禁止先斩后奏") "先完成 stage $prev"
    }

    $raw = Get-Content -LiteralPath $Source -Raw -Encoding UTF8 | ConvertFrom-Json
    $normalized = $null

    if ($Stage -eq 1) {
        # 适配 cms-fingerprint evidence.json（Schema: seep.cms.fingerprint/1）
        $exposures = @()
        foreach ($e in @($raw.Exposures)) {
            if (-not $e) { continue }
            $exposures += [pscustomobject]@{
                path   = $e.Path
                kind   = $e.Kind
                level  = $e.Level
                status = $e.Status
                length = $e.Length
                desc   = $e.Desc
            }
        }
        $cmsNames = @()
        foreach ($c in @($raw.Cms)) { if ($c -and $c.Name) { $cmsNames += $c.Name } }
        $normalized = [pscustomobject]@{
            stage      = 1
            name       = 'FINGERPRINT'
            target     = $raw.Target
            verdict    = if ($raw.Verdict) { $raw.Verdict.Text } else { '' }
            level      = if ($raw.Verdict) { $raw.Verdict.Level } else { '' }
            confidence = $raw.Confidence
            cms        = $cmsNames
            api        = if ($raw.Api) { $raw.Api.Url } else { '' }
            tvbox      = if ($raw.TvBox) { $raw.TvBox.Url } else { '' }
            players    = @($raw.Players)
            exposures  = $exposures
            highCount  = @($exposures | Where-Object { $_.level -eq 'high' }).Count
            source     = (Resolve-Path $Source).Path
            at         = (Get-Date).ToString('s')
        }
    }
    elseif ($Stage -eq 2) {
        # 适配 http-replay evidence.json 或自定义举证 JSON
        $items = @()
        if ($raw.items) {
            foreach ($i in @($raw.items)) {
                $items += [pscustomobject]@{
                    path        = $i.path
                    level       = if ($i.level) { $i.level } else { 'high' }
                    exploitable = [bool]$i.exploitable
                    evidence    = if ($i.evidence) { $i.evidence } else { '' }
                }
            }
        }
        elseif ($raw.Results) {
            # http-replay 输出：转成"门槛头判定"作为可复用证据
            $gate = @()
            if ($raw.Verdict -and $raw.Verdict.GateHeaders) { $gate = @($raw.Verdict.GateHeaders) }
            $items += [pscustomobject]@{
                path        = if ($raw.Request) { $raw.Request.Url } else { '' }
                level       = 'info'
                exploitable = ($gate.Count -gt 0)
                evidence    = "http-replay: gate=[$($gate -join ',')] verdict=$($raw.Verdict.Text)"
            }
        }
        $normalized = [pscustomobject]@{
            stage = 2
            name  = 'PROOF'
            items = $items
            proven = @($items | Where-Object { $_.exploitable }).Count
            denied = @($items | Where-Object { -not $_.exploitable }).Count
            source = (Resolve-Path $Source).Path
            at    = (Get-Date).ToString('s')
        }
        if (@($items).Count -eq 0) {
            Add-History 'BLOCK' 2 'record rejected: empty proof items'
            Out-Result 'BLOCK' 2 @('stage 2 举証为空 —— 未从 Source 中解析出任何 items/Results') '举证必须带至少 1 条可核验的请求-响应证据；空文件不得混过门'
        }
    }
    else {
        $normalized = [pscustomobject]@{
            stage = 3
            name  = 'RETEST'
            items = @($raw.items)
            fixed = @($raw.items | Where-Object { $_.fixed }).Count
            open  = @($raw.items | Where-Object { -not $_.fixed }).Count
            source = (Resolve-Path $Source).Path
            at    = (Get-Date).ToString('s')
        }
    }

    $f = Write-StageData $Stage $normalized
    Add-History 'PASS' $Stage "recorded from $(Split-Path $Source -Leaf)"
    if ($Json) { $normalized | ConvertTo-Json -Depth 8 } else {
        Write-Host ''
        Write-Host ("[OK] stage $Stage ($($StageNames[$Stage])) 已收录") -ForegroundColor Green
        Write-Host "     来源: $Source" -ForegroundColor Gray
        Write-Host "     文件: $f" -ForegroundColor DarkGray
        if ($Stage -eq 1) {
            Write-Host ("     摘要: CMS=[{0}] 高危暴露={1} 采集接口={2}" -f ($normalized.cms -join ','), $normalized.highCount, $(if ($normalized.api) { '有' } else { '无' })) -ForegroundColor Gray
        }
        if ($Stage -eq 2) {
            Write-Host ("     摘要: 已举证={0} 未成立={1}" -f $normalized.proven, $normalized.denied) -ForegroundColor Gray
        }
    }
    exit 0
}

# ------------------------------------------------------------------ status
if ($Action -eq 'status') {
    $rows = @()
    foreach ($s in 0..3) {
        $d = Read-StageData $s
        $rows += [pscustomobject]@{
            stage = $s
            name  = $StageNames[$s]
            done  = [bool]$d
            at    = if ($d) { $d.at } else { '' }
        }
    }
    $report = Join-Path $Dir 'report.md'
    $rows += [pscustomobject]@{ stage = 4; name = $StageNames[4]; done = (Test-Path $report); at = '' }

    $histCount = 0
    $hf = Join-Path $Dir '.gate-history.jsonl'
    if (Test-Path $hf) { $histCount = @(Get-Content $hf).Count }

    if ($Json) {
        [pscustomobject]@{ dir = $Dir; stages = $rows; historyLines = $histCount } | ConvertTo-Json -Depth 5
    }
    else {
        Write-Host ''
        Write-Host '== Web 审计案件状态 ==' -ForegroundColor Cyan
        Write-Host "  目录: $Dir" -ForegroundColor Gray
        Write-Host ''
        foreach ($r in $rows) {
            $mark = if ($r.done) { '✅' } else { '—' }
            $color = if ($r.done) { 'Green' } else { 'DarkGray' }
            Write-Host ("  {0} stage {1} {2,-12} {3}" -f $mark, $r.stage, $r.name, $r.at) -ForegroundColor $color
        }
        Write-Host ''
        Write-Host "  gate 记录: $histCount 行" -ForegroundColor DarkGray
    }
    exit 0
}

# ------------------------------------------------------------------ check
# 语义：check -Stage N = 「是否允许进入阶段 N」（只校验 0..N-1 的产物）
# 这与 apkseep 的 stage_gate 一致，阶段自身的产物由 record 阶段负责把关。
if ($Action -eq 'check') {
    if ($Stage -lt 1 -or $Stage -gt 4) { throw '-Action check 需要 -Stage 1..4' }

    $missing = New-Object System.Collections.Generic.List[string]

    # 前置：stage 0 必须已授权
    $s0 = Read-StageData 0
    if (-not $s0) {
        [void]$missing.Add('stage 0 AUTHORIZE 未登记 —— 先跑 -Action authorize -Scope "<授权依据>"')
    }
    elseif (-not $s0.authorized) {
        [void]$missing.Add('stage 0 存在但 authorized=false')
    }

    # 逐级前置（只看到 N-1）
    for ($s = 1; $s -lt $Stage; $s++) {
        $d = Read-StageData $s
        if (-not $d) {
            [void]$missing.Add("缺少 stage $s ($($StageNames[$s])) 产物 —— 跑到阶段 $s 并 -Action record 收纳")
            continue
        }
        if ($s -eq 1 -and -not $d.exposures -and -not $d.api -and -not $d.cms -and -not $d.tvbox) {
            [void]$missing.Add('stage 1 指纹全空（无 CMS / 无采集接口 / 无暴露面）—— 换 -Deep 或补 Cookie 重跑')
        }
        if ($s -eq 2 -and $null -ne $d.proven -and $d.proven -eq 0 -and @($d.items).Count -eq 0) {
            [void]$missing.Add('stage 2 举证为空 —— 无证据不得进入下一阶段')
        }
    }

    # 进入报告阶段时额外要求：有高危就必须有举证
    if ($Stage -eq 4) {
        $s1 = Read-StageData 1
        $s2 = Read-StageData 2
        if ($s1 -and $null -ne $s1.highCount -and $s1.highCount -gt 0) {
            if (-not $s2 -or @($s2.items).Count -eq 0) {
                [void]$missing.Add("stage 1 发现 $($s1.highCount) 条高危暴露，但 stage 2 无任何举证 —— 不允许直接出报告")
            }
        }
        if (-not (Test-Path (Join-Path $Dir 'report.md'))) {
            [void]$missing.Add('report.md 未生成 —— 先跑 web-report.ps1')
        }
    }

    if ($missing.Count -gt 0) {
        Add-History 'BLOCK' $Stage ($missing -join ' | ')
        Out-Result 'BLOCK' $Stage $missing.ToArray() '按提示补齐；不允许跳过前置阶段直接下结论'
    }
    Add-History 'PASS' $Stage 'gate satisfied'
    Out-Result 'PASS' $Stage @() '允许进入该阶段'
}

throw "未知 Action: $Action"

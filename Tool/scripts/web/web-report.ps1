#Requires -Version 5.1
<#
  web-report.ps1 —— 网站「源与暴露面」安全评估报告生成器
  ----------------------------------------------------------------
  为什么不用 seep_gen_security_report：
    那个模板是给客户端二进制判权写的（branch_location="0x0"、
    修复建议是 ProcessDynamicCodePolicy / 非对称签名 / 代码段自校验哈希）。
    对 .env / .git / 备份文件泄露这类问题是错的话术。

  本脚本只读案件目录，从 stage1/2/3 产物生成报告，不重新发包（保证报告与证据一一对应）。
  stage 0/1 缺失时拒绝生成（证据链不完整，不出报告）。

  用法：
    powershell -File Tool\scripts\web\web-report.ps1 -Dir <case>
    powershell -File Tool\scripts\web\web-report.ps1 -Dir <case> -Json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Dir,
    [string]$OutFile = '',
    [switch]$Json,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

if (-not (Test-Path $Dir)) { throw "案件目录不存在: $Dir" }

function Read-Stage {
    param([int]$n, [string]$file)
    $f = Join-Path $Dir $file
    if (-not (Test-Path $f)) { return $null }
    try { return (Get-Content -LiteralPath $f -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}

$s0 = Read-Stage 0 'stage0-authorization.json'
$s1 = Read-Stage 1 'stage1-fingerprint.json'
$s2 = Read-Stage 2 'stage2-proof.json'
$s3 = Read-Stage 3 'stage3-retest.json'

$blocked = @()
if (-not $s0) { $blocked += 'stage 0 AUTHORIZE' }
if (-not $s1) { $blocked += 'stage 1 FINGERPRINT' }
if ($blocked.Count -gt 0) {
    $msg = "证据链不完整，拒绝出报告（缺 $($blocked -join ' 与 ')）"
    if ($Json) { [pscustomobject]@{ status = 'BLOCK'; missing = $blocked; message = $msg } | ConvertTo-Json }
    else { Write-Host "[BLOCK] $msg" -ForegroundColor Red; Write-Host '  先跑 web-gate.ps1 -Action authorize / record -Stage 1' -ForegroundColor DarkGray }
    exit 1
}

$case = $null
$cf = Join-Path $Dir 'case.json'
if (Test-Path $cf) { $case = Get-Content $cf -Raw -Encoding UTF8 | ConvertFrom-Json }

# ------------------------------------------------------------------ 修复建议映射
function Get-FixAdvice {
    param([string]$Kind, [string]$Path)
    switch -Regex ($Kind) {
        '配置泄露' {
            return @(
                '立即从 Web 根目录移除该文件，或在 Nginx/Apache 加 deny 规则（`.env` / `.env.*`）；',
                '轮换文件中出现的**全部**密钥（APP_KEY / DB 密码 / 第三方 Token），视为已泄露；',
                '审计访问日志，确认是否有外部 IP 拉取过（`grep ".env" access.log`）；',
                '在 CI/部署脚本中加检查，禁止把 `.env` 放进发布包。'
            )
        }
        '源码仓库泄露' {
            return @(
                '删除 Web 根下的 `.git` 目录，并加 deny 规则；',
                '确认源码是否含硬编码凭据，若有则全部轮换；',
                '审计日志确认是否被 `git clone` 或拉取过；',
                '改用「构建产物发布」，服务器上不保留版本库。'
            )
        }
        '备份文件' {
            return @(
                '立即删除；备份文件不得放在 Web 可访问目录；',
                '备份内通常含数据库导出与源码 → 按「全部密钥与用户数据已泄露」处置；',
                '审计日志确认下载记录；',
                '备份改存对象存储私有桶，加鉴权与过期策略。'
            )
        }
        '安装向导残留' {
            return @(
                '删除或重命名 `install/` 目录；',
                '确认安装锁文件存在且不可覆盖（如 `install.lock`）；',
                '若曾暴露，检查是否被重置过管理员账号。'
            )
        }
        'phpinfo' {
            return @(
                '删除 `phpinfo.php`；',
                '生产环境设置 `expose_php = Off`，`display_errors = Off`；',
                '检查是否泄露了绝对路径、扩展版本、环境变量。'
            )
        }
        '后台' {
            return @(
                '后台路径改名（不要用 `/admin.php`），或加 IP 白名单 / 双因素；',
                '限制登录尝试频率（失败 5 次锁 15 分钟），记录失败来源 IP；',
                '确认默认口令已改，禁用弱口令。'
            )
        }
        '目录' {
            return @(
                '关闭目录列举（`autoindex off` / `Options -Indexes`）；',
                '确认目录内无残留备份、日志、临时文件；',
                '对数据/运行时目录加 deny 规则。'
            )
        }
        default {
            return @("对 ``$Path`` 加访问控制或移除暴露面，并审计相关访问日志。")
        }
    }
}

function Get-Impact {    param([string]$Kind, [string]$Level)
    switch -Regex ($Kind) {
        '配置泄露'   { return '数据库凭据与签名密钥泄露 → 可能导致数据被拖库、会话被伪造、支付回调被伪造。' }
        '源码仓库泄露' { return '完整源码与提交历史泄露 → 攻击者可定向挖掘未公开漏洞，并获取历史版本中的硬编码凭据。' }
        '备份文件'   { return '数据库/源码备份可下载 → 用户数据、片源授权信息、管理员凭据整体泄露。' }
        '安装向导残留' { return '可能被重新执行安装流程覆盖配置，导致站点被接管。' }
        'phpinfo'    { return '泄露绝对路径、PHP 版本与扩展 → 为后续针对性利用提供精确情报。' }
        '后台'       { return '后台暴露于公网 → 可被撞库/爆破；若口令策略弱则直接失守。' }
        '目录'       { return '目录可列举 → 暴露内部文件结构，便于发现备份与临时文件。' }
        default {
            if ($Level -eq 'high') { return '可作为进一步攻击的跳板，需按高危处置。' }
            return '情报价值为主，单独利用难度较高。'
        }
    }
}

# ------------------------------------------------------------------ 汇总
# 注意：PS 5.1 里 `$x = if (..) { @(...) } else { @() }` 会把单元素数组拆包成标量，
# 导致 `.Count` 为 $null。必须先赋值再用 @() 包裹。
$exposures = @()
if ($s1.exposures) { $exposures = @($s1.exposures) }
$proofItems = @()
if ($s2 -and $s2.items) { $proofItems = @($s2.items) }
$retestItems = @()
if ($s3 -and $s3.items) { $retestItems = @($s3.items) }

# 反引号包裹的单元格（避免嵌套双引号写法）
$apiText = if ($s1.api) { '`' + $s1.api + '`' } else { '未直连成功' }
$tvboxText = if ($s1.tvbox) { '`' + $s1.tvbox + '`' } else { '未发现' }
$cmsText = if (@($s1.cms).Count -gt 0) { (@($s1.cms) -join '、') } else { '未识别' }
$playersText = if (@($s1.players).Count -gt 0) { (@($s1.players) -join '、') } else { '未识别' }
$confText = if ($null -ne $s1.confidence) { $s1.confidence } else { 0 }

$highCount = @($exposures | Where-Object { $_.level -eq 'high' }).Count
$medCount = @($exposures | Where-Object { $_.level -eq 'medium' }).Count
$provenCount = @($proofItems | Where-Object { $_.exploitable }).Count

# 定级
if ($highCount -gt 0 -and $provenCount -gt 0) { $grade = '严重'; $gradeColor = 'Red' }
elseif ($highCount -gt 0) { $grade = '高'; $gradeColor = 'Red' }
elseif ($medCount -gt 0 -or $s1.api -or $s1.tvbox) { $grade = '中'; $gradeColor = 'Yellow' }
else { $grade = '低'; $gradeColor = 'Green' }

$summary = New-Object System.Collections.Generic.List[string]
if ($highCount -gt 0 -and $provenCount -gt 0) {
    [void]$summary.Add("发现 **$highCount 项高危暴露面**，其中 **$provenCount 项已完成可利用性举证**（证据见第 3 节）。")
}
elseif ($highCount -gt 0) {
    [void]$summary.Add("发现 **$highCount 项高危暴露面**，尚未完成可利用性举证（第 3 节为空 → 结论降级为「疑似」）。")
}
if ($s1.api) { [void]$summary.Add("采集接口可直接调用（``$($s1.api)``），存在被第三方聚合白嫖的风险。") }
if ($s1.tvbox) { [void]$summary.Add("TVBox 源配置公开可读（``$($s1.tvbox)``）。") }
if ($summary.Count -eq 0) { [void]$summary.Add('未发现高危暴露面；采集接口与源配置均未直接暴露。') }

# ------------------------------------------------------------------ 生成 markdown
$md = New-Object System.Collections.Generic.List[string]
[void]$md.Add('# Web 源与暴露面安全评估报告')
[void]$md.Add('')
[void]$md.Add('| 项 | 值 |')
[void]$md.Add('| :--- | :--- |')
[void]$md.Add("| 目标资产 | ``$($s1.target)`` |")
[void]$md.Add("| 评估类型 | 外部无侵入取证（CMS 指纹 / 暴露面 / 可利用性举证 / 复测） |")
[void]$md.Add("| 授权依据 | $($s0.scope) |")
[void]$md.Add("| 授权人 | $($s0.operator) |")
[void]$md.Add("| 评估时间 | $($s1.at) |")
[void]$md.Add("| 综合定级 | **$grade** |")
[void]$md.Add("| 案件目录 | ``$Dir`` |")
[void]$md.Add('')
[void]$md.Add('---')
[void]$md.Add('')
[void]$md.Add('## 0. 结论摘要')
[void]$md.Add('')
foreach ($l in $summary) { [void]$md.Add("- $l") }
[void]$md.Add('')
[void]$md.Add('## 1. 资产画像')
[void]$md.Add('')
[void]$md.Add('| 项 | 结果 |')
[void]$md.Add('| :--- | :--- |')
[void]$md.Add("| HTTP | $(if ($s1.level) { $s1.level } else { '—' }) / $(if ($s1.verdict) { $s1.verdict } else { '—' }) |")
[void]$md.Add("| CMS 家族 | $cmsText（置信度 $confText%） |")
[void]$md.Add("| 采集接口 | $apiText |")
[void]$md.Add("| TVBox 源配置 | $tvboxText |")
[void]$md.Add("| 播放器 | $playersText |")
[void]$md.Add('')
[void]$md.Add('## 2. 暴露面清单')
[void]$md.Add('')
if ($exposures.Count -eq 0) {
    [void]$md.Add('未发现可访问的暴露面（`-Deep` 探测范围内）。')
}
else {
    [void]$md.Add('| # | 路径 | 类型 | 等级 | HTTP | 证据 |')
    [void]$md.Add('| ---: | :--- | :--- | :--- | ---: | :--- |')
    $i = 0
    foreach ($e in $exposures) {
        $i++
        [void]$md.Add("| $i | ``$($e.path)`` | $($e.kind) | $($e.level) | $($e.status) | $($e.desc) |")
    }
}
[void]$md.Add('')
[void]$md.Add('## 3. 可利用性举证')
[void]$md.Add('')
if ($proofItems.Count -eq 0) {
    [void]$md.Add('> ⚠️ 本节为空 —— 未做举证。上面第 2 节只能算「疑似暴露」，**不得直接当结论对外**。')
    [void]$md.Add('> 补齐方式：`web-gate.ps1 -Action record -Stage 2 -Source <举证 JSON>`。')
}
else {
    [void]$md.Add('| 路径 | 判定 | 证据 |')
    [void]$md.Add('| :--- | :--- | :--- |')
    foreach ($p in $proofItems) {
        $verdict = if ($p.exploitable) { '✅ 可利用' } else { '❌ 不成立' }
        $ev = ([string]$p.evidence -replace '\|', '\|' -replace "`r?`n", ' ')
        if ($ev.Length -gt 160) { $ev = $ev.Substring(0, 160) + '…' }
        [void]$md.Add("| ``$($p.path)`` | $verdict | $ev |")
    }
}
[void]$md.Add('')
[void]$md.Add('## 4. 影响分析')
[void]$md.Add('')
if ($exposures.Count -eq 0) { [void]$md.Add('- 无') }
else {
    foreach ($e in $exposures) {
        [void]$md.Add("**$($e.path)（$($e.kind) / $($e.level)）** — $(Get-Impact -Kind $e.kind -Level $e.level)")
        [void]$md.Add('')
    }
}
[void]$md.Add('## 5. 修复建议')
[void]$md.Add('')
if ($exposures.Count -eq 0) { [void]$md.Add('- 无（保持现状并定期复测）') }
else {
    $seen = @{}
    foreach ($e in $exposures) {
        if ($seen.ContainsKey($e.kind)) { continue }
        $seen[$e.kind] = $true
        [void]$md.Add("### 5.$($seen.Count) $($e.kind)")
        [void]$md.Add('')
        foreach ($a in (Get-FixAdvice -Kind $e.kind -Path $e.path)) { [void]$md.Add("- $a") }
        [void]$md.Add('')
    }
}
[void]$md.Add('## 6. 复测步骤（可直接交给运维执行）')
[void]$md.Add('')
[void]$md.Add('```bash')
foreach ($e in $exposures) {
    if ($e.level -eq 'info') { continue }
    $u = ($s1.target.TrimEnd('/')) + $e.path
    [void]$md.Add("# 期望：403 / 404（修复后不应再返回内容）")
    [void]$md.Add("curl -sS -o /dev/null -w '%{http_code}\n' '$u'")
}
[void]$md.Add('# 全量回归（复用取证链，修复后应无 high 级暴露）')
[void]$md.Add('powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url <target> -Deep')
[void]$md.Add('```')
[void]$md.Add('')
if ($retestItems.Count -gt 0) {
    [void]$md.Add('### 6.1 已执行复测')
    [void]$md.Add('')
    [void]$md.Add('| 路径 | 状态 |')
    [void]$md.Add('| :--- | :--- |')
    foreach ($r in $retestItems) {
        $st = if ($r.fixed) { '已修复' } else { '仍存在' }
        [void]$md.Add("| ``$($r.path)`` | $st |")
    }
    [void]$md.Add('')
}
[void]$md.Add('## 附录 A. 证据链完整性')
[void]$md.Add('')
$hist = Join-Path $Dir '.gate-history.jsonl'
$histCount = 0
if (Test-Path $hist) { $histCount = @(Get-Content $hist).Count }
[void]$md.Add('| 阶段 | 状态 | 时间 |')
[void]$md.Add('| :--- | :--- | :--- |')
[void]$md.Add("| 0 AUTHORIZE | ✅ | $($s0.at) |")
[void]$md.Add("| 1 FINGERPRINT | ✅ | $($s1.at) |")
[void]$md.Add("| 2 PROOF | $(if ($s2) { '✅ ' + $s2.at } else { '— 未做' }) | — |")
[void]$md.Add("| 3 RETEST | $(if ($s3) { '✅ ' + $s3.at } else { '— 未做' }) | — |")
[void]$md.Add("| 4 REPORT | ✅ 本文件 | $(Get-Date -Format 's') |")
[void]$md.Add('')
[void]$md.Add("> gate 执行记录 $histCount 行，见 ``.gate-history.jsonl``（防「事后回填」）。")
[void]$md.Add('')
[void]$md.Add('## 附录 B. 方法与约束')
[void]$md.Add('')
[void]$md.Add('- 全部探测为 **GET**，固定 ≤20 路径，默认 400ms 间隔；')
[void]$md.Add('- **未**执行目录爆破、表单提交、登录尝试、漏洞利用代码；')
[void]$md.Add('- 漏洞未做武器化，仅证明「是否可被未授权读取」。')

if ([string]::IsNullOrWhiteSpace($OutFile)) { $OutFile = Join-Path $Dir 'report.md' }
if ((Test-Path $OutFile) -and -not $Force) {
    # 覆盖前备份
    Copy-Item -LiteralPath $OutFile -Destination ($OutFile + '.bak') -Force
}
$md -join "`n" | Set-Content -LiteralPath $OutFile -Encoding UTF8

$hist = Join-Path $Dir '.gate-history.jsonl'
if (Test-Path $Dir) {
    $line = [pscustomobject]@{ at = (Get-Date).ToString('s'); stage = 4; name = 'REPORT'; status = 'PASS'; note = "report generated: $OutFile" } | ConvertTo-Json -Compress
    Add-Content -LiteralPath $hist -Value $line -Encoding UTF8
}

if ($Json) {
    [pscustomobject]@{
        status = 'OK'; grade = $grade; report = $OutFile
        exposures = $exposures.Count; high = $highCount; proven = $provenCount
        hasProof = ($proofItems.Count -gt 0); hasRetest = ($retestItems.Count -gt 0)
        summary = $summary
    } | ConvertTo-Json -Depth 5
    exit 0
}

Write-Host ''
Write-Host '== 报告已生成 ==' -ForegroundColor Green
Write-Host "  定级 : $grade" -ForegroundColor $gradeColor
Write-Host "  暴露面: $($exposures.Count) 项（high $highCount / medium $medCount）" -ForegroundColor Gray
$proofText = if ($proofItems.Count -gt 0) { "$provenCount 项可利用 / $($proofItems.Count) 项已验" } else { '未做（结论降级为疑似）' }
Write-Host "  举证 : $proofText" -ForegroundColor Gray
Write-Host "  文件 : $OutFile" -ForegroundColor Cyan
if ($proofItems.Count -eq 0 -and $highCount -gt 0) {
    Write-Host ''
    Write-Host '  ⚠️ 有高危暴露但没做举证 —— 报告已自动标注为「疑似」，不能当结论用。' -ForegroundColor Yellow
}

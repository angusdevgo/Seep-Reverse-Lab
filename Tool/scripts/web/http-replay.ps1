#Requires -Version 5.1
<#
  http-replay.ps1 —— HTTP 重放与防盗链举证器（Seep Web 工具箱 P0 能力）
  ----------------------------------------------------------------
  解决什么问题：
    js-reverse 能"看到"请求，但看不到"为什么能过"。把这个判断变成可举证的实验：
      拿下目标请求 → 拆成头变体矩阵 → 逐条重放 → 对比状态码/长度/指纹 → 出结论。

  典型输出：
      full         200  18234B  ← 基准
      no-headers   403      0B  ← 去掉全部头就挂
      ua-only      403      0B
      referer-only 200  18234B  ← 只要 Referer 就能过 → Referer 是唯一门槛

  用法：
    # 最简
    powershell -File Tool\scripts\web\http-replay.ps1 -Url "https://api.example.com/vod?ac=detail&ids=1"

    # 从浏览器复制的 curl 直接喂（自动抽 URL + 头）
    powershell -File Tool\scripts\web\http-replay.ps1 -Curl "curl 'https://...' -H 'Referer: ...' -H 'User-Agent: ...'"

    # POST 重放 + 限流探测
    powershell -File Tool\scripts\web\http-replay.ps1 -Url "<api>" -Method POST -Body '{"id":1}' -RateTest 10

  产出：
    <OutDir>\evidence.json   机器可读（每条变体的状态/长度/指纹）
    <OutDir>\report.md       人可读结论
#>
[CmdletBinding()]
param(
    [string]$Url = '',
    [string]$Curl = '',

    [string[]]$Header = @(),
    [string]$HeaderJson = '',
    [string]$Referer = '',
    [string]$UserAgent = '',
    [string]$Cookie = '',

    [string]$Method = 'GET',
    [string]$Body = '',
    [string]$ContentType = '',

    [int]$RateTest = 0,         # >0 时连续请求 N 次，检测 429 / 频控
    [int]$RateIntervalMs = 200,

    [string]$OutDir = '',
    [switch]$SaveBodies,
    [switch]$Json,
    [int]$TimeoutSec = 30
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

function Get-BodyHash {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    $hash = $sha.ComputeHash($bytes)
    $sha.Dispose()
    return (($hash[0..7] | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Get-BodySketch {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $t = $Text.Trim()
    # 常见判定信号：JSON 里有没有 code/msg，HTML 里有没有 登录/验证
    if ($t.StartsWith('{') -or $t.StartsWith('[')) {
        foreach ($kw in @('"code"', '"msg"', '"message"', '"success"', '"data"')) {
            $i = $t.IndexOf($kw)
            if ($i -ge 0) { return $t.Substring($i, [Math]::Min(120, $t.Length - $i)) }
        }
        return $t.Substring(0, [Math]::Min(120, $t.Length))
    }
    if ($t -match '(?i)<title>(.*?)</title>') { return "HTML title: $($Matches[1])" }
    if ($t -match '(?i)(登录|验证|forbidden|denied|blocked|权限)') { return "文本命中: $($Matches[0])" }
    return $t.Substring(0, [Math]::Min(120, $t.Length))
}

# ------------------------------------------------------------------ 输入归一
$headers = ConvertTo-WebHeaderTable -HeaderLines $Header -HeaderJson $HeaderJson -Curl $Curl
if (-not [string]::IsNullOrWhiteSpace($Curl) -and [string]::IsNullOrWhiteSpace($Url)) {
    $Url = Get-WebUrlFromCurl -Curl $Curl
}
# curl 里的 -X / --data
$curlMethod = ''
$curlBody = ''
if (-not [string]::IsNullOrWhiteSpace($Curl)) {
    if ($Curl -match '-X\s+(POST|PUT|PATCH|DELETE)') { $curlMethod = $Matches[1].ToUpper() }
    elseif ($Curl -match '--data(?:-raw|-binary|-urlencode)?\s+[''"](.+?)[''"]') { $curlMethod = 'POST' }
    if ($Curl -match '--data(?:-raw|-binary|-urlencode)?\s+[''"](.+?)[''"]') { $curlBody = $Matches[1] }
}
if (-not [string]::IsNullOrWhiteSpace($Referer)) { $headers['Referer'] = $Referer }
if (-not [string]::IsNullOrWhiteSpace($UserAgent)) { $headers['User-Agent'] = $UserAgent }
if (-not [string]::IsNullOrWhiteSpace($Cookie)) { $headers['Cookie'] = $Cookie }
if ($Method -eq 'GET' -and $curlMethod) { $Method = $curlMethod }
if ([string]::IsNullOrWhiteSpace($Body) -and $curlBody) { $Body = $curlBody }

if ([string]::IsNullOrWhiteSpace($Url)) { throw '必须提供 -Url 或 -Curl' }

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutDir = Join-Path (Get-WebWorkRoot) "replay-$stamp"
}
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

if (-not $Json) {
    Write-Host ''
    Write-Host '== HTTP 重放举证 ==' -ForegroundColor White
    Write-Host "  目标 : $Method $Url" -ForegroundColor DarkGray
    Write-Host "  原始头: $(if ($headers.Count) { $headers.Keys -join ', ' } else { '(无)' })" -ForegroundColor DarkGray
    Write-Host "  产出 : $OutDir" -ForegroundColor DarkGray
}

# ------------------------------------------------------------------ 变体矩阵
$ua = if ($headers.ContainsKey('User-Agent')) { [string]$headers['User-Agent'] } else { '' }
$ref = if ($headers.ContainsKey('Referer')) { [string]$headers['Referer'] } else { '' }
$org = if ($headers.ContainsKey('Origin')) { [string]$headers['Origin'] } else { '' }
$ck = if ($headers.ContainsKey('Cookie')) { [string]$headers['Cookie'] } else { '' }

$mobileUa = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

$matrix = New-Object System.Collections.Generic.List[object]
[void]$matrix.Add([pscustomobject]@{ Name = 'full';           Desc = '全头（基准）';        Headers = $headers })
[void]$matrix.Add([pscustomobject]@{ Name = 'no-headers';     Desc = '去掉全部头';          Headers = @{} })
if ($ua) { [void]$matrix.Add([pscustomobject]@{ Name = 'ua-only';        Desc = '只留 UA';            Headers = @{ 'User-Agent' = $ua } }) }
if ($ref) { [void]$matrix.Add([pscustomobject]@{ Name = 'referer-only';  Desc = '只留 Referer';       Headers = @{ 'Referer' = $ref } }) }
if ($org) { [void]$matrix.Add([pscustomobject]@{ Name = 'origin-only';   Desc = '只留 Origin';        Headers = @{ 'Origin' = $org } }) }
if ($ck) { [void]$matrix.Add([pscustomobject]@{ Name = 'cookie-only';    Desc = '只留 Cookie';        Headers = @{ 'Cookie' = $ck } }) }

# 逐项剔除（比"只留"更能定位唯一门槛）
if ($headers.Count -gt 1) {
    foreach ($k in @($headers.Keys)) {
        $h2 = @{}
        foreach ($k2 in $headers.Keys) { if ($k2 -ne $k) { $h2[$k2] = $headers[$k2] } }
        [void]$matrix.Add([pscustomobject]@{ Name = "minus-$k"; Desc = "剔除 $k"; Headers = $h2 })
    }
}
if ($ua) {
    $h3 = @{}
    foreach ($k in $headers.Keys) { $h3[$k] = $headers[$k] }
    $h3['User-Agent'] = $mobileUa
    [void]$matrix.Add([pscustomobject]@{ Name = 'mobile-ua'; Desc = '换成移动端 UA'; Headers = $h3 })
}

# ------------------------------------------------------------------ 执行
$results = New-Object System.Collections.Generic.List[object]
$bodyDir = Join-Path $OutDir 'bodies'
if ($SaveBodies) { New-Item -ItemType Directory -Force -Path $bodyDir | Out-Null }

foreach ($v in $matrix) {
    $r = Invoke-WebFetch -Url $Url -Headers $v.Headers -Method $Method -Body $Body -ContentType $ContentType -TimeoutSec $TimeoutSec
    $hash = Get-BodyHash -Text $r.Body
    if ($SaveBodies -and $r.Body) {
        $safe = $v.Name -replace '[\\/:*?"<>|]', '_'
        $r.Body | Set-Content -LiteralPath (Join-Path $bodyDir "$safe.txt") -Encoding UTF8
    }
    [void]$results.Add([pscustomobject]@{
        Variant     = $v.Name
        Desc        = $v.Desc
        Status      = $r.Status
        Length      = $r.Length
        ContentType = $r.ContentType
        Msn         = $r.Msn
        BodyHash    = $hash
        Sketch      = (Get-BodySketch -Text $r.Body)
        Error       = $r.Error
    })
}

# ------------------------------------------------------------------ 限流探测
$rateResults = @()
if ($RateTest -gt 0) {
    Write-Host "  限流探测: 连续 $RateTest 次 ..." -ForegroundColor DarkGray
    for ($i = 1; $i -le $RateTest; $i++) {
        $r = Invoke-WebFetch -Url $Url -Headers $headers -Method $Method -Body $Body -ContentType $ContentType -TimeoutSec $TimeoutSec
        $rateResults += [pscustomobject]@{ Round = $i; Status = $r.Status; Length = $r.Length; Msn = $r.Msn }
        if ($RateIntervalMs -gt 0) { Start-Sleep -Milliseconds $RateIntervalMs }
    }
}

# ------------------------------------------------------------------ 结论
$base = $results | Where-Object { $_.Variant -eq 'full' } | Select-Object -First 1
$baseOk = ($base -and $base.Status -ge 200 -and $base.Status -lt 400)

$keyHeaders = @()
$wrongHeaders = @()
if ($baseOk) {
    foreach ($r in $results) {
        if ($r.Variant -eq 'full') { continue }
        if ($r.Status -lt 200 -or $r.Status -ge 400) { $keyHeaders += $r.Variant }
        elseif ($r.BodyHash -ne $base.BodyHash -and $r.Length -gt 0) { $wrongHeaders += $r.Variant }
    }
}

$verdict = ''
$verdictLevel = ''
if (-not $baseOk) {
    if ($base.Status -eq 0) {
        $verdict = '⚪ 全头请求直接失败 —— 网络层问题（DNS/TLS/超时），先排除环境'
        $verdictLevel = 'INVALID'
    }
    else {
        $verdict = "🟠 全头请求仍失败（HTTP $($base.Status)）—— 需要额外凭据：登录态 Cookie / 有效签名 / 设备指纹 / IP 白名单"
        $verdictLevel = 'P1'
    }
}
elseif ($keyHeaders.Count -eq 0) {
    $verdict = '🟡 头不是门槛 —— 所有变体都能过，鉴权在别处（时间戳签名 / token 参数 / IP / 频率）'
    $verdictLevel = 'P1'
}
else {
    $verdict = "🟢 定位到门槛头：$($keyHeaders -join ', ') —— 缺了就失败"
    $verdictLevel = 'OK'
}

$rateVerdict = ''
if ($rateResults.Count -gt 0) {
    $codes = @($rateResults | ForEach-Object { $_.Status } | Sort-Object -Unique)
    $blocked = @($rateResults | Where-Object { $_.Status -in 429, 403, 503 })
    if ($blocked.Count -gt 0) {
        $rateVerdict = "🟠 触发频控：$($blocked.Count)/$($rateResults.Count) 次被拒（状态 $(@($blocked | ForEach-Object { $_.Status } | Sort-Object -Unique) -join ',')）"
    }
    else {
        $rateVerdict = "🟢 $RateTest 次连续请求未被拦截（状态集合 $($codes -join ',')）"
    }
}

# ------------------------------------------------------------------ 输出
$evidence = [pscustomobject]@{
    Schema      = 'seep.http.replay/1'
    GeneratedAt = (Get-Date).ToString('s')
    Request     = [pscustomobject]@{
        Url     = $Url
        Method  = $Method
        HasBody = (-not [string]::IsNullOrWhiteSpace($Body))
        Headers = ($headers.Keys | ForEach-Object { $_ })
    }
    Results     = $results
    RateTest    = $rateResults
    Verdict     = [pscustomobject]@{ Level = $verdictLevel; Text = $verdict; GateHeaders = $keyHeaders; SemanticDiff = $wrongHeaders; Rate = $rateVerdict }
    OutDir      = $OutDir
}

$jsonPath = Join-Path $OutDir 'evidence.json'
$evidence | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = New-Object System.Collections.Generic.List[object]
[void]$md.Add('# HTTP 重放举证报告')
[void]$md.Add('')
[void]$md.Add("- 生成: $($evidence.GeneratedAt)")
[void]$md.Add("- 请求: ``$Method $Url``")
[void]$md.Add("- 结论: **$verdict**")
if ($rateVerdict) { [void]$md.Add("- 频控: $rateVerdict") }
[void]$md.Add('')
[void]$md.Add('| 变体 | 说明 | 状态 | 长度 | 耗时 | 指纹 | 片段 |')
[void]$md.Add('| :--- | :--- | ---: | ---: | ---: | :--- | :--- |')
foreach ($r in $results) {
    $flag = if ($r.Status -ge 200 -and $r.Status -lt 400) { '' } else { ' ❌' }
    $sk = ($r.Sketch -replace '\|', '\|' -replace "`r?`n", ' ')
    if ($sk.Length -gt 60) { $sk = $sk.Substring(0, 60) + '…' }
    [void]$md.Add("| ``$($r.Variant)`` | $($r.Desc) | $($r.Status)$flag | $($r.Length) | $($r.Msn)ms | ``$($r.BodyHash)`` | $sk |")
}
[void]$md.Add('')
if ($keyHeaders.Count -gt 0) {
    [void]$md.Add("**门槛头**: $($keyHeaders -join ', ')")
}
if ($wrongHeaders.Count -gt 0) {
    [void]$md.Add('')
    [void]$md.Add("**语义变化（状态相同但内容不同）**: $($wrongHeaders -join ', ')")
}
$mdPath = Join-Path $OutDir 'report.md'
$md -join "`n" | Set-Content -LiteralPath $mdPath -Encoding UTF8

if ($Json) {
    $evidence | ConvertTo-Json -Depth 6
    return
}

Write-Host ''
Write-Host ("  {0,-16} {1,-6} {2,10} {3,8}  {4}" -f '变体', '状态', '长度', '耗时', '片段') -ForegroundColor White
Write-Host "  $('-' * 78)" -ForegroundColor DarkGray
foreach ($r in $results) {
    $c = if ($r.Status -ge 200 -and $r.Status -lt 400) { 'Green' } else { 'Red' }
    $sk = ($r.Sketch -replace "`r?`n", ' ')
    if ($sk.Length -gt 34) { $sk = $sk.Substring(0, 34) + '…' }
    Write-Host ("  {0,-16} {1,-6} {2,10} {3,7}ms  {4}" -f $r.Variant, $r.Status, $r.Length, $r.Msn, $sk) -ForegroundColor $c
}

Write-Host ''
Write-Host "== 结论 == $verdict" -ForegroundColor $(if ($verdictLevel -eq 'OK') { 'Green' } elseif ($verdictLevel -eq 'INVALID') { 'Gray' } else { 'Yellow' })
if ($rateVerdict) { Write-Host "  频控 : $rateVerdict" -ForegroundColor DarkYellow }
if ($wrongHeaders.Count -gt 0) { Write-Host "  语义 : $($wrongHeaders -join ', ') 状态相同但内容不同（可能是软性拦截）" -ForegroundColor DarkYellow }
Write-Host ''
Write-Host "  证据 : $jsonPath" -ForegroundColor Cyan
Write-Host "  报告 : $mdPath" -ForegroundColor Cyan

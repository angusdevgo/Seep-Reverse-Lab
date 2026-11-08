#Requires -Version 5.1
<#
  cms-fingerprint.ps1 —— 影视站 CMS / 源站指纹识别（whatweb 的针对性替代）
  ----------------------------------------------------------------
  为什么不用 whatweb：
    whatweb 是 Ruby 脚本，本机无 Ruby；而且它对「苹果CMS / 海洋CMS / TVBox 源」
    这类国内影视站特征覆盖很薄。本脚本专为这几类目标写，识别得准、结论说得清。

  识别维度：
    ① 服务栈        Server / X-Powered-By / Set-Cookie 名 / CDN 与 WAF 特征
    ② CMS 家族      苹果CMS(maccms10) / 海洋CMS(seacms) / 织梦 / WordPress / 自建
    ③ 采集接口      /api.php/provide/vod/?ac=list 是否可用（影视站的核心资产）
    ④ 播放器链路    MacPlayer / DPlayer / videojs / hls.js / aliplayer
    ⑤ TVBox 配置    /tvbox/config.json 类源配置（sites/lives 结构）
    ⑥ 暴露面        后台入口 / 备份文件 / .env / .git / install / phpinfo（只探测不改写）

  用法：
    powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url https://site.com
    powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url https://site.com -Deep
    powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url https://site.com -Json

  合规：
    只发 GET，只做固定小规模探测（≤20 个路径），默认 400ms 间隔。
    不做字典爆破、不提交表单、不尝试登录。目标须为自有或已授权站点。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Url,

    [string[]]$Header = @(),
    [string]$HeaderJson = '',
    [string]$Referer = '',
    [string]$UserAgent = '',
    [string]$Cookie = '',

    [switch]$Deep,                 # 额外的暴露面探测（备份/配置/后台）
    [int]$DelayMs = 400,
    [int]$TimeoutSec = 15,
    [string]$OutDir = '',
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

if ($Url -notmatch '^https?://') { $Url = 'https://' + $Url }
$base = $Url.TrimEnd('/')

$headers = ConvertTo-WebHeaderTable -HeaderLines $Header -HeaderJson $HeaderJson
if ($Referer) { $headers['Referer'] = $Referer }
if ($UserAgent) { $headers['User-Agent'] = $UserAgent }
if ($Cookie) { $headers['Cookie'] = $Cookie }
if (-not $headers.ContainsKey('User-Agent')) {
    $headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutDir = Join-Path (Get-WebWorkRoot) "cms-$stamp"
}
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

if (-not $Json) {
    Write-Host ''
    Write-Host '== 影视站 CMS / 源站指纹 ==' -ForegroundColor White
    Write-Host "  目标 : $base" -ForegroundColor DarkGray
    Write-Host "  模式 : $(if ($Deep) { 'Deep（含暴露面探测）' } else { '常规' })" -ForegroundColor DarkGray
    Write-Host "  产出 : $OutDir" -ForegroundColor DarkGray
}

# ------------------------------------------------------------------ 基础请求
$evidence = New-Object System.Collections.Generic.List[object]
function Add-Evidence {
    param([string]$Kind, [string]$Value, [string]$Source, [string]$Note = '')
    [void]$evidence.Add([pscustomobject]@{ Kind = $Kind; Value = $Value; Source = $Source; Note = $Note })
}

$rootResp = Invoke-WebFetch -Url $base -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 1048576
Add-Evidence -Kind 'http' -Value "HTTP $($rootResp.Status)" -Source 'GET /' -Note "长度 $($rootResp.Length)，耗时 $($rootResp.Msn)ms"

if ($rootResp.Status -eq 0) {
    $fail = [pscustomobject]@{
        Schema = 'seep.cms.fingerprint/1'; GeneratedAt = (Get-Date).ToString('s')
        Target = $base; Error = $rootResp.Error
        Verdict = [pscustomobject]@{ Level = 'FAIL'; Text = "⚪ 站点不可达：$($rootResp.Error)" }
        OutDir = $OutDir
    }
    $fail | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutDir 'evidence.json') -Encoding UTF8
    if ($Json) { $fail | ConvertTo-Json -Depth 6 } else { Write-Host "`n  结论: ⚪ 站点不可达（$($rootResp.Error)）" -ForegroundColor Yellow }
    return
}

$rootRespHeaders = $rootResp.Headers
$html = if ($rootResp.Body) { $rootResp.Body } else { '' }

# ------------------------------------------------------------------ ① 服务栈
$server = if ($rootRespHeaders.ContainsKey('Server')) { [string]$rootRespHeaders['Server'] } else { '' }
$poweredBy = if ($rootRespHeaders.ContainsKey('X-Powered-By')) { [string]$rootRespHeaders['X-Powered-By'] } else { '' }
$setCookie = if ($rootRespHeaders.ContainsKey('Set-Cookie')) { [string]$rootRespHeaders['Set-Cookie'] } else { '' }
if ($server) { Add-Evidence -Kind 'server' -Value $server -Source 'Server 头' }
if ($poweredBy) { Add-Evidence -Kind 'server' -Value $poweredBy -Source 'X-Powered-By' }

# CDN / WAF
$cdn = @()
if ($rootRespHeaders.Keys -match '^cf-ray$') { $cdn += 'Cloudflare' }
if ($rootRespHeaders.ContainsKey('Server') -and $server -match 'cloudflare') { $cdn += 'Cloudflare' }
if ($setCookie -match 'jsl_clearlocalstorage|__jsluid') { $cdn += '加速乐(Jiasule)' }
if ($rootRespHeaders.Keys -match '^x-via$|^x-cache$') { $cdn += 'CDN(X-Via/X-Cache)' }
if ($setCookie -match 'acw_sc__v2|acw_tc') { $cdn += '阿里云WAF' }
if ($html -match 'document\.cookie\s*=\s*["'']__jsl') { $cdn += '加速乐(JS挑战)' }
$cdn = @($cdn | Select-Object -Unique)
foreach ($c in $cdn) { Add-Evidence -Kind 'cdn' -Value $c -Source '响应头/HTML' }

# ------------------------------------------------------------------ ② CMS 家族（HTML 特征）
$cmsHits = New-Object System.Collections.Generic.List[object]
function Add-Cms {
    param([string]$Name, [string]$Signal, [int]$Weight)
    $cmsHits.Add([pscustomobject]@{ Name = $Name; Signal = $Signal; Weight = $Weight })
}

$patterns = @(
    @{ N = '苹果CMS (maccms10)'; R = 'Powered by\s*<a[^>]*>?Maccms|maccms\.com|/template/default/html/|mac_\w+\.js|maccms'; W = 3 },
    @{ N = '苹果CMS (v10 特征路径)'; R = 'application/admin|extend/base\.php|think\\'; W = 2 },
    @{ N = '海洋CMS (seacms)'; R = 'seacms|海洋影视|/template/default/|mytemplate|seacms\.com'; W = 3 },
    @{ N = '织梦 (DedeCMS)'; R = '/dede/|DedeCMS|Power by DedeCms'; W = 2 },
    @{ N = 'WordPress'; R = '/wp-content/|wp-includes|WordPress'; W = 2 },
    @{ N = '织梦/帝国/其他国内 CMS'; R = '帝国CMS|EmpireCMS|phpcms|ThinkPHP'; W = 1 }
)
foreach ($p in $patterns) {
    if ($html -match $p.R) { Add-Cms -Name $p.N -Signal "HTML 命中 /$($p.R)/" -Weight $p.W }
}

# 播放器链路
$players = @()
foreach ($p in @(
    @{ N = 'MacPlayer'; R = 'MacPlayer|player_aaaa|mac_player' },
    @{ N = 'DPlayer';   R = 'DPlayer' },
    @{ N = 'video.js';  R = 'video-js|videojs' },
    @{ N = 'hls.js';    R = 'hls\.js|Hls\.js' },
    @{ N = 'ckplayer';  R = 'ckplayer' },
    @{ N = 'aliplayer'; R = 'Aliplayer|aliplayer' },
    @{ N = 'jwplayer';  R = 'jwplayer' },
    @{ N = 'artplayer'; R = 'artplayer' }
)) {
    if ($html -match $p.R) { $players += $p.N }
}
foreach ($p in $players) { Add-Evidence -Kind 'player' -Value $p -Source 'HTML' }

# m3u8 直出
$m3u8InHtml = ([regex]::Matches($html, 'https?://[^"''\s]+\.m3u8[^"''\s]*')).Count
if ($m3u8InHtml -gt 0) { Add-Evidence -Kind 'stream' -Value "HTML 内直出 $m3u8InHtml 个 m3u8 地址" -Source 'HTML' -Note '说明播放链路未做二次解析' }

# ------------------------------------------------------------------ ③ 采集接口（影视站核心资产）
function Get-BaseOrigin {
    try { $u = [Uri]$base; return "$($u.Scheme)://$($u.Authority)" } catch { return $base }
}
$origin = Get-BaseOrigin

$apiCandidates = @(
    "$origin/api.php/provide/vod/?ac=list",
    "$origin/api.php/provide/vod/at/xml/?ac=list",
    "$origin/api.php/provide/vod/?ac=list&pg=1"
)

$apiResult = $null
foreach ($apiUrl in $apiCandidates) {
    $r = Invoke-WebFetch -Url $apiUrl -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 262144
    if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
    $isJson = ($r.ContentType -match 'json') -or ($r.Body -match '^\s*[\{\[]')
    $looksVod = ($r.Body -match '"code"\s*:' -and $r.Body -match '"list"\s*:|"data"\s*:|vod_')
    if ($r.Ok -and $isJson -and $looksVod) {
        $seg = $r.Body.Substring(0, [Math]::Min(200, $r.Body.Length))
        $apiResult = [pscustomobject]@{
            Url    = $apiUrl
            Status = $r.Status
            Length = $r.Length
            Sketch = $seg
        }
        Add-Evidence -Kind 'api' -Value '采集接口可用' -Source $apiUrl -Note "HTTP $($r.Status)，$($r.Length) 字节"
        if ($r.Body -match 'provide/vod') { Add-Cms -Name '苹果CMS 采集接口' -Signal 'api.php/provide/vod 响应有效 JSON' -Weight 4 }
        break
    }
    elseif ($r.Status -in 200, 301, 302, 403) {
        Add-Evidence -Kind 'api' -Value "探测 $($r.Status)" -Source $apiUrl -Note '存在但未返回有效采集 JSON'
    }
}

# ------------------------------------------------------------------ ④ TVBox 源配置
$tvboxCandidates = @(
    "$origin/tvbox/config.json",
    "$origin/config.json",
    "$origin/tvbox.json"
)
$tvboxResult = $null
foreach ($tu in $tvboxCandidates) {
    $r = Invoke-WebFetch -Url $tu -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 262144
    if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
    if ($r.Ok -and $r.Body -match '"sites"\s*:' ) {
        $tvboxResult = [pscustomobject]@{ Url = $tu; Status = $r.Status; Length = $r.Length }
        Add-Evidence -Kind 'tvbox' -Value 'TVBox 源配置可访问' -Source $tu -Note "含 sites 数组，$($r.Length) 字节"
        # 注意：TVBox 配置是「聚合源」特征，不是 CMS 家族，不参与 CMS 排名
        break
    }
}

# ------------------------------------------------------------------ ⑤ 后台 / 暴露面
$probePaths = @(
    @{ P = '/admin.php';        K = '后台入口'; Lv = 'info' },
    @{ P = '/admin/';           K = '后台目录'; Lv = 'info' },
    @{ P = '/admin/login.php';  K = '后台登录'; Lv = 'info' }
)
if ($Deep) {
    $probePaths += @(
        @{ P = '/.env';             K = '配置泄露'; Lv = 'high' },
        @{ P = '/.git/config';      K = '源码仓库泄露'; Lv = 'high' },
        @{ P = '/install/';         K = '安装向导残留'; Lv = 'high' },
        @{ P = '/phpinfo.php';      K = 'phpinfo 泄露'; Lv = 'high' },
        @{ P = '/backup.zip';       K = '备份文件'; Lv = 'high' },
        @{ P = '/www.zip';          K = '备份文件'; Lv = 'high' },
        @{ P = '/data/';            K = '数据目录'; Lv = 'medium' },
        @{ P = '/runtime/';         K = '运行时目录'; Lv = 'medium' }
    )
}

$exposures = New-Object System.Collections.Generic.List[object]
foreach ($item in $probePaths) {
    $u = "$origin$($item.P)"
    $r = Invoke-WebFetch -Url $u -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 65536
    if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }

    $hit = $false
    $desc = ''
    if ($r.Status -eq 200 -and $r.Length -gt 0) {
        if ($item.P -eq '/.env' -and $r.Body -match '(?m)^\s*[A-Z_]+=') { $hit = $true; $desc = '.env 内容可读' }
        elseif ($item.P -eq '/.git/config' -and $r.Body -match '\[core\]') { $hit = $true; $desc = '.git/config 可读' }
        elseif ($item.K -eq '备份文件' -and $r.ContentType -notmatch 'html') { $hit = $true; $desc = "备份文件可下载（$($r.ContentType)）" }
        elseif ($item.K -eq 'phpinfo 泄露' -and $r.Body -match 'PHP Version|phpinfo\(\)') { $hit = $true; $desc = 'phpinfo 页面可读' }
        elseif ($item.K -match '后台' -and $r.Body -match '(?i)login|password|登录|管理') { $hit = $true; $desc = "后台入口可访问（HTTP $($r.Status)）" }
        elseif ($item.K -match '目录' -and $r.Body -match '(?i)Index of /|Directory listing') { $hit = $true; $desc = '目录可列出' }
    }
    elseif ($r.Status -in 401, 403) {
        $hit = $true
        $desc = "存在但被拒（HTTP $($r.Status)）"
    }

    if ($hit) {
        [void]$exposures.Add([pscustomobject]@{
            Path = $item.P; Kind = $item.K; Level = $item.Lv
            Status = $r.Status; Length = $r.Length; Desc = $desc
        })
        Add-Evidence -Kind 'exposure' -Value "$($item.K)：$desc" -Source $u
    }
}

# ------------------------------------------------------------------ 汇总
$cmsSorted = @($cmsHits | Sort-Object Weight -Descending)
$topCms = if ($cmsSorted.Count -gt 0) { $cmsSorted[0] } else { $null }
$confidence = 0
foreach ($h in $cmsSorted) { $confidence += $h.Weight }
$confidence = [Math]::Min(100, $confidence * 20)

$highRisk = @($exposures | Where-Object { $_.Level -eq 'high' })

$verdict = ''
$level = ''
if ($topCms -and $confidence -ge 60) {
    $verdict = "🟢 识别为：$($topCms.Name)（置信度 $confidence%）"
    $level = 'OK'
}
elseif ($topCms) {
    $verdict = "🟡 疑似：$($topCms.Name)（置信度 $confidence%，证据偏少）"
    $level = 'P1'
}
else {
    $verdict = '⚪ 未能识别 CMS 家族 —— 可能是自建站 / 全静态 / 有强 WAF 拦截'
    $level = 'UNKNOWN'
}

$advice = New-Object System.Collections.Generic.List[string]
if ($apiResult) { [void]$advice.Add("采集接口直连可用（$($apiResult.Url)）→ 可直接跑 hls-analyze / http-replay 验证取流链路") }
else { [void]$advice.Add('采集接口未直连成功 → 用 ffuf 枚举路径，或用 js-reverse 抓前端实际请求的接口') }
if ($cdn.Count -gt 0) { [void]$advice.Add("存在 CDN/WAF（$($cdn -join ', ')）→ 先过 js-reverse 拿真实 Cookie，再重放") }
if ($players.Count -gt 0) { [void]$advice.Add("播放器：$($players -join ', ') → 取 m3u8 后交 hls-analyze 判定加密/防盗链") }
if ($highRisk.Count -gt 0) { [void]$advice.Add("⚠️ 高危暴露 $($highRisk.Count) 项：$((($highRisk | ForEach-Object { $_.Path }) -join ', '))") }
if ($tvboxResult) { [void]$advice.Add("TVBox 源配置可读（$($tvboxResult.Url)）→ 这是源站的聚合配置，比单站更有价值") }

# ------------------------------------------------------------------ 输出
$payload = [pscustomobject]@{
    Schema      = 'seep.cms.fingerprint/1'
    GeneratedAt = (Get-Date).ToString('s')
    Target      = $base
    Http        = [pscustomobject]@{
        Status = $rootResp.Status; Length = $rootResp.Length; Msn = $rootResp.Msn
        Server = $server; PoweredBy = $poweredBy
    }
    Cdn         = $cdn
    Cms         = @($cmsSorted | Select-Object -First 5)
    Confidence  = $confidence
    Players     = $players
    M3u8InHtml  = $m3u8InHtml
    Api         = $apiResult
    TvBox       = $tvboxResult
    Exposures   = $exposures
    Evidence    = $evidence
    Verdict     = [pscustomobject]@{ Level = $level; Text = $verdict; Advice = $advice.ToArray() }
    OutDir      = $OutDir
}

$jsonPath = Join-Path $OutDir 'evidence.json'
$payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

# markdown
$md = New-Object System.Collections.Generic.List[string]
[void]$md.Add('# 影视站 CMS / 源站指纹报告')
[void]$md.Add('')
[void]$md.Add("- 目标: ``$base``")
[void]$md.Add("- 时间: $($payload.GeneratedAt)")
[void]$md.Add("- 结论: **$verdict**")
[void]$md.Add('')
[void]$md.Add('## 1. 服务栈')
[void]$md.Add('')
[void]$md.Add('| 项 | 值 |')
[void]$md.Add('| :--- | :--- |')
[void]$md.Add("| HTTP | $($rootResp.Status) / $($rootResp.Length) B / $($rootResp.Msn) ms |")
[void]$md.Add("| Server | $(if ($server) { $server } else { '—' }) |")
[void]$md.Add("| X-Powered-By | $(if ($poweredBy) { $poweredBy } else { '—' }) |")
[void]$md.Add("| CDN/WAF | $(if ($cdn.Count) { $cdn -join ', ' } else { '—' }) |")
[void]$md.Add('')
if ($cmsSorted.Count -gt 0) {
    [void]$md.Add('## 2. CMS 判定证据')
    [void]$md.Add('')
    [void]$md.Add('| 候选 | 权重 | 证据 |')
    [void]$md.Add('| :--- | ---: | :--- |')
    foreach ($c in $cmsSorted) { [void]$md.Add("| $($c.Name) | $($c.Weight) | $($c.Signal) |") }
    [void]$md.Add('')
}
if ($apiResult -or $tvboxResult -or $players.Count -gt 0 -or $m3u8InHtml -gt 0) {
    [void]$md.Add('## 3. 源与播放链路')
    [void]$md.Add('')
    if ($apiResult) { [void]$md.Add("- **采集接口可用**：``$($apiResult.Url)``（HTTP $($apiResult.Status)，$($apiResult.Length) B）") }
    if ($tvboxResult) { [void]$md.Add("- **TVBox 源配置**：``$($tvboxResult.Url)``（HTTP $($tvboxResult.Status)）") }
    if ($players.Count -gt 0) { [void]$md.Add("- 播放器：$($players -join ', ')") }
    if ($m3u8InHtml -gt 0) { [void]$md.Add("- HTML 内直出 $m3u8InHtml 个 m3u8 地址（播放链路未做二次解析）") }
    [void]$md.Add('')
}
if ($exposures.Count -gt 0) {
    [void]$md.Add('## 4. 暴露面')
    [void]$md.Add('')
    [void]$md.Add('| 路径 | 类型 | 等级 | 状态 | 说明 |')
    [void]$md.Add('| :--- | :--- | :--- | ---: | :--- |')
    foreach ($e in $exposures) {
        [void]$md.Add("| ``$($e.Path)`` | $($e.Kind) | $($e.Level) | $($e.Status) | $($e.Desc) |")
    }
    [void]$md.Add('')
}
[void]$md.Add('## 5. 下一步建议')
[void]$md.Add('')
foreach ($a in $advice) { [void]$md.Add("- $a") }
$mdPath = Join-Path $OutDir 'report.md'
$md -join "`n" | Set-Content -LiteralPath $mdPath -Encoding UTF8

if ($Json) {
    $payload | ConvertTo-Json -Depth 8
    return
}

# 控制台
Write-Host ''
Write-Host ("  服务栈  : HTTP {0} · {1} B · {2}" -f $rootResp.Status, $rootResp.Length, $(if ($server) { $server } else { 'Server 未暴露' })) -ForegroundColor Gray
Write-Host ("  CDN/WAF : {0}" -f $(if ($cdn.Count) { $cdn -join ', ' } else { '未检出' })) -ForegroundColor Gray
if ($cmsSorted.Count -gt 0) {
    Write-Host '  CMS 候选:' -ForegroundColor White
    foreach ($c in ($cmsSorted | Select-Object -First 4)) {
        Write-Host ("    [w={0}] {1}  ← {2}" -f $c.Weight, $c.Name, $c.Signal) -ForegroundColor DarkYellow
    }
}
if ($apiResult) { Write-Host "  采集接口: ✅ $($apiResult.Url)" -ForegroundColor Green }
if ($tvboxResult) { Write-Host "  TVBox   : ✅ $($tvboxResult.Url)" -ForegroundColor Green }
if ($players.Count -gt 0) { Write-Host "  播放器  : $($players -join ', ')" -ForegroundColor Gray }
if ($exposures.Count -gt 0) {
    Write-Host '  暴露面:' -ForegroundColor White
    foreach ($e in $exposures) {
        $c = if ($e.Level -eq 'high') { 'Red' } elseif ($e.Level -eq 'medium') { 'Yellow' } else { 'DarkGray' }
        Write-Host ("    [{0,-6}] {1,-22} {2}  {3}" -f $e.Level, $e.Path, $e.Status, $e.Desc) -ForegroundColor $c
    }
}
Write-Host ''
Write-Host "== 结论 == $verdict" -ForegroundColor $(if ($level -eq 'OK') { 'Green' } elseif ($level -eq 'UNKNOWN') { 'Gray' } else { 'Yellow' })
foreach ($a in $advice) { Write-Host "  · $a" -ForegroundColor DarkYellow }
Write-Host ''
Write-Host "  证据 : $jsonPath" -ForegroundColor Cyan
Write-Host "  报告 : $mdPath" -ForegroundColor Cyan

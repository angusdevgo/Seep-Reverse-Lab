#Requires -Version 5.1
<#
  hls-analyze.ps1 —— HLS / m3u8 取证器（Seep Web 工具箱 P0 能力）
  ----------------------------------------------------------------
  解决什么问题：
    影视源逆向里"播放不出来"有 6 种完全不同的根因，靠肉眼看 playlist 分不清：
      ① 防盗链（缺 Referer / UA / Origin）
      ② key 鉴权（EXT-X-KEY 的 URI 需要 token 或登录态）
      ③ AES-128 加密但 key 可取 → 可解
      ④ SAMPLE-AES / fMP4（EXT-X-MAP）→ 需专用解封装
      ⑤ DRM（Widevine / FairPlay / PlayReady）→ 密码学保护，不可逆向
      ⑥ 播放列表本身失效（站返回 HTML 错误页伪装成 m3u8）

  本脚本把 6 种根因一次性判定，并给出「能否取证闭环」的结论 + 证据 JSON。

  用法：
    # 最简：给一个 m3u8 地址
    powershell -File Tool\scripts\web\hls-analyze.ps1 -Url "https://cdn.example.com/hls/index.m3u8"

    # 带防盗链头（影视站最常见）
    powershell -File Tool\scripts\web\hls-analyze.ps1 -Url "<m3u8>" -Referer "https://site.com/" -UserAgent "<UA>"

    # 从浏览器里复制的 curl 命令直接喂进来
    powershell -File Tool\scripts\web\hls-analyze.ps1 -Curl "curl 'https://...' -H 'Referer: ...' -H 'User-Agent: ...'"

    # 已下载到本地的 playlist（配合 -BaseUrl 解析相对分片）
    powershell -File Tool\scripts\web\hls-analyze.ps1 -Playlist .\index.m3u8 -BaseUrl "https://cdn.example.com/hls/"

  产出：
    <OutDir>\evidence.json    机器可读（MCP / 报告直接引用）
    <OutDir>\report.md        人可读（含结论与修复建议）
    <OutDir>\probe.ts         ffmpeg 实解产出（验证"能播"的物证）
#>
[CmdletBinding()]
param(
    [string]$Url = '',
    [string]$Playlist = '',
    [string]$BaseUrl = '',

    [string[]]$Header = @(),
    [string]$HeaderJson = '',
    [string]$Curl = '',
    [string]$Referer = '',
    [string]$UserAgent = '',
    [string]$Cookie = '',

    [string]$Variant = 'best',      # best | all | 序号(0 起)
    [int]$VerifySeconds = 15,
    [switch]$NoVerify,
    [switch]$NoKeyProbe,
    [string]$OutDir = '',
    [switch]$Json,
    [int]$TimeoutSec = 30
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')

# ------------------------------------------------------------------ 工具函数
function Resolve-HlsUri {
    param([string]$Base, [string]$Rel)
    if ([string]::IsNullOrWhiteSpace($Rel)) { return '' }
    if ($Rel -match '^https?://') { return $Rel }
    if ([string]::IsNullOrWhiteSpace($Base)) { return $Rel }
    try { return ([Uri]::new([Uri]$Base, $Rel)).AbsoluteUri } catch { return $Rel }
}

function ConvertFrom-HlsAttributes {
    param([string]$Line)
    $h = @{}
    # METHOD=AES-128,URI="key.bin",IV=0x00...
    foreach ($m in [regex]::Matches($Line, '([A-Z0-9\-]+)=("[^"]*"|[^,]*)')) {
        $k = $m.Groups[1].Value
        $v = $m.Groups[2].Value.Trim('"')
        $h[$k] = $v
    }
    return $h
}

function Get-HlsDrmKind {
    param([hashtable]$Attrs)
    $kf = ''
    if ($Attrs.ContainsKey('KEYFORMAT')) { $kf = [string]$Attrs['KEYFORMAT'] }
    $method = ''
    if ($Attrs.ContainsKey('METHOD')) { $method = [string]$Attrs['METHOD'] }

    if ($kf -match 'edef8ba9-79d6-4ace-a3c8-27dcd51d21ed') { return 'Widevine' }
    if ($kf -match '94ce86fb-07ff-4f43-adb8-93d2fa968ca2' -or $kf -match 'streamingkeydelivery') { return 'FairPlay' }
    if ($kf -match '9a04f079-9840-4286-ab92-e65be0885f95' -or $kf -match 'playready') { return 'PlayReady' }
    if ($kf -match 'clearkey') { return 'ClearKey' }
    if ($method -eq 'SAMPLE-AES-CTR') { return 'SAMPLE-AES-CTR' }
    if ($method -eq 'SAMPLE-AES') { return 'SAMPLE-AES' }
    return ''
}

function ConvertTo-HeaderString {
    param([hashtable]$Headers, [string]$ExtraReferer, [string]$ExtraUa, [string]$ExtraCookie)
    $h = @{}
    foreach ($k in $Headers.Keys) { $h[$k] = $Headers[$k] }
    if (-not [string]::IsNullOrWhiteSpace($ExtraReferer) -and -not $h.ContainsKey('Referer')) { $h['Referer'] = $ExtraReferer }
    if (-not [string]::IsNullOrWhiteSpace($ExtraUa) -and -not $h.ContainsKey('User-Agent')) { $h['User-Agent'] = $ExtraUa }
    if (-not [string]::IsNullOrWhiteSpace($ExtraCookie) -and -not $h.ContainsKey('Cookie')) { $h['Cookie'] = $ExtraCookie }
    if ($h.Count -eq 0) { return '' }
    $sb = New-Object System.Text.StringBuilder
    foreach ($k in $h.Keys) { [void]$sb.Append("${k}: $($h[$k])`r`n") }
    return $sb.ToString()
}

# ------------------------------------------------------------------ 输入归一
$headers = ConvertTo-WebHeaderTable -HeaderLines $Header -HeaderJson $HeaderJson -Curl $Curl
if (-not [string]::IsNullOrWhiteSpace($Curl) -and [string]::IsNullOrWhiteSpace($Url)) {
    $Url = Get-WebUrlFromCurl -Curl $Curl
}
if (-not [string]::IsNullOrWhiteSpace($Referer)) { $headers['Referer'] = $Referer }
if (-not [string]::IsNullOrWhiteSpace($UserAgent)) { $headers['User-Agent'] = $UserAgent }
if (-not [string]::IsNullOrWhiteSpace($Cookie)) { $headers['Cookie'] = $Cookie }
if ([string]::IsNullOrWhiteSpace($Url) -and [string]::IsNullOrWhiteSpace($Playlist)) {
    throw '必须提供 -Url 或 -Playlist（或 -Curl）'
}

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutDir = Join-Path (Get-WebWorkRoot) "hls-$stamp"
}
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

if (-not $Json) {
    Write-Host ''
    Write-Host '== HLS / m3u8 取证 ==' -ForegroundColor White
    Write-Host "  目标   : $(if ($Url) { $Url } else { $Playlist })" -ForegroundColor DarkGray
    Write-Host "  请求头 : $($headers.Keys -join ', ')" -ForegroundColor DarkGray
    Write-Host "  产出   : $OutDir" -ForegroundColor DarkGray
}

# ------------------------------------------------------------------ 拉取 playlist
$fetchInfo = $null
$playlistText = ''
$playlistBase = ''

if (-not [string]::IsNullOrWhiteSpace($Playlist)) {
    if (-not (Test-Path -LiteralPath $Playlist)) { throw "Playlist 文件不存在: $Playlist" }
    $playlistText = Get-Content -LiteralPath $Playlist -Raw -Encoding UTF8
    $playlistBase = if ($BaseUrl) { $BaseUrl } else { '' }
    $fetchInfo = [pscustomobject]@{ Ok = $true; Status = 200; Length = $playlistText.Length; ContentType = 'local'; Error = ''; Msn = 0 }
}
else {
    $r = Invoke-WebFetch -Url $Url -Headers $headers -TimeoutSec $TimeoutSec
    $fetchInfo = $r
    $playlistText = $r.Body
    $playlistBase = $Url
}

# 伪装成 m3u8 的错误页判定
$looksLikeHls = ($playlistText -match '#EXTM3U')
$errorPage = (-not $looksLikeHls)

$diagnosis = New-Object System.Collections.ArrayList
if ($errorPage) {
    [void]$diagnosis.Add([pscustomobject]@{
        Code   = 'NOT_A_PLAYLIST'
        Level  = 'P0'
        Detail = "返回内容不是 m3u8（HTTP $($fetchInfo.Status)，$($fetchInfo.Length) 字节，CT=$($fetchInfo.ContentType)）。"
        Advice = '站点可能返回了 HTML 错误页 / 登录页 / 风控页。先看 evidence.json 的 fetch.head，再补 Referer / Cookie / UA。'
    })
}

# ------------------------------------------------------------------ 解析
$variants = @()
$media = $null

if ($looksLikeHls) {
    $lines = $playlistText -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
    $isMaster = ($playlistText -match '#EXT-X-STREAM-INF')

    if ($isMaster) {
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -like '#EXT-X-STREAM-INF*') {
                $attrs = ConvertFrom-HlsAttributes -Line ($lines[$i] -replace '^#EXT-X-STREAM-INF:', '')
                $uri = ''
                for ($j = $i + 1; $j -lt $lines.Count; $j++) {
                    if (-not $lines[$j].StartsWith('#')) { $uri = $lines[$j]; break }
                }
                if ($uri) {
                    $variants += [pscustomobject]@{
                        Bandwidth  = if ($attrs.ContainsKey('BANDWIDTH')) { [int64]$attrs['BANDWIDTH'] } else { 0 }
                        Resolution = if ($attrs.ContainsKey('RESOLUTION')) { $attrs['RESOLUTION'] } else { '' }
                        Codecs     = if ($attrs.ContainsKey('CODECS')) { $attrs['CODECS'] } else { '' }
                        Uri        = (Resolve-HlsUri -Base $playlistBase -Rel $uri)
                        Raw        = $uri
                    }
                }
            }
        }
    }

    # 解析媒体 playlist（master 则不适用，需再取一次子 playlist —— 交给下面按 variant 拉）
    $media = [pscustomobject]@{
        IsMaster          = $isMaster
        Version           = ''
        TargetDuration    = 0
        MediaSequence     = 0
        Segments          = @()
        Keys              = @()
        Maps              = @()
        Discontinuities    = 0
        EndList           = ($playlistText -match '#EXT-X-ENDLIST')
        TotalDuration     = 0.0
    }

    if (-not $isMaster) {
        # 注意：PS 的 `+=` 作用在 ArrayList / List<T> 上会退化成 Object[]，必须用 .Add()
        $segments = New-Object System.Collections.Generic.List[object]
        $keys = New-Object System.Collections.Generic.List[object]
        $maps = New-Object System.Collections.Generic.List[object]
        $dur = 0.0
        $pendingDur = 0.0

        foreach ($ln in $lines) {
            if ($ln -match '^#EXT-X-VERSION:(.+)$') { $media.Version = $Matches[1].Trim() }
            elseif ($ln -match '^#EXT-X-TARGETDURATION:(.+)$') { $media.TargetDuration = [double]$Matches[1].Trim() }
            elseif ($ln -match '^#EXT-X-MEDIA-SEQUENCE:(.+)$') { $media.MediaSequence = [int64]$Matches[1].Trim() }
            elseif ($ln -match '^#EXT-X-DISCONTINUITY\s*$') { $media.Discontinuities++ }
            elseif ($ln -match '^#EXT-X-KEY:(.+)$') {
                $a = ConvertFrom-HlsAttributes -Line $Matches[1]
                $uriRaw = if ($a.ContainsKey('URI')) { [string]$a['URI'] } else { '' }
                [void]$keys.Add([pscustomobject]@{
                    Method    = if ($a.ContainsKey('METHOD')) { [string]$a['METHOD'] } else { '' }
                    Uri       = (Resolve-HlsUri -Base $playlistBase -Rel $uriRaw)
                    UriRaw    = $uriRaw
                    Iv        = if ($a.ContainsKey('IV')) { [string]$a['IV'] } else { '' }
                    KeyFormat = if ($a.ContainsKey('KEYFORMAT')) { [string]$a['KEYFORMAT'] } else { 'identity' }
                    DrmKind   = (Get-HlsDrmKind -Attrs $a)
                })
            }
            elseif ($ln -match '^#EXT-X-MAP:(.+)$') {
                $a = ConvertFrom-HlsAttributes -Line $Matches[1]
                $uriRaw = if ($a.ContainsKey('URI')) { [string]$a['URI'] } else { '' }
                [void]$maps.Add([pscustomobject]@{ Uri = (Resolve-HlsUri -Base $playlistBase -Rel $uriRaw); UriRaw = $uriRaw })
            }
            elseif ($ln -match '^#EXTINF:([0-9.]+)') {
                $pendingDur = [double]$Matches[1]
                $dur += $pendingDur
            }
            elseif (-not $ln.StartsWith('#')) {
                [void]$segments.Add((Resolve-HlsUri -Base $playlistBase -Rel $ln))
                $pendingDur = 0.0
            }
        }
        $media.Segments = $segments.ToArray()
        $media.Keys = $keys.ToArray()
        $media.Maps = $maps.ToArray()
        $media.TotalDuration = [math]::Round($dur, 2)
    }
}

# ------------------------------------------------------------------ 选 variant 并下钻
$chosen = $null
$targetUri = $Url
$targetMedia = $media

function Get-HlsMediaFromUri {
    param([string]$Uri, [hashtable]$Headers, [int]$Timeout)
    $r = Invoke-WebFetch -Url $Uri -Headers $Headers -TimeoutSec $Timeout
    $txt = $r.Body
    if ($txt -notmatch '#EXTM3U') {
        return [pscustomobject]@{ Fetch = $r; Media = $null; Text = $txt }
    }
    $ls = $txt -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
    $segs = New-Object System.Collections.Generic.List[object]
    $keys = New-Object System.Collections.Generic.List[object]
    $maps = New-Object System.Collections.Generic.List[object]
    $dur = 0.0
    $td = 0.0; $ms = 0; $ver = ''; $disc = 0
    foreach ($ln in $ls) {
        if ($ln -match '^#EXT-X-VERSION:(.+)$') { $ver = $Matches[1].Trim() }
        elseif ($ln -match '^#EXT-X-TARGETDURATION:(.+)$') { $td = [double]$Matches[1].Trim() }
        elseif ($ln -match '^#EXT-X-MEDIA-SEQUENCE:(.+)$') { $ms = [int64]$Matches[1].Trim() }
        elseif ($ln -match '^#EXT-X-DISCONTINUITY\s*$') { $disc++ }
        elseif ($ln -match '^#EXT-X-KEY:(.+)$') {
            $a = ConvertFrom-HlsAttributes -Line $Matches[1]
            $uriRaw = if ($a.ContainsKey('URI')) { [string]$a['URI'] } else { '' }
            [void]$keys.Add([pscustomobject]@{
                Method    = if ($a.ContainsKey('METHOD')) { [string]$a['METHOD'] } else { '' }
                Uri       = (Resolve-HlsUri -Base $Uri -Rel $uriRaw)
                UriRaw    = $uriRaw
                Iv        = if ($a.ContainsKey('IV')) { [string]$a['IV'] } else { '' }
                KeyFormat = if ($a.ContainsKey('KEYFORMAT')) { [string]$a['KEYFORMAT'] } else { 'identity' }
                DrmKind   = (Get-HlsDrmKind -Attrs $a)
            })
        }
        elseif ($ln -match '^#EXT-X-MAP:(.+)$') {
            $a = ConvertFrom-HlsAttributes -Line $Matches[1]
            $uriRaw = if ($a.ContainsKey('URI')) { [string]$a['URI'] } else { '' }
            [void]$maps.Add([pscustomobject]@{ Uri = (Resolve-HlsUri -Base $Uri -Rel $uriRaw); UriRaw = $uriRaw })
        }
        elseif ($ln -match '^#EXTINF:([0-9.]+)') { $dur += [double]$Matches[1] }
        elseif (-not $ln.StartsWith('#')) { [void]$segs.Add((Resolve-HlsUri -Base $Uri -Rel $ln)) }
    }
    $m = [pscustomobject]@{
        IsMaster       = $false
        Version        = $ver
        TargetDuration = $td
        MediaSequence  = $ms
        Segments       = $segs.ToArray()
        Keys           = $keys.ToArray()
        Maps           = $maps.ToArray()
        Discontinuities = $disc
        EndList        = ($txt -match '#EXT-X-ENDLIST')
        TotalDuration  = [math]::Round($dur, 2)
    }
    return [pscustomobject]@{ Fetch = $r; Media = $m; Text = $txt }
}

if ($looksLikeHls -and $media -and $media.IsMaster -and $variants.Count -gt 0) {
    if ($Variant -eq 'all') {
        $chosen = $variants
    }
    elseif ($Variant -match '^\d+$') {
        $idx = [int]$Variant
        if ($idx -lt $variants.Count) { $chosen = @($variants[$idx]) } else { $chosen = @($variants[0]) }
    }
    else {
        $chosen = @($variants | Sort-Object Bandwidth -Descending | Select-Object -First 1)
    }

    if ($chosen.Count -gt 0) {
        $targetUri = $chosen[0].Uri
        $sub = Get-HlsMediaFromUri -Uri $targetUri -Headers $headers -Timeout $TimeoutSec
        $targetMedia = $sub.Media
        if (-not $sub.Media) {
            [void]$diagnosis.Add([pscustomobject]@{
                Code   = 'VARIANT_NOT_PLAYLIST'
                Level  = 'P0'
                Detail = "子播放列表 $targetUri 返回的不是 m3u8（HTTP $($sub.Fetch.Status)）。"
                Advice = '子 playlist 也受防盗链保护；确认头是否对子域名同样有效（不同 CDN 域可能不同策略）。'
            })
        }
    }
}

# ------------------------------------------------------------------ 分片特征
$segPattern = ''
$tokenParams = @()
$segHosts = @()
if ($targetMedia -and $targetMedia.Segments.Count -gt 0) {
    $first = $targetMedia.Segments[0]
    $segPattern = ($first -replace '\d{3,}', '{n}')
    $segHosts = @($targetMedia.Segments | ForEach-Object { try { ([Uri]$_).Host } catch { '' } } | Sort-Object -Unique)
    $q = @()
    foreach ($s in ($targetMedia.Segments | Select-Object -First 20)) {
        try {
            $u = [Uri]$s
            if ($u.Query) {
                foreach ($pair in ($u.Query.TrimStart('?') -split '&')) {
                    $k = ($pair -split '=')[0]
                    if ($k) { $q += $k }
                }
            }
        }
        catch { }
    }
    $tokenParams = @($q | Group-Object | Where-Object { $_.Name -match '(?i)sign|token|auth|expire|secret|key|e$|st$|t$|wssecret|txsecret' } | ForEach-Object { $_.Name })
}

# ------------------------------------------------------------------ key 鉴权探测
$keyProbes = @()
if (-not $NoKeyProbe -and $targetMedia -and $targetMedia.Keys.Count -gt 0) {
    $seen = @{}
    foreach ($k in $targetMedia.Keys) {
        if ($k.Method -eq 'NONE' -or [string]::IsNullOrWhiteSpace($k.Uri)) { continue }
        if ($seen.ContainsKey($k.Uri)) { continue }
        $seen[$k.Uri] = $true

        $withH = Invoke-WebFetch -Url $k.Uri -Headers $headers -TimeoutSec $TimeoutSec -MaxBodyBytes 256
        $bareHeaders = @{}
        $bare = Invoke-WebFetch -Url $k.Uri -Headers $bareHeaders -TimeoutSec $TimeoutSec -MaxBodyBytes 256

        $verdict = 'UNKNOWN'
        $note = ''
        if ($withH.Ok -and $withH.Length -eq 16) { $verdict = 'KEY_OK' ; $note = '返回 16 字节，标准 AES-128 key，可直接解密' }
        elseif ($withH.Ok -and $withH.Length -gt 0 -and $withH.Length -ne 16) {
            $verdict = 'KEY_SUSPECT'
            $note = "返回 $($withH.Length) 字节，非标准 16 字节 key（可能是 DRM 许可证响应或错误页）"
        }
        elseif ($withH.Status -in 401, 403) {
            $verdict = 'KEY_DENIED'
            $note = "带头仍被拒（HTTP $($withH.Status)），key 需要登录态 / 一次性 token / 设备指纹"
        }
        elseif ($withH.Status -eq 0) { $verdict = 'KEY_ERROR'; $note = $withH.Error }
        else { $verdict = 'KEY_UNEXPECTED'; $note = "HTTP $($withH.Status)，$($withH.Length) 字节" }

        $refDelta = ''
        if ($bare.Status -ne $withH.Status) { $refDelta = "去头后 HTTP $($bare.Status)（带头 $($withH.Status)）→ 头是关键" }
        elseif ($bare.Status -eq $withH.Status -and $withH.Status -eq 200) { $refDelta = '去头后仍 200 → key 无鉴权' }

        $keyProbes += [pscustomobject]@{
            Uri     = $k.Uri
            Method  = $k.Method
            WithHeadersStatus = $withH.Status
            WithHeadersLength = $withH.Length
            BareStatus        = $bare.Status
            Verdict           = $verdict
            Note              = $note
            HeaderDelta       = $refDelta
        }
    }
}

# ------------------------------------------------------------------ 解密可行性判定
$drmKinds = @()
if ($targetMedia) { $drmKinds = @($targetMedia.Keys | ForEach-Object { $_.DrmKind } | Where-Object { $_ } | Sort-Object -Unique) }
$sampAes = @($targetMedia.Keys | Where-Object { $_.Method -like 'SAMPLE-AES*' })

$decrypt = [pscustomobject]@{
    Possible   = $false
    Scheme     = 'NONE'
    Reason     = ''
    Drm        = ($drmKinds -join ',')
    Fmp4       = ($targetMedia -and $targetMedia.Maps.Count -gt 0)
    NeedsHeaders = ($headers.Count -gt 0)
}

if ($drmKinds.Count -gt 0) {
    $decrypt.Scheme = 'DRM'
    $decrypt.Possible = $false
    $decrypt.Reason = "检测到 DRM（$($drmKinds -join ', ')）—— 受版权保护体系约束，密钥由许可证服务器下发，不属于可逆向范围。"
    [void]$diagnosis.Add([pscustomobject]@{
        Code   = 'DRM_PROTECTED'
        Level  = 'STOP'
        Detail = $decrypt.Reason
        Advice = '按 G-Auth 边界终止取证：写"受 DRM 保护、不可逆向、需版权方授权"结论，不要继续探测许可证服务器。'
    })
}
elseif ($sampAes.Count -gt 0) {
    $decrypt.Scheme = 'SAMPLE-AES'
    $decrypt.Possible = $false
    $decrypt.Reason = 'SAMPLE-AES 只加密部分 NAL / 音频帧，ffmpeg 无法直接 -c copy 还原，需按样本特点定制解封装。'
    [void]$diagnosis.Add([pscustomobject]@{
        Code = 'SAMPLE_AES'
        Level = 'P1'
        Detail = $decrypt.Reason
        Advice = '先确认是否同时在 key 上有 DRM KEYFORMAT；纯 SAMPLE-AES(AES-128 密钥) 可用 mp4decrypt/shaka 处理。'
    })
}
elseif ($targetMedia -and @($targetMedia.Keys | Where-Object { $_.Method -eq 'AES-128' }).Count -gt 0) {
    $decrypt.Scheme = 'AES-128'
    $denied = @($keyProbes | Where-Object { $_.Verdict -eq 'KEY_DENIED' })
    if ($denied.Count -gt 0) {
        $decrypt.Possible = $false
        $decrypt.Reason = 'AES-128 加密，但 key URI 在带头情况下仍被拒绝 → 需要登录态或一次性 token。'
    }
    else {
        $decrypt.Possible = $true
        $decrypt.Reason = 'AES-128 加密，key 可获取（ffmpeg -headers 可直接解密），取证闭环可做。'
    }
}
elseif ($targetMedia) {
    $decrypt.Scheme = 'CLEAR'
    $decrypt.Possible = $true
    $decrypt.Reason = '未加密（METHOD=NONE 或无 EXT-X-KEY），可直接取流。'
}

# 播放列表失效
if ($targetMedia -and $targetMedia.Segments.Count -eq 0 -and $looksLikeHls) {
    [void]$diagnosis.Add([pscustomobject]@{
        Code   = 'NO_SEGMENTS'
        Level  = 'P1'
        Detail = 'playlist 里没有任何分片（可能是 live 未开始的空窗口，或 EXT-X-ENDLIST 已过期）。'
        Advice = '确认是否 live 流；点播流出现空分片通常意味着源已下架。'
    })
}

# ------------------------------------------------------------------ ffmpeg 实解验证
$verify = [pscustomobject]@{
    Attempted = $false
    Ok        = $false
    Seconds   = 0
    File      = ''
    Ffprobe   = ''
    Error     = ''
    Skipped   = ''
}

$ffmpeg = Resolve-WebTool -Name 'ffmpeg'
$ffprobe = Resolve-WebTool -Name 'ffprobe'

if ($NoVerify) { $verify.Skipped = 'NoVerify' }
elseif (-not $decrypt.Possible) { $verify.Skipped = "解密不可行（$($decrypt.Scheme)）" }
elseif (-not $ffmpeg) { $verify.Skipped = 'ffmpeg 未安装（先跑 install-web-toolbox.ps1）' }
elseif ([string]::IsNullOrWhiteSpace($targetUri)) { $verify.Skipped = '无可用目标 URI（本地 playlist 且未给 BaseUrl）' }
else {
    $verify.Attempted = $true
    $outFile = Join-Path $OutDir 'probe.ts'
    $hdrString = ConvertTo-HeaderString -Headers $headers

    $args = @('-hide_banner', '-nostdin', '-loglevel', 'error', '-y')
    if ($hdrString) { $args += @('-headers', $hdrString) }
    # 关键：ffmpeg 的 -headers 不会稳定下传到 HLS 子资源（分片/key），
    # UA 必须用独立 -user_agent 选项，否则防盗链站点会在分片上 403。
    if ($headers.ContainsKey('User-Agent')) { $args += @('-user_agent', [string]$headers['User-Agent']) }
    if ($headers.ContainsKey('Referer')) { $args += @('-referer', [string]$headers['Referer']) }
    $args += @('-protocol_whitelist', 'file,http,https,tcp,tls,crypto')
    $args += @('-i', $targetUri, '-t', [string]$VerifySeconds, '-c', 'copy', '-f', 'mpegts', $outFile)

    $log = (Invoke-WebNative -Exe $ffmpeg -Arguments $args -Quiet) -join "`n"
    if ((Test-Path $outFile) -and (Get-Item $outFile).Length -gt 1024) {
        $verify.Ok = $true
        $verify.File = $outFile
        $verify.Seconds = [math]::Round((Get-Item $outFile).Length / 1MB, 2)
        if ($ffprobe) {
            $probeArgs = @('-hide_banner', '-v', 'error', '-show_entries', 'stream=index,codec_name,codec_type,width,height,bit_rate', '-show_entries', 'format=duration,bit_rate,format_name', '-of', 'json', $outFile)
            $verify.Ffprobe = (Invoke-WebNative -Exe $ffprobe -Arguments $probeArgs -Quiet) -join "`n"
        }
    }
    else {
        $verify.Ok = $false
        $verify.Error = if ($log) { $log } else { 'ffmpeg 未产生输出（无错误信息）' }
        [void]$diagnosis.Add([pscustomobject]@{
            Code   = 'DECRYPT_FAILED'
            Level  = 'P0'
            Detail = '按判定应该可解，但 ffmpeg 实解失败。'
            Advice = '常见原因：key 有一次性有效期（拉详情与拉分片的 token 不同域）、分片需单独 Referer、或 base64 变体 key。看 probe 日志首行。'
        })
    }
}

# ------------------------------------------------------------------ 结论
$verdictText = ''
$verdictLevel = ''
if (-not $looksLikeHls) {
    $verdictText = '⚪ 目标不是有效 m3u8 —— 404 / 被拦截 / 返了登录页'
    $verdictLevel = 'INVALID'
}
elseif ($drmKinds.Count -gt 0) {
    $verdictText = '🔴 DRM 保护 —— 取证终止（写"不可逆向，需版权方授权"）'
    $verdictLevel = 'STOP'
}
elseif ($decrypt.Scheme -eq 'SAMPLE-AES') {
    $verdictText = '🟠 SAMPLE-AES —— 需专用解封装，不能直接 -c copy'
    $verdictLevel = 'P1'
}
elseif ($verify.Ok) {
    $verdictText = '🟢 可取证闭环 —— playlist 可解、分片可播（物证 probe.ts）'
    $verdictLevel = 'OK'
}
elseif ($decrypt.Possible -and -not $verify.Attempted) {
    $verdictText = '🟡 静态判定可解（已跳过实解验证）—— 去掉 -NoVerify 出物证'
    $verdictLevel = 'P1'
}
elseif ($decrypt.Possible -and $verify.Attempted) {
    $verdictText = '🟡 逻辑可解但实解失败 —— 查 token 有效期 / 分片级头'
    $verdictLevel = 'P1'
}
elseif (-not $decrypt.Possible) {
    $verdictText = '🟠 key 受鉴权保护 —— 需登录态或一次性 token'
    $verdictLevel = 'P1'
}
else {
    $verdictText = '⚪ 未完成判定 —— 检查输入与网络'
    $verdictLevel = 'UNKNOWN'
}

# ------------------------------------------------------------------ 输出
$evidence = [pscustomobject]@{
    Schema     = 'seep.hls.evidence/1'
    GeneratedAt = (Get-Date).ToString('s')
    Input      = [pscustomobject]@{
        Url      = $Url
        Playlist = $Playlist
        Variant  = $Variant
        Headers  = ($headers.Keys | ForEach-Object { $_ })
    }
    Fetch      = [pscustomobject]@{
        Status      = $fetchInfo.Status
        Length      = $fetchInfo.Length
        ContentType = $fetchInfo.ContentType
        Msn         = $fetchInfo.Msn
        IsPlaylist  = $looksLikeHls
        Error       = $fetchInfo.Error
        Head        = if ($fetchInfo.Body) { $fetchInfo.Body.Substring(0, [Math]::Min(400, $fetchInfo.Body.Length)) } else { '' }
    }
    Variants   = $variants
    Chosen     = $targetUri
    Media      = if ($targetMedia) {
        [pscustomobject]@{
            Version        = $targetMedia.Version
            TargetDuration = $targetMedia.TargetDuration
            MediaSequence  = $targetMedia.MediaSequence
            SegmentCount   = $targetMedia.Segments.Count
            TotalDuration  = $targetMedia.TotalDuration
            Discontinuities = $targetMedia.Discontinuities
            EndList        = $targetMedia.EndList
            FirstSegments  = @($targetMedia.Segments | Select-Object -First 3)
            Keys           = $targetMedia.Keys
            Maps           = $targetMedia.Maps
            SegmentPattern = $segPattern
            SegmentHosts   = $segHosts
            TokenParams    = $tokenParams
        }
    } else { $null }
    KeyProbes  = $keyProbes
    Decrypt    = $decrypt
    Verify     = $verify
    Diagnosis  = $diagnosis
    Verdict    = [pscustomobject]@{ Level = $verdictLevel; Text = $verdictText }
    OutDir     = $OutDir
}

$jsonPath = Join-Path $OutDir 'evidence.json'
$evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

# markdown 报告
$md = New-Object System.Collections.ArrayList
[void]$md.Add("# HLS 取证报告")
[void]$md.Add('')
[void]$md.Add("- 生成时间: $($evidence.GeneratedAt)")
[void]$md.Add("- 目标: ``$(if ($Url) { $Url } else { $Playlist })``")
[void]$md.Add("- 结论: **$verdictText**")
[void]$md.Add('')
[void]$md.Add('## 1. 播放列表')
[void]$md.Add('')
[void]$md.Add('| 项 | 值 |')
[void]$md.Add('| :--- | :--- |')
[void]$md.Add("| HTTP 状态 | $($fetchInfo.Status) |")
[void]$md.Add("| 内容类型 | $($fetchInfo.ContentType) |")
[void]$md.Add("| 是否 m3u8 | $looksLikeHls |")
[void]$md.Add("| Master | $($targetMedia.IsMaster) |")
if ($targetMedia) {
    [void]$md.Add("| 分片数 | $($targetMedia.Segments.Count) |")
    [void]$md.Add("| 总时长 | $($targetMedia.TotalDuration) s |")
    [void]$md.Add("| 断点(DISCONTINUITY) | $($targetMedia.Discontinuities) |")
    [void]$md.Add("| fMP4(EXT-X-MAP) | $($targetMedia.Maps.Count -gt 0) |")
    [void]$md.Add("| 分片主机 | $($segHosts -join ', ') |")
    [void]$md.Add("| 分片 URL 特征 | ``$segPattern`` |")
    if ($tokenParams.Count -gt 0) { [void]$md.Add("| 可疑 token 参数 | $($tokenParams -join ', ') |") }
}
[void]$md.Add('')
if ($variants.Count -gt 0) {
    [void]$md.Add('### 变体')
    [void]$md.Add('')
    [void]$md.Add('| # | 码率 | 分辨率 | 编码 | URI |')
    [void]$md.Add('| ---: | ---: | :--- | :--- | :--- |')
    $i = 0
    foreach ($v in $variants) {
        [void]$md.Add("| $i | $($v.Bandwidth) | $($v.Resolution) | $($v.Codecs) | ``$($v.Uri)`` |")
        $i++
    }
    [void]$md.Add('')
}
[void]$md.Add('## 2. 加密与密钥')
[void]$md.Add('')
[void]$md.Add("| 项 | 值 |")
[void]$md.Add('| :--- | :--- |')
[void]$md.Add("| 加密方案 | $($decrypt.Scheme) |")
[void]$md.Add("| DRM | $(if ($drmKinds.Count) { $drmKinds -join ', ' } else { '—' }) |")
[void]$md.Add("| 可解密 | $($decrypt.Possible) |")
[void]$md.Add("| 判定依据 | $($decrypt.Reason) |")
[void]$md.Add('')
if ($keyProbes.Count -gt 0) {
    [void]$md.Add('### key URI 鉴权探测')
    [void]$md.Add('')
    [void]$md.Add('| 判定 | 带头 | 去头 | 说明 | URI |')
    [void]$md.Add('| :--- | ---: | ---: | :--- | :--- |')
    foreach ($k in $keyProbes) {
        [void]$md.Add("| $($k.Verdict) | $($k.WithHeadersStatus)/$($k.WithHeadersLength)B | $($k.BareStatus) | $($k.Note) $($k.HeaderDelta) | ``$($k.Uri)`` |")
    }
    [void]$md.Add('')
}
[void]$md.Add('## 3. 实解验证')
[void]$md.Add('')
if ($verify.Skipped) {
    [void]$md.Add("- 跳过: $($verify.Skipped)")
}
else {
    [void]$md.Add("| 项 | 值 |")
    [void]$md.Add('| :--- | :--- |')
    [void]$md.Add("| 成功 | $($verify.Ok) |")
    [void]$md.Add("| 产物 | ``$($verify.File)`` |")
    [void]$md.Add("| 大小 | $($verify.Seconds) MB |")
    if ($verify.Error) { [void]$md.Add("| 错误 | ``$($verify.Error -replace "`n", ' ')`` |") }
}
[void]$md.Add('')
[void]$md.Add('## 4. 诊断')
[void]$md.Add('')
if ($diagnosis.Count -eq 0) { [void]$md.Add('- 无异常') }
else {
    foreach ($d in $diagnosis) {
        [void]$md.Add("**[${($d.Level)}] $($d.Code)** — $($d.Detail)")
        [void]$md.Add('')
        [void]$md.Add("> 处置: $($d.Advice)")
        [void]$md.Add('')
    }
}
$mdPath = Join-Path $OutDir 'report.md'
$md -join "`n" | Set-Content -LiteralPath $mdPath -Encoding UTF8

if ($Json) {
    $evidence | ConvertTo-Json -Depth 8
    return
}

# 控制台看板
Write-Host ''
Write-Host "== 结论 == $verdictText" -ForegroundColor $(if ($verdictLevel -eq 'OK') { 'Green' } elseif ($verdictLevel -eq 'STOP') { 'Red' } else { 'Yellow' })
Write-Host ''
if ($targetMedia) {
    Write-Host ("  分片    : {0} 个 / {1} s / 断点 {2} / fMP4 {3}" -f $targetMedia.Segments.Count, $targetMedia.TotalDuration, $targetMedia.Discontinuities, ($targetMedia.Maps.Count -gt 0)) -ForegroundColor Gray
    Write-Host ("  主机    : {0}" -f ($segHosts -join ', ')) -ForegroundColor Gray
}
Write-Host ("  加密    : {0}   DRM: {1}   可解: {2}" -f $decrypt.Scheme, ($drmKinds -join ','), $decrypt.Possible) -ForegroundColor Gray
if ($tokenParams.Count -gt 0) { Write-Host ("  token   : {0}" -f ($tokenParams -join ', ')) -ForegroundColor DarkYellow }
if ($keyProbes.Count -gt 0) {
    Write-Host ''
    Write-Host '  key 探测:' -ForegroundColor White
    foreach ($k in $keyProbes) {
        $c = if ($k.Verdict -eq 'KEY_OK') { 'Green' } elseif ($k.Verdict -eq 'KEY_DENIED') { 'Red' } else { 'Yellow' }
        Write-Host ("    [{0,-12}] {1}" -f $k.Verdict, $k.Uri) -ForegroundColor $c
        if ($k.Note) { Write-Host ("                   $($k.Note)") -ForegroundColor DarkGray }
        if ($k.HeaderDelta) { Write-Host ("                   $($k.HeaderDelta)") -ForegroundColor DarkGray }
    }
}
if ($verify.Attempted) {
    if ($verify.Ok) { Write-Host "`n  实解    : ✅ $($verify.File) ($($verify.Seconds) MB)" -ForegroundColor Green }
    else { Write-Host "`n  实解    : ❌ $($verify.Error -replace "`n", ' ')" -ForegroundColor Red }
}
elseif ($verify.Skipped) {
    Write-Host "`n  实解    : 跳过（$($verify.Skipped)）" -ForegroundColor DarkGray
}
if ($diagnosis.Count -gt 0) {
    Write-Host ''
    Write-Host '  诊断:' -ForegroundColor White
    foreach ($d in $diagnosis) {
        $c = if ($d.Level -eq 'STOP') { 'Red' } elseif ($d.Level -eq 'P0') { 'Yellow' } else { 'DarkYellow' }
        Write-Host ("    [$($d.Level)] $($d.Code): $($d.Detail)") -ForegroundColor $c
        Write-Host ("           → $($d.Advice)") -ForegroundColor DarkGray
    }
}
Write-Host ''
Write-Host "  证据    : $jsonPath" -ForegroundColor Cyan
Write-Host "  报告    : $mdPath" -ForegroundColor Cyan

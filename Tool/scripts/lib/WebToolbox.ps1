# WebToolbox.ps1 - Web / 流媒体外部工具箱统一解析层（ffmpeg / ffprobe / node / jadx）
#
# 设计目标与 AndroidToolbox.ps1 一致：仓库只装"图纸"，上 GB 的运行时放到本机工具箱，
# 通过统一解析层指向它，任何一台机器路径不同也能自动探测到。
#
# 探测优先级：
#   1. 环境变量 SEEP_WEB_TOOLBOX 指定的根目录
#   2. 默认根目录 D:\Tool\Web      （Windows，本项目约定安装位）
#   3. 系统 PATH 中的可执行文件     （Linux / macOS / 换机器的场景）
#
# 工具箱标准布局（由 Tool/scripts/web/install-web-toolbox.ps1 建立）：
#   <root>\bin\               垫片目录（ffmpeg.cmd / ffprobe.cmd，建议加入 PATH）
#   <root>\ffmpeg\bin\        ffmpeg.exe + ffprobe.exe（官方 builds 解压）
#   <root>\work\              HLS 取证 / 重放举证的工作目录（默认输出根）

function Get-WebToolboxRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:SEEP_WEB_TOOLBOX)) {
        return $env:SEEP_WEB_TOOLBOX
    }
    return 'D:\Tool\Web'
}

function Get-WebToolboxBinDir {
    return (Join-Path (Get-WebToolboxRoot) 'bin')
}

function Get-WebWorkRoot {
    $root = Get-WebToolboxRoot
    return (Join-Path $root 'work')
}

<#
.SYNOPSIS
    解析 Web 工具箱中某个工具的可执行路径。
.DESCRIPTION
    依次查找：<root>\bin\<name>.cmd → <root>\ffmpeg\bin\<name>.exe →
    <root>\<name>.exe → 系统 PATH。找不到返回 $null（不抛异常）。
#>
function Resolve-WebTool {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $root = Get-WebToolboxRoot
    # 顺序很重要：优先真实 .exe，最后才用 .cmd 垫片。
    # .cmd 垫片通过 %* 传参，无法携带含 CRLF 的多行参数（ffmpeg -headers 就是这种），
    # 在命令行里由 .cmd 中转会触发 "Trailing option(s) found in the command" 而失败。
    $candidates = @(
        (Join-Path $root "ffmpeg\bin\$Name.exe"),
        (Join-Path $root "bin\$Name.exe"),
        (Join-Path $root "bin\$Name.cmd"),
        (Join-Path $root "$Name\bin\$Name.exe"),
        (Join-Path $root "$Name.exe")
    )

    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }

    $onPath = Get-Command $Name -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    return $null
}

function Test-WebTool {
    param([Parameter(Mandatory = $true)][string]$Name)
    return ($null -ne (Resolve-WebTool -Name $Name))
}

<#
.SYNOPSIS
    以“干净文本”方式调用外部工具，stderr 与 stdout 合并为字符串输出。
#>
function Invoke-WebNative {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @(),
        [switch]$Quiet
    )

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $line = if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $msg = ''
                try { $msg = $_.Exception.Message } catch { $msg = '' }
                if ($msg) { $msg } else { '' }
            }
            else { "$_" }
            if ([string]::IsNullOrWhiteSpace($line)) { return }
            if (-not $Quiet) { Write-Host "  $line" } else { $line }
        }
    }
    finally { $ErrorActionPreference = $prevEap }
}

<#
.SYNOPSIS
    带自定义请求头发起一次 HTTP 请求，返回结构化结果（永不抛异常，失败也返回对象）。
.DESCRIPTION
    这是 fetch / 防盗链举证 / key 鉴权探测的公共底座。
    返回字段：Ok / Status / StatusText / Length / ContentType / Body / Headers / Error / Msn
    - Msn: 毫秒耗时
    - Body: 前 2MB（Get-WebResponseText 取全文另存）
#>
function Invoke-WebFetch {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [hashtable]$Headers = @{},
        [string]$Method = 'GET',
        [string]$Body,
        [string]$ContentType,
        [int]$TimeoutSec = 30,
        [int]$MaxBodyBytes = 2097152,
        [switch]$NoRedirect,
        [switch]$Insecure,
        [string]$Cookie
    )

    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls } catch { }

    $h = @{}
    foreach ($k in $Headers.Keys) {
        if (-not [string]::IsNullOrWhiteSpace($Headers[$k])) { $h[$k] = [string]$Headers[$k] }
    }
    if (-not [string]::IsNullOrWhiteSpace($Cookie) -and -not $h.ContainsKey('Cookie')) {
        $h['Cookie'] = $Cookie
    }

    $params = @{
        Uri                = $Url
        Method             = $Method
        Headers            = $h
        TimeoutSec         = $TimeoutSec
        UseBasicParsing    = $true
        MaximumRedirection = if ($NoRedirect) { 0 } else { 5 }
    }
    if (-not [string]::IsNullOrWhiteSpace($Body)) {
        $params['Body'] = $Body
        if ([string]::IsNullOrWhiteSpace($ContentType)) { $params['ContentType'] = 'application/json' }
        else { $params['ContentType'] = $ContentType }
    }

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $resp = $null
    $errorText = ''
    try {
        $resp = Invoke-WebRequest @params
    }
    catch {
        $errorText = $_.Exception.Message
        if ($_.Exception.Response -ne $null) { $resp = $_.Exception.Response }
    }
    $sw.Stop()

    if ($null -eq $resp) {
        return [pscustomobject]@{
            Ok          = $false
            Status      = 0
            StatusText  = 'ERROR'
            Length      = 0
            ContentType = ''
            Body        = ''
            Headers     = @{}
            Error       = $errorText
            Msn         = [int]$sw.ElapsedMilliseconds
        }
    }

    $status = 0
    $statusText = ''
    $ct = ''
    $len = 0
    $text = ''
    $respHeaders = @{}

    if ($resp -is [Microsoft.PowerShell.Commands.WebResponseObject]) {
        $status = [int]$resp.StatusCode
        $statusText = [string]$resp.StatusCode
        $ct = [string]$resp.Headers['Content-Type']
        $len = [int64]$resp.RawContentLength
        if ($null -ne $resp.Content -and $resp.Content -is [byte[]]) {
            $take = [Math]::Min($resp.Content.Length, $MaxBodyBytes)
            $text = [Text.Encoding]::UTF8.GetString($resp.Content, 0, $take)
        }
        else { $text = [string]$resp.Content }
        foreach ($k in $resp.Headers.Keys) { $respHeaders[[string]$k] = [string]$resp.Headers[$k] }
    }
    else {
        # 非 2xx 走异常分支时拿到的是 HttpWebResponse
        $status = [int]$resp.StatusCode
        $statusText = [string]$resp.StatusDescription
        $ct = [string]$resp.ContentType
        foreach ($k in $resp.Headers.AllKeys) { $respHeaders[$k] = [string]$resp.Headers[$k] }
        try {
            $stream = $resp.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $text = $reader.ReadToEnd()
            $reader.Close()
            $len = $text.Length
        }
        catch { }
        if ([string]::IsNullOrWhiteSpace($errorText)) { $errorText = "HTTP $status" }
    }

    return [pscustomobject]@{
        Ok          = ($status -ge 200 -and $status -lt 400)
        Status      = $status
        StatusText  = $statusText
        Length      = $len
        ContentType = $ct
        Body        = if ($null -eq $text) { '' } else { $text }
        Headers     = $respHeaders
        Error       = $errorText
        Msn         = [int]$sw.ElapsedMilliseconds
    }
}

<#
.SYNOPSIS
    把 "K: V" 或 "K=V" 形式的字符串数组解析成请求头哈希表。
#>
function ConvertTo-WebHeaderTable {
    param(
        [string[]]$HeaderLines = @(),
        [string]$HeaderJson,
        [string]$Curl
    )

    $h = @{}

    if (-not [string]::IsNullOrWhiteSpace($HeaderJson)) {
        try {
            $obj = $HeaderJson | ConvertFrom-Json
            foreach ($p in $obj.PSObject.Properties) { $h[$p.Name] = [string]$p.Value }
        }
        catch { Write-Warning "HeaderJson 解析失败: $($_.Exception.Message)" }
    }

    foreach ($line in $HeaderLines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -match '^\s*([^:=]+?)\s*[:=]\s*(.*)$') {
            $h[$Matches[1]] = $Matches[2]
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($Curl)) {
        foreach ($m in [regex]::Matches($Curl, "-H\s+'([^:]+):\s*([^']*)'")) {
            $h[$m.Groups[1].Value.Trim()] = $m.Groups[2].Value.Trim()
        }
        foreach ($m in [regex]::Matches($Curl, '-H\s+"([^:]+):\s*([^"]*)"')) {
            $h[$m.Groups[1].Value.Trim()] = $m.Groups[2].Value.Trim()
        }
        foreach ($m in [regex]::Matches($Curl, "--header\s+([^:]+):\s*(\S+)")) {
            $h[$m.Groups[1].Value.Trim()] = $m.Groups[2].Value.Trim()
        }
    }

    return $h
}

<#
.SYNOPSIS
    从 curl 命令串里抽出目标 URL。
#>
function Get-WebUrlFromCurl {
    param([Parameter(Mandatory = $true)][string]$Curl)

    foreach ($m in [regex]::Matches($Curl, "curl\s+(?:[^'""\s]+\s+)*['""](https?://[^'""]+)['""]")) {
        return $m.Groups[1].Value
    }
    foreach ($m in [regex]::Matches($Curl, '(https?://[^\s''"]+)')) {
        return $m.Groups[1].Value
    }
    return ''
}

<#
.SYNOPSIS
    输出 Web 工具箱就绪看板（供 verify / recon 复用）。
#>
function Get-WebToolboxStatus {
    $root = Get-WebToolboxRoot
    $tools = [ordered]@{
        'ffmpeg'  = 'HLS/TS 解密与转封装（-headers 原生处理 AES-128）'
        'ffprobe' = '流格式与编码探测（验证"能否播"）'
        'node'    = 'JS 本地复现 / 沙盒执行（配合 js-reverse 取证）'
    }

    $rows = foreach ($k in $tools.Keys) {
        $p = Resolve-WebTool -Name $k
        [pscustomobject]@{
            Tool    = $k
            Ready   = [bool]$p
            Path    = if ($p) { $p } else { '—' }
            Purpose = $tools[$k]
        }
    }

    return [pscustomobject]@{
        Root   = $root
        Tools  = $rows
        WorkDir = (Get-WebWorkRoot)
    }
}

#Requires -Version 5.1
<#
  spider-extract.ps1 —— TVBox / CatVod spider 三入口提取器（Seep Web 工具箱 P1 能力）
  ----------------------------------------------------------------
  背景：
    TVBox / CatVod / 影视源聚合器的"源"就是一个 jar（spider.jar），
    入口固定为 com.github.catvod.crawler.Spider 的三/四个方法：
        homeContent(cfg)        → 首页分类与推荐
        categoryContent(...)    → 分类分页列表
        detailContent(ids)      → 详情（真正下发播放地址的地方）
        playerContent(flag,id,vipFlags) → 播放解析（取流逻辑）
    找到 detailContent / playerContent 就等于找到了取流链路。

  本脚本做的事：
    jadx 反编译 → 定位入口方法 → 抽取硬编码域名 / 接口路径 / 凭据 / 请求头 / 加密调用 → 出报告

  用法：
    powershell -File Tool\scripts\web\spider-extract.ps1 -Path .\spider.jar
    powershell -File Tool\scripts\web\spider-extract.ps1 -Path .\spider.jar -OutDir D:\work\spider1
    powershell -File Tool\scripts\web\spider-extract.ps1 -Path .\app.apk -SkipDecompile   # 复用已有反编译产物

  产出：
    <OutDir>\src\             jadx 反编译结果（.java）
    <OutDir>\evidence.json    机器可读
    <OutDir>\report.md        人可读（含入口定位与可疑项）
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$OutDir = '',
    [switch]$SkipDecompile,
    [int]$MaxSnippets = 3,
    [switch]$Json,
    [int]$TimeoutSec = 600
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LibDir = Join-Path (Split-Path -Parent $ScriptDir) 'lib'
. (Join-Path $LibDir 'WebToolbox.ps1')
. (Join-Path $LibDir 'ToolDiscovery.ps1')

if (-not (Test-Path -LiteralPath $Path)) { throw "目标不存在: $Path" }
$target = (Resolve-Path -LiteralPath $Path).Path
$baseName = [IO.Path]::GetFileNameWithoutExtension($target)

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutDir = Join-Path (Get-WebWorkRoot) "spider-$baseName-$stamp"
}
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
$srcDir = Join-Path $OutDir 'src'

if (-not $Json) {
    Write-Host ''
    Write-Host '== TVBox / CatVod spider 提取 ==' -ForegroundColor White
    Write-Host "  目标 : $target" -ForegroundColor DarkGray
    Write-Host "  产出 : $OutDir" -ForegroundColor DarkGray
}

# ------------------------------------------------------------------ 反编译
$jadxInfo = $null
if (-not $SkipDecompile) {
    $spec = $null
    try { $spec = Resolve-ReverseToolSpec -Name 'jadx' } catch { }
    if (-not $spec -or -not $spec.Available) {
        throw '未找到 jadx。请确认工作台内置工具存在（Tool/mcp/Tool/safe/jadx）或已执行 setup/repair-tools.ps1 -Only jadx'
    }
    $jadx = $spec.Command
    $jadxInfo = $spec

    if (-not $Json) { Write-Host "  反编译: $jadx" -ForegroundColor DarkGray }
    if (-not (Test-Path -LiteralPath $srcDir)) {
        $args = @('-d', $srcDir, '--no-res', '--show-bad-code', $target)
        $log = (Invoke-WebNative -Exe $jadx -Arguments $args -Quiet) -join "`n"
        if (-not (Test-Path -LiteralPath $srcDir)) {
            # 加了 --no-res 之后，如果包里本来就没有 DEX（资源包、测试样本、纯 so 包），
            # jadx 会正常退出但不创建输出目录。这不是坏掉，别报成「反编译失败」。
            if ($log -match 'No classes') {
                Write-Warning 'jadx 报告「没有可反编译的 class」，继续走资源/字符串线索'
                New-Item -ItemType Directory -Path $srcDir -Force | Out-Null
            } else {
                throw "jadx 反编译失败（未生成输出目录）。日志尾部：`n$($log.Substring([Math]::Max(0, $log.Length - 1200)))"
            }
        }
    }
}
elseif (-not (Test-Path -LiteralPath $srcDir)) {
    throw "指定了 -SkipDecompile，但 $srcDir 不存在"
}

# ------------------------------------------------------------------ 扫描
$javaFiles = @(Get-ChildItem -LiteralPath $srcDir -Recurse -File -Include *.java, *.kt -ErrorAction SilentlyContinue)
if ($javaFiles.Count -eq 0) { throw "反编译目录里没有源码文件: $srcDir" }
if (-not $Json) { Write-Host "  源码   : $($javaFiles.Count) 个文件" -ForegroundColor DarkGray }

function Find-InSources {
    param(
        [string]$Pattern,
        [int]$Limit = 20,
        [switch]$IgnoreCase
    )
    $hits = New-Object System.Collections.Generic.List[object]
    $opts = if ($IgnoreCase) { [Text.RegularExpressions.RegexOptions]::IgnoreCase } else { [Text.RegularExpressions.RegexOptions]::None }
    $rx = New-Object System.Text.RegularExpressions.Regex($Pattern, $opts)
    foreach ($f in $javaFiles) {
        if ($hits.Count -ge $Limit) { break }
        $text = $null
        try { $text = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 } catch { continue }
        if ([string]::IsNullOrWhiteSpace($text)) { continue }
        $rel = $f.FullName.Substring($srcDir.Length).TrimStart('\', '/')
        # 关键：一个文件里可能有多个匹配（多个域名/多个密钥），必须遍历所有 Match
        foreach ($m in $rx.Matches($text)) {
            if ($hits.Count -ge $Limit) { break }
            $hits.Add([pscustomobject]@{
                File  = $rel
                Match = $m.Value.Trim()
                Line  = (($text.Substring(0, $m.Index) -split "`n").Count)
            })
        }
    }
    return $hits.ToArray()
}

function Get-Unique {
    param($Items, [string]$Prop = 'Match')
    if (-not $Items) { return @() }
    return @($Items | ForEach-Object { $_.$Prop } | Sort-Object -Unique)
}

# 三/四入口
$entryPatterns = @{
    'homeContent'     = 'homeContent\s*\('
    'categoryContent' = 'categoryContent\s*\('
    'detailContent'   = 'detailContent\s*\('
    'playerContent'   = 'playerContent\s*\('
    'searchContent'   = 'searchContent\s*\('
    'homeVideoContent' = 'homeVideoContent\s*\('
}

$entries = New-Object System.Collections.Generic.List[object]
foreach ($k in $entryPatterns.Keys) {
    $hits = @(Find-InSources -Pattern $entryPatterns[$k] -Limit 6)
    $entries.Add([pscustomobject]@{
        Entry = $k
        Found = ($hits.Count -gt 0)
        Files = (Get-Unique -Items $hits -Prop 'File')
    })
}

# Spider 基类
$baseSpider = @(Find-InSources -Pattern 'extends\s+(com\.github\.catvod\.crawler\.)?Spider' -Limit 10)

# 域名 / URL
$urls = @(Find-InSources -Pattern 'https?://[A-Za-z0-9\.\-:]+[^\s"''\)\\]*' -Limit 200 -IgnoreCase)
$domains = @($urls | ForEach-Object {
    try { ([Uri]$_.Match).Host } catch { '' }
} | Where-Object { $_ } | Sort-Object -Unique)

# 接口路径（含字符串里的 /api 路径与 ?ac= 这类采集参数）
$paths = @(Find-InSources -Pattern '(?i)("[^"]*?/(api|vod|json|php)[^"]*"|[?&]ac=(list|videolist|detail)|/[A-Za-z0-9_\-]+\?[A-Za-z0-9_\-]+=)' -Limit 80)

# 凭据 / 密钥
$secrets = @(Find-InSources -Pattern '(?i)(api[_-]?key|secret|token|appid|appkey|access[_-]?key|password|passwd)\s*[=:]\s*"[^"]{4,}"' -Limit 40)

# 请求头（影视源大概率要伪造 Referer/UA）
$headerSets = @(Find-InSources -Pattern '(?i)\.put\(\s*"(Referer|User-Agent|Origin|Cookie|X-[A-Za-z\-]+)"\s*,\s*"[^"]*"' -Limit 40)

# 加密 / 编码调用
$cryptoCalls = @(Find-InSources -Pattern '(Base64\.decode|Base64\.encode|Cipher\.getInstance|MessageDigest\.getInstance|AES/|DES/)' -Limit 40)
$cryptoKinds = @($cryptoCalls | ForEach-Object {
    if ($_.Match -match 'Base64') { 'Base64' }
    elseif ($_.Match -match 'MessageDigest') { 'MessageDigest(摘要)' }
    elseif ($_.Match -match 'Cipher') { 'Cipher(对称加密)' }
    else { $_.Match }
} | Sort-Object -Unique)

# 混淆特征（单字母类名占比）
$shortNames = @($javaFiles | Where-Object { $_.BaseName -match '^[a-zA-Z]{1,2}$' }).Count
$obfRatio = if ($javaFiles.Count -gt 0) { [math]::Round(100.0 * $shortNames / $javaFiles.Count, 1) } else { 0 }

# ------------------------------------------------------------------ 结论
$foundEntries = @($entries | Where-Object { $_.Found } | ForEach-Object { $_.Entry })
$missingEntries = @($entries | Where-Object { -not $_.Found } | ForEach-Object { $_.Entry })

$verdict = ''
$level = ''
if ($foundEntries.Count -eq 0) {
    $verdict = '🔴 未定位到任何 Spider 入口 —— 可能不是 CatVod spider，或方法被字符串反射调用'
    $level = 'FAIL'
}
elseif ($foundEntries -contains 'detailContent' -and $foundEntries -contains 'playerContent') {
    $verdict = "🟢 已定位取流链路：$($foundEntries -join ' / ')"
    $level = 'OK'
}
else {
    $verdict = "🟡 部分入口命中：$($foundEntries -join ' / ')（缺 $($missingEntries -join ', ')）"
    $level = 'P1'
}

$risk = New-Object System.Collections.Generic.List[string]
if ($secrets.Count -gt 0) { [void]$risk.Add("硬编码凭据 $($secrets.Count) 处（源码里直接可见，属 CWE-798）") }
if ($headerSets.Count -gt 0) { [void]$risk.Add("代码内硬编码请求头 $($headerSets.Count) 处（防盗链绕过逻辑所在）") }
if ($cryptoCalls.Count -gt 0) { [void]$risk.Add("加密/编码调用：$($cryptoKinds -join ', ')（可能有字符串保护，需跟进）") }
if ($obfRatio -ge 30) { [void]$risk.Add("混淆程度较高（单字母类名占比 $obfRatio%），疑似 ProGuard/Allatori") }
if ($domains.Count -gt 6) { [void]$risk.Add("硬编码域名 $($domains.Count) 个，源站可能多套切换") }

# ------------------------------------------------------------------ 输出
$evidence = [pscustomobject]@{
    Schema      = 'seep.spider.extract/1'
    GeneratedAt = (Get-Date).ToString('s')
    Target      = $target
    Jadx        = if ($jadxInfo) { $jadxInfo.Command } else { 'skipped' }
    SourceFiles = $javaFiles.Count
    Entries     = $entries
    BaseSpider  = $baseSpider
    Domains     = $domains
    Urls        = @($urls | Select-Object -First 40)
    ApiPaths    = @($paths | Select-Object -First 40)
    Secrets     = @($secrets | Select-Object -First $MaxSnippets)
    HeaderSets  = @($headerSets | Select-Object -First 20)
    CryptoKinds = $cryptoKinds
    Obfuscation = [pscustomobject]@{ ShortClassNames = $shortNames; Ratio = $obfRatio }
    Verdict     = [pscustomobject]@{ Level = $level; Text = $verdict; Risks = $risk.ToArray() }
    OutDir      = $OutDir
}

$jsonPath = Join-Path $OutDir 'evidence.json'
$evidence | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$md = New-Object System.Collections.Generic.List[string]
[void]$md.Add('# Spider 提取报告')
[void]$md.Add('')
[void]$md.Add("- 目标: ``$([IO.Path]::GetFileName($target))``")
[void]$md.Add("- 源码文件: $($javaFiles.Count)")
[void]$md.Add("- 结论: **$verdict**")
[void]$md.Add('')
[void]$md.Add('## 1. 入口定位')
[void]$md.Add('')
[void]$md.Add('| 入口 | 命中 | 文件 |')
[void]$md.Add('| :--- | :---: | :--- |')
foreach ($e in $entries) {
    $mark = if ($e.Found) { '✅' } else { '—' }
    [void]$md.Add("| ``$($e.Entry)`` | $mark | $($e.Files -join '<br>') |")
}
[void]$md.Add('')
if ($domains.Count -gt 0) {
    [void]$md.Add('## 2. 硬编码域名')
    [void]$md.Add('')
    foreach ($d in $domains) { [void]$md.Add("- ``$d``") }
    [void]$md.Add('')
}
if ($paths.Count -gt 0) {
    [void]$md.Add('## 3. 接口路径')
    [void]$md.Add('')
    foreach ($p in ($paths | Select-Object -First 30)) {
        [void]$md.Add("- ``$($p.Match)``  ← ``$($p.File):$($p.Line)``")
    }
    [void]$md.Add('')
}
if ($secrets.Count -gt 0) {
    [void]$md.Add('## 4. 硬编码凭据（CWE-798）')
    [void]$md.Add('')
    [void]$md.Add('| 文件:行 | 片段 |')
    [void]$md.Add('| :--- | :--- |')
    foreach ($s in ($secrets | Select-Object -First $MaxSnippets)) {
        $snip = ($s.Match -replace '\|', '\|')
        [void]$md.Add("| ``$($s.File):$($s.Line)`` | ``$snip`` |")
    }
    [void]$md.Add('')
}
if ($headerSets.Count -gt 0) {
    [void]$md.Add('## 5. 代码内硬编码请求头（防盗链绕过点）')
    [void]$md.Add('')
    foreach ($h in ($headerSets | Select-Object -First 15)) {
        [void]$md.Add("- ``$($h.Match)``  ← ``$($h.File):$($h.Line)``")
    }
    [void]$md.Add('')
}
[void]$md.Add('## 6. 风险与后续')
[void]$md.Add('')
if ($risk.Count -eq 0) { [void]$md.Add('- 无异常见项') }
else { foreach ($r in $risk) { [void]$md.Add("- $r") } }
[void]$md.Add('')
$mdPath = Join-Path $OutDir 'report.md'
$md -join "`n" | Set-Content -LiteralPath $mdPath -Encoding UTF8

if ($Json) {
    $evidence | ConvertTo-Json -Depth 6
    return
}

Write-Host ''
foreach ($e in $entries) {
    $c = if ($e.Found) { 'Green' } else { 'DarkGray' }
    $mark = if ($e.Found) { '✅' } else { '— ' }
    Write-Host ("  {0} {1,-18} {2}" -f $mark, $e.Entry, (($e.Files | Select-Object -First 2) -join ', ')) -ForegroundColor $c
}
Write-Host ''
Write-Host "  域名   : $(if ($domains.Count) { $domains -join ', ' } else { '（无）' })" -ForegroundColor Gray
Write-Host "  接口   : $($paths.Count) 条    凭据: $($secrets.Count) 处    硬编码头: $($headerSets.Count) 处" -ForegroundColor Gray
Write-Host "  混淆   : 单字母类名 $shortNames / $($javaFiles.Count) = $obfRatio%" -ForegroundColor Gray
if ($cryptoKinds.Count -gt 0) { Write-Host "  加密   : $($cryptoKinds -join ', ')" -ForegroundColor DarkYellow }
Write-Host ''
Write-Host "== 结论 == $verdict" -ForegroundColor $(if ($level -eq 'OK') { 'Green' } elseif ($level -eq 'FAIL') { 'Red' } else { 'Yellow' })
foreach ($r in $risk) { Write-Host "  · $r" -ForegroundColor DarkYellow }
Write-Host ''
Write-Host "  证据 : $jsonPath" -ForegroundColor Cyan
Write-Host "  报告 : $mdPath" -ForegroundColor Cyan

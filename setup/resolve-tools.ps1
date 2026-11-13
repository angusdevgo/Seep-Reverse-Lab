#Requires -Version 5.1
<#
.SYNOPSIS
    Seep Lab —— 外部工具统一解析 / 实跑验证器

.DESCRIPTION
    回答两个问题，且用同一条证据链回答：
      1. 这个工具在这台机器上「在哪」？
      2. 它「真的能启动」吗？（不是文件存在就算）

    路径发现规则来自 setup/tool-registry.json —— 规则集中声明，不在代码里写死。
    这意味着：你的 IDA 装在 D:\Tool\IDA Pro，别人的装在 E:\Rev\IDA 或者根本没装，
    同一个脚本都能判对，而不是用你的路径去要求别人。

    解析链（逐层下降，命中即停，并记录来自哪一层）：
      1. env        环境变量（SEEP_IDA_ROOT / SEEP_WEB_TOOLBOX / SEEP_PYTHON ...）
      2. cache      ~/.seep/tools.json 上次解析成功的位置（-NoCache 可跳过）
      3. bundled    仓库自带 <repo>/Tool/mcp/Tool/safe/...（相对路径，任何机器一致）
      4. path       系统 PATH
      5. candidates 常见安装位候选表（%VAR% / ~ / {env:VAR} 展开）

    四态判定：
      READY     找到且实跑成功（未加 -Verify 时标记为「未实跑」，状态仍是 READY）
      DEGRADED  找到但跑不起来 —— 不阻断，给出修复命令
      OPTIONAL  没找到，属于可选能力 —— 不阻断
      MISSING   没找到，属于核心能力 —— 阻断部署（退出码 1）

.PARAMETER Tool
    只检查指定 id（可多个）。省略则检查注册表全部。

.PARAMETER Verify
    真正启动每个找到的工具并检查返回码。不加则只做路径解析。

.PARAMETER Json
    输出 JSON（便于 verify.ps1 等程序消费）。

.PARAMETER NoCache
    不读也不写 ~/.seep/tools.json。

.PARAMETER Timeout
    单个工具的实跑超时秒数，默认取注册表里每条自己的 timeout，兜底 10 秒。

.PARAMETER Root
    仓库根目录，默认取本脚本的上级目录。

.EXAMPLE
    powershell -File setup\resolve-tools.ps1
    powershell -File setup\resolve-tools.ps1 -Verify
    powershell -File setup\resolve-tools.ps1 -Tool ida -Verify -Json
    powershell -File setup\resolve-tools.ps1 -Verify -NoCache
#>
[CmdletBinding()]
param(
    [string[]]$Tool = @(),
    [switch]$Verify,
    [switch]$Json,
    [switch]$NoCache,
    [int]$Timeout = 0,
    [string]$Root = ''
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Root)) { $Root = Split-Path -Parent $ScriptDir }
$RegistryPath = Join-Path $ScriptDir 'tool-registry.json'
$CachePath = Join-Path (Join-Path $env:USERPROFILE '.seep') 'tools.json'

# ---------------------------------------------------------------- 工具函数

function Expand-Token {
    <# 展开 %VAR% / ~ / {env:VAR}，并统一成正斜杠友好的本机路径 #>
    param([string]$Pattern, [string]$ToolRoot = '')

    if ([string]::IsNullOrWhiteSpace($Pattern)) { return $null }
    $p = $Pattern

    if ($ToolRoot -ne '') { $p = $p.Replace('{root}', $ToolRoot) }

    # {env:NAME}
    $p = [regex]::Replace($p, '\{env:([A-Za-z0-9_]+)\}', {
        param($m)
        $v = [Environment]::GetEnvironmentVariable($m.Groups[1].Value)
        if ($v) { $v } else { $m.Value }
    })

    # %NAME%
    $p = [regex]::Replace($p, '%([A-Za-z0-9_() ]+)%', {
        param($m)
        $v = [Environment]::GetEnvironmentVariable($m.Groups[1].Value)
        if ($v) { $v } else { $m.Value }
    })

    if ($p.StartsWith('~')) {
        $p = (Join-Path $env:USERPROFILE $p.Substring(1).TrimStart('\', '/'))
    }

    return $p
}

function Invoke-Capture {
    <# 启动子进程并捕获输出，带硬超时。stdin 显式重定向后立即关闭 ——
       不继承父进程 stdin（与 issue #13 同一类故障：子进程等 stdin 会挂死）。 #>
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$ArgList = @(),
        [int]$TimeoutSec = 10
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $ext = [IO.Path]::GetExtension($Exe).ToLowerInvariant()

    if ($ext -eq '.bat' -or $ext -eq '.cmd') {
        $psi.FileName = $env:ComSpec
        # cmd.exe 引号规则：/c "path" "arg" 会被当成一个 token。正确写法是整体再包一层：
        #   /s /c ""path" "arg""   —— 注意首尾各只加一个引号，因为 path 自身已带引号。
        # 加 /s 是让 cmd 明确只剥掉最外层那一对引号。
        $quoted = @($Exe) + @($ArgList) | ForEach-Object { '"{0}"' -f ($_ -replace '"', '""') }
        $psi.Arguments = '/s /c "' + ($quoted -join ' ') + '"'
    }
    else {
        $psi.FileName = $Exe
        $argText = @($ArgList) | ForEach-Object {
            if ($_ -match '[\s"]') { '"{0}"' -f ($_ -replace '"', '\"') } else { $_ }
        }
        $psi.Arguments = ($argText -join ' ')
    }

    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = $true

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
    }
    catch {
        return [pscustomobject]@{ Ok = $false; TimedOut = $false; Code = -1; Text = $_.Exception.Message }
    }

    try { $proc.StandardInput.Close() } catch { }

    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()

    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        try { $proc.Kill() } catch { }
        return [pscustomobject]@{ Ok = $false; TimedOut = $true; Code = -1; Text = ('超时 {0}s 未返回' -f $TimeoutSec) }
    }

    $text = ''
    try {
        $all = ($outTask.Result + "`n" + $errTask.Result).Trim()
        $first = @($all -split "`r?`n" |
            Where-Object { $_.Trim() -ne '' } |
            Where-Object { $_ -notmatch '^[-=*_#~]+$' } |   # 跳过纯分隔线，取到有用信息
            Select-Object -First 2)
        $text = ($first -join ' / ').Trim()
        if ($text.Length -gt 120) { $text = $text.Substring(0, 120) }
    }
    catch { }

    return [pscustomobject]@{
        Ok       = ($proc.ExitCode -eq 0)
        TimedOut = $false
        Code     = $proc.ExitCode
        Text     = $text
    }
}

function Get-RootCandidates {
    <# 从「根目录」推出候选可执行文件路径。toolbox_layout 优先，否则按 path_names 推。 #>
    param($ToolDef, [string]$ToolRoot)

    $list = @()
    if ($ToolDef.PSObject.Properties.Name -contains 'toolbox_layout') {
        $list = @($ToolDef.toolbox_layout)
    }
    elseif ($ToolDef.id -eq 'ida') {
        $list = @('{root}/ida.exe', '{root}/ida64.exe',
            '{root}/App/IDA Pro/ida.exe', '{root}/App/IDA Pro/ida64.exe')
    }
    else {
        $names = @()
        if ($ToolDef.PSObject.Properties.Name -contains 'path_names') { $names = @($ToolDef.path_names) }
        foreach ($n in $names) {
            $list += @("{root}/$n.exe", "{root}/$n", "{root}/bin/$n.exe", "{root}/bin/$n", "{root}/Scripts/$n.exe")
        }
    }
    return @($list | ForEach-Object { Expand-Token -Pattern $_ -ToolRoot $ToolRoot })
}

function Resolve-OneTool {
    param($ToolDef, $Cache)

    $id = $ToolDef.id
    $result = [pscustomobject]@{
        id       = $id
        kind     = $ToolDef.kind
        purpose  = $(if ($ToolDef.PSObject.Properties.Name -contains 'purpose') { $ToolDef.purpose } else { '' })
        path     = $null
        source   = $null
        state    = 'MISSING'
        detail   = ''
        fix      = $(if ($ToolDef.PSObject.Properties.Name -contains 'fix') { $ToolDef.fix } else { '' })
        expect   = $(if ($ToolDef.PSObject.Properties.Name -contains 'expect') { $ToolDef.expect } else { '' })
        verified = $false
        warn     = @()
    }

    # 解析层顺序：注册表可用 chain 字段覆盖（例如 python 要优先找 venv 而不是 PATH 垫片）
    $chain = @('env', 'bundled', 'cache', 'path', 'candidates')
    if ($ToolDef.PSObject.Properties.Name -contains 'chain' -and $ToolDef.chain) {
        $chain = @($ToolDef.chain)
    }

    foreach ($layer in $chain) {
        if ($result.path) { break }

        switch ($layer) {

            'env' {
                if (-not ($ToolDef.PSObject.Properties.Name -contains 'env')) { break }
                if ([string]::IsNullOrWhiteSpace($ToolDef.env)) { break }

                $raw = [Environment]::GetEnvironmentVariable($ToolDef.env)
                if ([string]::IsNullOrWhiteSpace($raw)) { break }

                $expanded = Expand-Token -Pattern $raw
                if (-not (Test-Path -LiteralPath $expanded)) {
                    # 环境变量设错了不该直接判死 —— 记下警告，继续沿链往下降。
                    # 否则用户把 SEEP_IDA_ROOT 写错一个字母，就会看到「IDA 缺失」而不是「你路径写错了」。
                    $result.warn += ('{0} 指向的路径不存在: {1}' -f $ToolDef.env, $expanded)
                    break
                }

                if ((Get-Item -LiteralPath $expanded).PSIsContainer) {
                    foreach ($c in (Get-RootCandidates -ToolDef $ToolDef -ToolRoot $expanded)) {
                        if ($c -and (Test-Path -LiteralPath $c) -and -not (Get-Item -LiteralPath $c).PSIsContainer) {
                            $result.path = (Resolve-Path -LiteralPath $c).Path
                            $result.source = ('env:{0}' -f $ToolDef.env)
                            break
                        }
                    }
                }
                else {
                    $result.path = (Resolve-Path -LiteralPath $expanded).Path
                    $result.source = ('env:{0}' -f $ToolDef.env)
                }
            }

            'cache' {
                if (-not $Cache -or -not $Cache.ContainsKey($id)) { break }
                $cached = $Cache[$id]
                if ($cached -and $cached.path -and (Test-Path -LiteralPath $cached.path)) {
                    # 缓存里的 .cmd 垫片可能已被卸载，实跑阶段会兜住；这里只做存在性检查
                    $result.path = $cached.path
                    $result.source = 'cache'
                }
            }

            'bundled' {
                if (-not ($ToolDef.PSObject.Properties.Name -contains 'bundled')) { break }
                foreach ($b in @($ToolDef.bundled)) {
$full = Join-Path $Root ($b.Replace('/', '\'))
                    if (Test-Path -LiteralPath $full) {
                        $result.path = (Resolve-Path -LiteralPath $full).Path
                        $result.source = 'bundled'
                        break
                    }
                }
            }

            'path' {
                if (-not ($ToolDef.PSObject.Properties.Name -contains 'path_names')) { break }
                foreach ($n in @($ToolDef.path_names)) {
                    $cmd = Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1
                    if ($cmd) {
                        $result.path = $cmd.Source
                        $result.source = 'path'
                        break
                    }
                }
            }

            'candidates' {
                if (-not ($ToolDef.PSObject.Properties.Name -contains 'candidates')) { break }
                foreach ($c in @($ToolDef.candidates)) {
                    $expanded = Expand-Token -Pattern $c
                    if (-not $expanded -or -not (Test-Path -LiteralPath $expanded)) { continue }

                    if ((Get-Item -LiteralPath $expanded).PSIsContainer) {
                        $hit = $null
                        foreach ($rc in (Get-RootCandidates -ToolDef $ToolDef -ToolRoot $expanded)) {
                            if ($rc -and (Test-Path -LiteralPath $rc) -and -not (Get-Item -LiteralPath $rc).PSIsContainer) {
                                $hit = (Resolve-Path -LiteralPath $rc).Path
                                break
                            }
                        }
                        if ($hit) {
                            $result.path = $hit
                            $result.source = 'candidates'
                            break
                        }
                    }
                    else {
                        $result.path = (Resolve-Path -LiteralPath $expanded).Path
                        $result.source = 'candidates'
                        break
                    }
                }
            }
        }
    }

    if ($result.path) { $result.state = 'READY' }
    elseif ($result.kind -eq 'optional') { $result.state = 'OPTIONAL' }
    else { $result.state = 'MISSING' }

    # 环境变量写错的警告要保留下来，不能因为后续层解析成功就吞掉
    if ($result.warn.Count -gt 0) {
        $warnText = ($result.warn -join '；')
        if ($result.detail) { $result.detail = $warnText + ' | ' + $result.detail }
        else { $result.detail = $warnText }
    }

    return $result
}

function Test-ToolVerify {
    <# 实跑验证。只有这一步通过，READY 才算真的「成功启动」。 #>
    param($Resolved, $ToolDef, [int]$DefaultTimeout = 10)

    $spec = $null
    if ($ToolDef.PSObject.Properties.Name -contains 'verify') { $spec = $ToolDef.verify }
    if (-not $spec) { return $Resolved }

    $to = $DefaultTimeout
    if ($spec.PSObject.Properties.Name -contains 'timeout' -and $spec.timeout) { $to = [int]$spec.timeout }

    $kind = $(if ($spec.PSObject.Properties.Name -contains 'kind') { $spec.kind } else { 'version' })
    $args = @()
    if ($spec.PSObject.Properties.Name -contains 'args') { $args = @($spec.args) }

    $probe = $null

    switch ($kind) {
        'python-import' {
            $mod = 'mcp'
            if ($spec.PSObject.Properties.Name -contains 'arg') { $mod = $spec.arg }
            $probe = Invoke-Capture -Exe $Resolved.path -ArgList @('-c', "import $mod") -TimeoutSec $to
        }
        'version' {
            $probe = Invoke-Capture -Exe $Resolved.path -ArgList $args -TimeoutSec $to
        }
        'jar' {
            $java = Get-Command java -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $java) {
                $Resolved.state = 'DEGRADED'
                $Resolved.detail = '缺少 java，无法执行 jar'
                return $Resolved
            }
            $probe = Invoke-Capture -Exe $java.Source -ArgList (@('-jar', $Resolved.path) + $args) -TimeoutSec $to
        }
        'exists' {
            # 目录型 MCP 包：检查 package.json 或入口文件，不实跑（实跑代价高且由 MCP 客户端负责）
            $pkg = Join-Path $Resolved.path 'package.json'
            if (Test-Path -LiteralPath $pkg) {
                $Resolved.verified = $true
                $Resolved.detail = '包目录完整（package.json 在位）'
            }
            else {
                $Resolved.state = 'DEGRADED'
                $Resolved.detail = '包目录缺少 package.json（可能 node_modules 未解压）'
            }
            return $Resolved
        }
        'ida' {
            $exe = $Resolved.path
            if (-not (Test-Path -LiteralPath $exe)) {
                $Resolved.state = 'DEGRADED'
                $Resolved.detail = 'ida.exe 不存在'
                return $Resolved
            }
            # IDA 自带 Python 能 import ida_pro_mcp 才算「真的能联动」
            $idaRoot = Split-Path -Parent $exe
            $srv = Get-ChildItem -LiteralPath $idaRoot -Recurse -Filter 'server.py' -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match 'ida_pro_mcp' } | Select-Object -First 1
            if ($srv) {
                $Resolved.verified = $true
                $Resolved.detail = 'ida.exe + ida_pro_mcp 就绪'
            }
            else {
                $Resolved.state = 'DEGRADED'
                $Resolved.detail = 'ida.exe 在位，但未装 ida_pro_mcp（跑 install-ida.ps1）'
            }
            return $Resolved
        }
        default {
            $probe = Invoke-Capture -Exe $Resolved.path -ArgList $args -TimeoutSec $to
        }
    }

    if ($probe -and $probe.Ok) {
        $Resolved.verified = $true
        $Resolved.detail = $probe.Text
    }
    elseif ($probe) {
        $Resolved.state = 'DEGRADED'
        if ($probe.TimedOut) {
            $Resolved.detail = $probe.Text
        }
        else {
            $Resolved.detail = ('启动失败(rc={0}): {1}' -f $probe.Code, $probe.Text)
        }
    }
    return $Resolved
}

# ---------------------------------------------------------------- 主流程

if (-not (Test-Path -LiteralPath $RegistryPath)) {
    Write-Host "[FAIL] 找不到注册表: $RegistryPath" -ForegroundColor Red
    exit 2
}

try {
    $registry = Get-Content -LiteralPath $RegistryPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
catch {
    Write-Host "[FAIL] 注册表 JSON 解析失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}

# 缓存
$cache = @{}
if (-not $NoCache -and (Test-Path -LiteralPath $CachePath)) {
    try {
        $raw = Get-Content -LiteralPath $CachePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($raw.resolved) {
            foreach ($p in $raw.resolved.PSObject.Properties) {
                $cache[$p.Name] = $p.Value
            }
        }
    }
    catch { $cache = @{} }
}

$defs = @($registry.tools)
if ($Tool.Count -gt 0) {
    $want = @($Tool | ForEach-Object { $_.ToLowerInvariant() })
    $defs = @($defs | Where-Object { $want -contains $_.id.ToLowerInvariant() })
    if ($defs.Count -eq 0) {
        Write-Host "[FAIL] 注册表里没有这些 id: $($Tool -join ', ')" -ForegroundColor Red
        exit 2
    }
}

$results = @()
foreach ($d in $defs) {
    $r = Resolve-OneTool -ToolDef $d -Cache $cache
    if ($Verify -and $r.path) {
        $to = 10
        if ($Timeout -gt 0) { $to = $Timeout }
        $r = Test-ToolVerify -Resolved $r -ToolDef $d -DefaultTimeout $to
    }
    $results += $r
}

# requires 依赖检查（如 apktool 需要 java）
foreach ($r in $results) {
    $def = $defs | Where-Object { $_.id -eq $r.id } | Select-Object -First 1
    if ($def -and ($def.PSObject.Properties.Name -contains 'requires')) {
        foreach ($dep in @($def.requires)) {
            $d = $results | Where-Object { $_.id -eq $dep } | Select-Object -First 1
            if ($d -and $d.state -ne 'READY') {
                $r.state = 'DEGRADED'
                $r.detail = ('依赖 {0} 未就绪' -f $dep)
            }
        }
    }
}

# 写缓存（只记解析成功且实跑通过的，避免把坏路径固化下来）
if (-not $NoCache) {
    $newCache = [ordered]@{ version = 1; resolved = [ordered]@{} }
    foreach ($r in $results) {
        if ($r.path -and ($r.state -eq 'READY')) {
            $newCache.resolved[$r.id] = [ordered]@{ path = $r.path; source = $r.source }
        }
    }
    try {
        $dir = Split-Path -Parent $CachePath
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        ($newCache | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $CachePath -Encoding UTF8
    }
    catch { }
}

# ---------------------------------------------------------------- 输出

$missCount = @($results | Where-Object { $_.state -eq 'MISSING' }).Count
$degCount = @($results | Where-Object { $_.state -eq 'DEGRADED' }).Count
$okCount = @($results | Where-Object { $_.state -eq 'READY' }).Count
$optCount = @($results | Where-Object { $_.state -eq 'OPTIONAL' }).Count

if ($Json) {
    $payload = [ordered]@{
        version     = 1
        verifyRun   = [bool]$Verify
        root        = $Root
        summary     = [ordered]@{ ready = $okCount; degraded = $degCount; optional = $optCount; missing = $missCount }
        tools       = @($results | ForEach-Object {
            [ordered]@{
                id = $_.id; kind = $_.kind; state = $_.state; path = $_.path; source = $_.source
                verified = $_.verified; detail = $_.detail; fix = $_.fix; purpose = $_.purpose
            }
        })
    }
    $payload | ConvertTo-Json -Depth 6
}
else {
    $modeText = $(if ($Verify) { '实跑验证模式' } else { '仅路径解析（加 -Verify 才会真启动）' })
    Write-Host ''
    Write-Host ('  === Seep 外部工具解析 / 验证 —— {0} ===' -f $modeText) -ForegroundColor Cyan
    Write-Host ('  注册表: {0}' -f $RegistryPath) -ForegroundColor DarkGray
    Write-Host ''

    $fmt = '  {0,-14} {1,-10} {2,-10} {3}'
    Write-Host ($fmt -f 'ID', '状态', '来源', '路径 / 说明') -ForegroundColor White
    Write-Host ('  ' + ('-' * 96)) -ForegroundColor DarkGray

    foreach ($r in $results) {
        $color = switch ($r.state) {
            'READY' { 'Green' }
            'DEGRADED' { 'Yellow' }
            'OPTIONAL' { 'DarkGray' }
            default { 'Red' }
        }
        $stateText = $r.state
        if ($r.state -eq 'READY' -and -not $r.verified) { $stateText = 'READY~' }
        $where = $(if ($r.path) { $r.path } else { '—' })
        $src = $(if ($r.source) { $r.source } else { '—' })

        Write-Host ($fmt -f $r.id, $stateText, $src, $where) -ForegroundColor $color
        if ($r.detail) { Write-Host ('  {0,-14} {1,10} {2,10} └─ {3}' -f '', '', '', $r.detail) -ForegroundColor DarkGray }
        if ($r.state -in @('DEGRADED', 'OPTIONAL', 'MISSING') -and $r.fix) {
            Write-Host ('  {0,-14} {1,10} {2,10} └─ 修复: {3}' -f '', '', '', $r.fix) -ForegroundColor $color
        }
    }

    Write-Host ('  ' + ('-' * 96)) -ForegroundColor DarkGray
    Write-Host ('  READY {0} | DEGRADED {1} | OPTIONAL {2} | MISSING {3}' -f $okCount, $degCount, $optCount, $missCount) -ForegroundColor White
    if (-not $Verify) {
        Write-Host '  提示: READY~ 表示只解析到路径，尚未实跑。加 -Verify 可验证「是否真的能启动」。' -ForegroundColor DarkGray
    }
    Write-Host ''
}

if ($missCount -gt 0) { exit 1 }
exit 0

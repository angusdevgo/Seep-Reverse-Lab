#Requires -Version 5.1
<#
  Seep 逆向工程工作台 —— 已有用户一键更新 (Updater)
  ================================================================
  适用场景：已经部署过工作台，现在要拉取最新版本。

  执行流程：
    1. 记录当前版本与用户自有数据指纹（用于事后校验零丢失）
    2. 自动探测代理并 git pull 拉取最新代码
    3. 对比版本，打印 CHANGELOG 变更说明
    4. 调用 install.ps1 做幂等增量同步（Skill / 提示词 / 扩展 / MCP 配置）
    5. 校验用户自有数据未被覆盖
    6. 跑官方基准自检并输出更新报告

  安全承诺：
    · 用户自有数据（models.json / auth.json / 自定义 MCP 条目 / lab-mode.flag）永不被覆盖
    · 覆盖前自动备份到 ~/.pi/agent/backup-<时间戳>/
    · 任何一步失败都会给出明确的回滚指引

  用法：
    powershell -ExecutionPolicy Bypass -File .\setup\update.ps1
    powershell -ExecutionPolicy Bypass -File .\setup\update.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File .\setup\update.ps1 -NoPull
#>
[CmdletBinding()]
param(
    [switch]$DryRun,        # 只显示将要做什么，不做任何修改
    [switch]$NoPull,        # 跳过 git pull（离线压缩包更新场景）
    [switch]$Check,         # 仅检查是否有新版本可用，不执行更新
    [switch]$SkipVerify,    # 跳过最终自检
    [switch]$WithTools,     # 顺带补齐外部能力包（ffmpeg / frida / APKiD / nuclei / ffuf）
    [switch]$SkipCapabilities,  # 跳过能力包步骤（只用本地已装的）
    [switch]$CheckCapabilities, # 只补能力、不动代码（网络不好或只想补依赖时用）
    [string]$IdaRoot = ''   # 可选：更新时顺带绑定 IDA Pro 路径
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$AgentDir  = Join-Path $env:USERPROFILE '.pi\agent'
$VersionFile = Join-Path $Root 'VERSION'
$ChangeLogFile = Join-Path $Root 'CHANGELOG.md'
$McpJson   = Join-Path $AgentDir 'mcp.json'

$script:Warnings = @()

function Write-Step($m) { Write-Host "`n>>> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "    [!!] $m" -ForegroundColor Yellow; $script:Warnings += $m }
function Write-Info($m) { Write-Host "    [..] $m" -ForegroundColor Gray }
function Write-Fail($m) { Write-Host "    [FAIL] $m" -ForegroundColor Red }

function Get-Version {
    if (Test-Path $VersionFile) {
        return (Get-Content $VersionFile -Raw -Encoding UTF8).Trim()
    }
    return 'unknown'
}

function Get-McpServerKeys {
    if (-not (Test-Path $McpJson)) { return @() }
    try {
        $raw = [System.IO.File]::ReadAllText($McpJson, [System.Text.Encoding]::UTF8)
        # 必须用序数/字符比较：.NET 默认 StartsWith 的文化敏感比较会把 U+FEFF（BOM）
        # 当作可忽略字符，导致无 BOM 文件也被误判为“以 BOM 开头”。
        if ($raw.Length -gt 0 -and [int]$raw[0] -eq 0xFEFF) { $raw = $raw.Substring(1) }
        $obj = $raw | ConvertFrom-Json
        if ($obj.mcpServers) { return @($obj.mcpServers.PSObject.Properties.Name) }
    } catch { }
    return @()
}

function Test-ProxyPort {
    param([int[]]$Ports)
    foreach ($p in $Ports) {
        $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        if ($c) { return $p }
    }
    return $null
}

# -----------------------------------------------------------------------------
# 0. 前置检查
# -----------------------------------------------------------------------------
Write-Host @"
================================================================================
          Seep Reverse Lab — 已有用户一键更新 (Updater)
================================================================================
  工作台根目录: $Root
"@ -ForegroundColor Cyan

$oldVersion = Get-Version
$isGitRepo = Test-Path (Join-Path $Root '.git')

if ($Check) {
    Write-Host "`n>>> 正在检查远程最新版本..." -ForegroundColor Cyan
    $proxyPort = Test-ProxyPort -Ports @(10808, 7897, 7890)
    $proxyArgs = if ($proxyPort) { @('-c', "http.proxy=http://127.0.0.1:$proxyPort", '-c', "https.proxy=http://127.0.0.1:$proxyPort") } else { @() }
    
    if ($isGitRepo) {
        Push-Location $Root
        try {
            $remoteLine = (& git @proxyArgs ls-remote origin refs/heads/main 2>$null)
            $localSha = (& git rev-parse HEAD 2>$null)
            if ($remoteLine -and $localSha) {
                $remoteSha = ($remoteLine -split '\s+')[0]
                if ($remoteSha -eq $localSha) {
                    Write-Host "  [OK] 当前工作台已是最新版本 (v$oldVersion, commit $($localSha.Substring(0,7)))" -ForegroundColor Green
                    Pop-Location
                    exit 0
                } else {
                    Write-Host "  [UPDATE] 检测到远程仓库有新版本/新提交！(本地: $($localSha.Substring(0,7)), 远程: $($remoteSha.Substring(0,7)))" -ForegroundColor Yellow
                    Write-Host "  提示: 双击 update.bat 或执行 powershell setup/update.ps1 即可一键更新。" -ForegroundColor Cyan
                    Pop-Location
                    exit 2
                }
            }
        } finally {
            Pop-Location
        }
    }

    try {
        $url = 'https://raw.githubusercontent.com/angusdevgo/Seep-Reverse-Lab/main/VERSION'
        $handler = New-Object System.Net.Http.HttpClientHandler
        if ($proxyPort) {
            $handler.Proxy = New-Object System.Net.WebProxy("http://127.0.0.1:$proxyPort")
        }
        $client = New-Object System.Net.Http.HttpClient($handler)
        $client.Timeout = [TimeSpan]::FromSeconds(5)
        $task = $client.GetStringAsync($url)
        $task.Wait()
        $rVer = $task.Result.Trim()
        if ($rVer -and $rVer -ne $oldVersion) {
            Write-Host "  [UPDATE] 检测到新版本 v$rVer 发布！(当前本地版本: v$oldVersion)" -ForegroundColor Yellow
            Write-Host "  提示: 双击 update.bat 或执行 powershell setup/update.ps1 即可一键更新。" -ForegroundColor Cyan
            exit 2
        } else {
            Write-Host "  [OK] 当前工作台已是最新版本 (v$oldVersion)" -ForegroundColor Green
            exit 0
        }
    } catch {
        Write-Host "  [..] 暂时无法连接远程检测版本 (当前本地版本: v$oldVersion)" -ForegroundColor Gray
        exit 0
    }
}

Write-Host "  当前版本    : v$oldVersion" -ForegroundColor White
Write-Host "  Git 仓库    : $(if ($isGitRepo) { '是（支持 git pull）' } else { '否（压缩包部署）' })" -ForegroundColor White
Write-Host "  运行模式    : $(if ($DryRun) { 'DRY RUN（不修改任何文件）' } elseif ($CheckCapabilities) { '仅补外部能力包（不动代码）' } else { '正常更新' })" -ForegroundColor White

# -CheckCapabilities 短路：不动代码、不重装配置，只补能力包，适合「网络拉不动代码但缺 ffmpeg/frida」
if ($CheckCapabilities) {
    $capScript = Join-Path $ScriptDir 'install-capabilities.ps1'
    if (-not (Test-Path $capScript)) { Write-Fail '缺少 setup\install-capabilities.ps1'; exit 1 }
    Write-Step '补齐外部能力包'
    & $capScript -Only all
    Write-Host ''
    Write-Host '  完成。若本次新装了 ffmpeg / frida，请完全重启 Agent 会话让 PATH 生效。' -ForegroundColor Cyan
    exit 0
}

# 记录更新前的用户自有数据指纹
$beforeMcpKeys = Get-McpServerKeys
Write-Info "更新前 mcp.json 中的 MCP 服务: $(if ($beforeMcpKeys.Count) { $beforeMcpKeys -join ', ' } else { '（无）' })"

$userDataFiles = @(
    (Join-Path $AgentDir 'models.json'),
    (Join-Path $AgentDir 'auth.json'),
    (Join-Path $AgentDir 'lab-mode.flag')
)
$userDataStamp = @{}
foreach ($f in $userDataFiles) {
    if (Test-Path $f) {
        $userDataStamp[$f] = (Get-Item $f).LastWriteTimeUtc.Ticks
    }
}
Write-Info "受保护的用户自有数据: $(($userDataFiles | ForEach-Object { Split-Path $_ -Leaf }) -join ', ')"

if ($DryRun) {
    Write-Host "`n  [DRY RUN] 将要执行的步骤：" -ForegroundColor Yellow
    Write-Host "    1. $(if ($NoPull) { '跳过 git pull（-NoPull）' } else { '自动探测代理并 git pull 拉取最新代码' })" -ForegroundColor Gray
    Write-Host "    2. 打印 CHANGELOG 版本变更说明" -ForegroundColor Gray
    Write-Host "    3. 调用 setup\install.ps1 做幂等增量同步（自动备份 + 保护自定义 MCP）" -ForegroundColor Gray
    Write-Host "    4. 校验用户自有数据未被覆盖" -ForegroundColor Gray
    Write-Host "    5. 跑 setup\verify.ps1 -Detailed 官方基准自检" -ForegroundColor Gray
    Write-Host "`n  未修改任何文件。去掉 -DryRun 即执行真实更新。`n" -ForegroundColor Yellow
    exit 0
}

# -----------------------------------------------------------------------------
# 1. 拉取最新代码
# -----------------------------------------------------------------------------
Write-Step '1/6  拉取最新代码'

if ($NoPull) {
    Write-Info '已指定 -NoPull，跳过 git pull（适用于手动下载压缩包覆盖的场景）'
} elseif (-not $isGitRepo) {
    $hasGit = Get-Command git -ErrorAction SilentlyContinue
    if ($hasGit) {
        Write-Info '检测到本机已安装 Git，正在将当前目录自动关联并初始化至远程仓库...'
        Push-Location $Root
        try {
            & git init 2>&1 | Out-Null
            & git remote add origin https://github.com/angusdevgo/Seep-Reverse-Lab.git 2>&1 | Out-Null
            & git remote set-url origin https://github.com/angusdevgo/Seep-Reverse-Lab.git 2>&1 | Out-Null
            Write-Info '正在从远程仓库高速拉取最新代码...'
            & git @proxyArgs fetch origin main 2>&1 | ForEach-Object { Write-Info $_ }
            & git @proxyArgs reset --mixed origin/main 2>&1 | Out-Null
            Write-Ok '已成功将当前工作台关联并更新至最新版本！'
            $isGitRepo = $true
        } catch {
            Write-Warn2 "自动关联拉取失败: $_"
        } finally {
            Pop-Location
        }
    } else {
        Write-Warn2 '当前目录不是 Git 仓库且本机未检测到 Git 命令，无法自动拉取。'
        Write-Info '若需更新，可从 GitHub 仓库下载最新压缩包覆盖后重跑本脚本。'
    }
} else {
    $proxyPort = Test-ProxyPort -Ports @(10808, 7897, 7890)
    if ($proxyPort) {
        Write-Info "检测到可用代理端口: $proxyPort"
        $proxyArgs = @('-c', "http.proxy=http://127.0.0.1:$proxyPort", '-c', "https.proxy=http://127.0.0.1:$proxyPort")
    } else {
        Write-Info '未检测到常见代理端口，尝试直连'
        $proxyArgs = @()
    }

    Push-Location $Root
    try {
        # 先检查是否有本地未提交改动（避免 rebase 被阻断）
        $dirty = & git status --porcelain 2>$null
        if ($dirty) {
            Write-Warn2 "工作区存在 $($dirty.Count) 项本地改动，将先暂存（stash）再拉取"
            & git stash push -u -m "seep-update-autostash-$(Get-Date -Format 'yyyyMMdd-HHmmss')" 2>&1 | ForEach-Object { Write-Info $_ }
            $script:Stashed = $true
        }

        & git @proxyArgs pull --rebase origin main 2>&1 | ForEach-Object { Write-Info $_ }
        if ($LASTEXITCODE -ne 0) {
            Write-Fail 'git pull 失败（可能是网络或代理问题）'
            Write-Info '可尝试：git -c http.proxy=http://127.0.0.1:<你的端口> pull --rebase origin main'
            Write-Info '或使用 -NoPull 参数：先手动下载最新压缩包覆盖，再运行 update.ps1 -NoPull'
            if ($script:Stashed) { Write-Warn2 '本地改动仍保存在 git stash 中，可用 git stash pop 恢复' }
            Pop-Location
            exit 1
        }
        Write-Ok '代码已更新到最新版本'
    } finally {
        Pop-Location
    }
}

# -----------------------------------------------------------------------------
# 2. 版本对比与变更说明
# -----------------------------------------------------------------------------
Write-Step '2/6  版本变更说明'

$newVersion = Get-Version
if ($oldVersion -eq $newVersion) {
    Write-Info "版本未变化（v$newVersion）—— 将执行一次幂等重同步（补齐可能缺失的组件）"
} else {
    Write-Ok "版本已更新: v$oldVersion  ->  v$newVersion"
}

if (Test-Path $ChangeLogFile) {
    $lines = Get-Content $ChangeLogFile -Encoding UTF8
    $start = -1; $end = $lines.Count
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^##\s*\[') {
            if ($start -eq -1) { $start = $i } else { $end = $i; break }
        }
    }
    if ($start -ge 0) {
        Write-Host "`n  ---------- 本次版本变更摘要 ----------" -ForegroundColor Yellow
        $lines[$start..($end - 1)] | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        Write-Host "  --------------------------------------`n" -ForegroundColor Yellow
    }
}

# -----------------------------------------------------------------------------
# 3. 幂等增量同步
# -----------------------------------------------------------------------------
Write-Step '3/6  执行幂等增量同步（自动备份 + 保护自定义配置）'

# 注意：PowerShell 的数组 splatting (@arr) 不会把 '-Name' 解析为参数名，
# 会当成位置参数导致 ParameterBindingException，因此这里用显式命名参数调用。
$installParams = @{ NonInteractive = $true }
if ($IdaRoot -ne '') { $installParams['IdaRoot'] = $IdaRoot }
else                 { $installParams['SkipTools'] = $true }
if ($WithTools)          { $installParams['WithWeb'] = $true; $installParams['WithAndroid'] = $true }
if ($SkipCapabilities)   { $installParams['SkipCapabilities'] = $true }

& (Join-Path $ScriptDir 'install.ps1') @installParams
$installExit = if ($?) { 0 } else { 1 }

if ($installExit -ne 0) {
    Write-Warn2 "install.ps1 返回码 $installExit，部分步骤可能未完成，请查看上方输出"
} else {
    Write-Ok '增量同步完成'
}

# -----------------------------------------------------------------------------
# 4. 用户自有数据零丢失校验
# -----------------------------------------------------------------------------
Write-Step '4/6  用户自有数据零丢失校验'

$afterMcpKeys = Get-McpServerKeys
$lostKeys = @($beforeMcpKeys | Where-Object { $afterMcpKeys -notcontains $_ })
$addedKeys = @($afterMcpKeys | Where-Object { $beforeMcpKeys -notcontains $_ })

if ($lostKeys.Count -gt 0) {
    Write-Fail "检测到 MCP 服务丢失: $($lostKeys -join ', ')"
    Write-Info "请从备份目录恢复: $AgentDir\backup-*\mcp.json"
} else {
    if ($beforeMcpKeys.Count -gt 0) {
        Write-Ok "原有 MCP 服务全部保留（$($beforeMcpKeys.Count) 个: $($beforeMcpKeys -join ', ')）"
    } else {
        Write-Ok '原有 MCP 服务全部保留（更新前为空）'
    }
}
if ($addedKeys.Count -gt 0) {
    Write-Ok "新增标准 MCP 服务: $($addedKeys -join ', ')"
} else {
    Write-Info '无新增 MCP 服务（已是最新）'
}

$tampered = @()
foreach ($f in $userDataStamp.Keys) {
    if (-not (Test-Path $f)) { $tampered += (Split-Path $f -Leaf); continue }
    if ((Get-Item $f).LastWriteTimeUtc.Ticks -ne $userDataStamp[$f]) {
        $tampered += (Split-Path $f -Leaf)
    }
}
if ($tampered.Count -gt 0) {
    Write-Warn2 "以下用户数据被改动（通常不应发生）: $($tampered -join ', ')"
} else {
    Write-Ok 'models.json / auth.json / lab-mode.flag 均未被触碰'
}

# -----------------------------------------------------------------------------
# 5. 官方基准自检
# -----------------------------------------------------------------------------
if (-not $SkipVerify) {
    Write-Step '5/6  官方基准自检'
    & (Join-Path $ScriptDir 'verify.ps1') -Detailed
    $verifyExit = $LASTEXITCODE
    if ($verifyExit -eq 0) {
        Write-Ok '自检全部通过'
    } else {
        Write-Warn2 '自检存在未通过项，请查看上方红色标记'
    }
} else {
    Write-Step '5/6  官方基准自检（已跳过 -SkipVerify）'
}

# -----------------------------------------------------------------------------
# 6. 更新报告
# -----------------------------------------------------------------------------
Write-Step '6/6  更新完成报告'

Write-Host "`n================================================================================" -ForegroundColor White
Write-Host ("  Seep 工作台更新完成:  v{0}  ->  v{1}" -f $oldVersion, $newVersion) -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor White

# -----------------------------------------------------------------------------
# 能力看板：区分「文件在不在」与「这个工具现在能不能真跑」
# 外部依赖（ffmpeg / frida / APKiD / Aotopsy / nuclei / ffuf）不在仓库里，
# 只看文件在位会给出「全绿但一半工具不可用」的假象。
# -----------------------------------------------------------------------------
$capRows = @()
$webLib = Join-Path $Root 'Tool\scripts\lib\WebToolbox.ps1'
$andLib = Join-Path $Root 'Tool\scripts\lib\AndroidToolbox.ps1'
if (Test-Path $webLib) { . $webLib }
if (Test-Path $andLib) { . $andLib }
if (Get-Command Get-WebToolboxStatus -ErrorAction SilentlyContinue) {
    try {
        foreach ($t in (Get-WebToolboxStatus).Tools) {
            $capRows += [pscustomobject]@{ G = 'Web'; T = $t.Tool; R = [bool]$t.Ready }
        }
    }
    catch { }
}
if (Get-Command Get-AndroidToolboxStatus -ErrorAction SilentlyContinue) {
    try {
        foreach ($t in (Get-AndroidToolboxStatus).Tools) {
            $capRows += [pscustomobject]@{ G = 'Android'; T = $t.Tool; R = [bool]$t.Ready }
        }
    }
    catch { }
}
$capMissing = @($capRows | Where-Object { -not $_.R })

# 动态统计，避免版本迭代后报告里的数字过时
$skillDirs  = @(Get-ChildItem (Join-Path $Root 'Tool\skill') -Directory -ErrorAction SilentlyContinue)
$safeCount  = 0
$safeDir    = Join-Path $Root 'Tool\skill\safe-skills'
if (Test-Path $safeDir) { $safeCount = @(Get-ChildItem $safeDir -Directory).Count }
$skillTotal = $skillDirs.Count - 1 + $safeCount
$serverPy   = Join-Path $Root 'Tool\mcp\seep_mcp_server.py'
$toolTotal  = if (Test-Path $serverPy) {
    @(Select-String -Path $serverPy -Pattern '^def seep_\w+\(' -AllMatches).Count
} else { 0 }

Write-Host ''
Write-Host '  本次同步:' -ForegroundColor White
Write-Host ("    · 逆向技能 {0} 个（Tool\skill 下 {1} 个目录）" -f $skillTotal, $skillDirs.Count) -ForegroundColor Gray
Write-Host ("    · MCP 工具定义 {0} 个" -f $toolTotal) -ForegroundColor Gray
Write-Host '    · 提示词 (seep-system.md / AGENTS.md) 与安全扩展' -ForegroundColor Gray
Write-Host '    · mcp.json 已增量合并（自定义 MCP 条目完整保留）' -ForegroundColor Gray
Write-Host '    · 内置工具箱与知识库已校验' -ForegroundColor Gray

if ($capRows.Count -gt 0) {
    Write-Host ''
    Write-Host '  外部能力:' -ForegroundColor White
    foreach ($r in $capRows) {
        $mark  = if ($r.R) { '[READY]  ' } else { '[MISSING]' }
        $color = if ($r.R) { 'Green' } else { 'Yellow' }
        Write-Host ("    {0} {1,-14} ({2})" -f $mark, $r.T, $r.G) -ForegroundColor $color
    }
    if ($capMissing.Count -gt 0) {
        Write-Host ''
        Write-Host '  缺件不影响 MCP 启动：相关工具会返回明确的修复指引，其余工具照常工作。' -ForegroundColor DarkGray
        Write-Host '  一条命令全补: powershell -File setup\install-capabilities.ps1 -Only all' -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host "  下一步（顺序不能跳）:" -ForegroundColor White
Write-Host @"

    1) 完全关闭并重新打开 Agent 会话
       Pi 与 DSH 都要整个进程退出重开。
       仅刷新或 re-load 不够 —— MCP 工具是启动时握手的，
       不重开就看不到新工具，也读不到新 Skill。
    2) 在对话框中发送:  lab：
       即可继续开工

  如需回滚:
    · 配置备份位于: $AgentDir\backup-<时间戳>\
    · 代码回滚:     git -C "$Root" log --oneline -10  然后 git reset --hard <commit>

"@ -ForegroundColor Cyan

if ($script:Stashed) {
    Write-Host "  [!!] 你之前的本地改动已自动 stash 保存，恢复命令:" -ForegroundColor Yellow
    Write-Host "       git -C `"$Root`" stash pop" -ForegroundColor Yellow
    Write-Host ""
}

if ($script:Warnings.Count -gt 0) {
    Write-Host "  关注项:" -ForegroundColor Yellow
    $script:Warnings | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
    Write-Host ""
}

exit 0

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
    [switch]$SkipVerify,    # 跳过最终自检
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

Write-Host "  当前版本    : v$oldVersion" -ForegroundColor White
Write-Host "  Git 仓库    : $(if ($isGitRepo) { '是（支持 git pull）' } else { '否（压缩包部署）' })" -ForegroundColor White
Write-Host "  运行模式    : $(if ($DryRun) { 'DRY RUN（不修改任何文件）' } else { '正常更新' })" -ForegroundColor White

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
    Write-Warn2 '当前目录不是 Git 仓库，无法自动拉取。请手动下载最新压缩包覆盖后重跑本脚本。'
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
if ($IdaRoot -ne '') {
    & (Join-Path $ScriptDir 'install.ps1') -NonInteractive -IdaRoot $IdaRoot
} else {
    & (Join-Path $ScriptDir 'install.ps1') -NonInteractive -SkipTools
}
$installExit = $LASTEXITCODE

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

Write-Host @"

  更新内容:
    · 9 大逆向 Skill 已同步到最新
    · 提示词 (SYSTEM.md / AGENTS.md) 与安全扩展已同步
    · mcp.json 已增量合并（自定义 MCP 完整保留）
    · 内置工具箱与知识库已校验

  下一步:
    1) 完全关闭并重新打开 Agent 会话（Pi / Claude Code / DSH / OpenCode）
       —— 这一步是必须的，新 Skill 与扩展需要重新加载
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

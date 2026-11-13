#Requires -Version 5.1
<#
  Seep 逆向工程工作台 —— 一键卸载 (Uninstaller)
  ================================================================
  设计原则：**只移除工作台自己装的东西，绝不碰你的数据。**

  卸载范围（精准白名单，逐项可关）：
    · ~/.pi/agent/skills/<工作台技能>      —— 仅工作台自带的 9 大技能
    · ~/.pi/agent/AGENTS.md / SYSTEM.md    —— 工作台写入的提示词
    · ~/.pi/agent/extensions/*.ts          —— 工作台扩展
    · ~/.pi/agent/mcp.json 中的 seep / js-reverse / playwright 条目
    · ~/.pi/agent/settings.json 中工作台加入的 packages
    · ~/.pi/agent/lab-mode.flag            —— 实验环境标志

  严格保护（永不删除）：
    · models.json / auth.json / sessions/ / logs/
    · 你自己添加的 Skill、MCP 条目、settings.json 字段
    · 你自己的 backup-* 备份目录（除非显式 -Purge）

  安全机制：
    · 默认交互确认；-Yes 跳过
    · 删除前把受影响文件整体备份到 ~/.pi/agent/backup-uninstall-<时间戳>/
    · -DryRun 只预览，不做任何修改
    · -Restore <备份目录> 反向恢复

  用法：
    powershell -ExecutionPolicy Bypass -File .\setup\uninstall.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File .\setup\uninstall.ps1
    powershell -ExecutionPolicy Bypass -File .\setup\uninstall.ps1 -Yes -KeepSkills
    powershell -ExecutionPolicy Bypass -File .\setup\uninstall.ps1 -Restore "$env:USERPROFILE\.pi\agent\backup-uninstall-20261011-120000"
#>
[CmdletBinding()]
param(
    [switch]$DryRun,          # 只显示将要做什么，不做任何修改
    [switch]$Yes,             # 跳过交互确认
    [switch]$KeepSkills,      # 保留已安装的技能
    [switch]$KeepPrompts,     # 保留 AGENTS.md / SYSTEM.md / extensions
    [switch]$KeepMcp,         # 保留 mcp.json 中的工作台条目
    [switch]$KeepPackages,    # 保留 settings.json 中工作台加入的 packages
    [switch]$KeepLabFlag,     # 保留 lab-mode.flag
    [switch]$Purge,           # 同时清理 backup-* 备份目录与生成的配置
    [string]$Restore = ''     # 从指定备份目录恢复，而非卸载
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$AgentDir  = Join-Path $env:USERPROFILE '.pi\agent'
$SkillsDir = Join-Path $AgentDir 'skills'
$ExtDir    = Join-Path $AgentDir 'extensions'
$McpJson   = Join-Path $AgentDir 'mcp.json'
$SetJson   = Join-Path $AgentDir 'settings.json'
$LabFlag   = Join-Path $AgentDir 'lab-mode.flag'

$script:Removed = 0
$script:Kept    = 0
$script:Failed  = 0

function Write-Step($m)  { Write-Host "`n>>> $m" -ForegroundColor Cyan }
function Write-Ok($m)    { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "    [!!] $m" -ForegroundColor Yellow }
function Write-Info($m)  { Write-Host "    [..] $m" -ForegroundColor Gray }
function Write-Fail($m)  { Write-Host "    [FAIL] $m" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# 读取 JSON（序数比较剥 BOM，避免 .NET 文化敏感比较误判）
# ---------------------------------------------------------------------------
function Read-JsonFile([string]$path) {
    if (-not (Test-Path $path)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
        if ($raw.Length -gt 0 -and [int]$raw[0] -eq 0xFEFF) { $raw = $raw.Substring(1) }
        return ($raw | ConvertFrom-Json)
    } catch {
        Write-Fail "解析失败: $path -> $($_.Exception.Message.Split([char]10)[0])"
        return $null
    }
}

# ---------------------------------------------------------------------------
# 工作台「自有资产」清单 —— 与 install-pi.ps1 严格对齐
# ---------------------------------------------------------------------------
function Get-WorkbenchSkillNames {
    $names = @()
    $src = Join-Path $Root 'Tool\skill'
    if (-not (Test-Path $src)) { return $names }
    foreach ($s in (Get-ChildItem $src -Directory -ErrorAction SilentlyContinue)) {
        if ($s.Name -eq 'safe-skills') {
            foreach ($sub in (Get-ChildItem $s.FullName -Directory -ErrorAction SilentlyContinue)) {
                $names += $sub.Name
            }
        } elseif ($s.Name -ne 'update') {
            $names += $s.Name
        }
    }
    return ($names | Select-Object -Unique)
}

$WorkbenchPackages = @(
    'npm:pi-open-tui', 'npm:pi-web-access', 'npm:@juicesharp/rpiv-todo',
    'npm:@narumitw/pi-btw', 'npm:@narumitw/pi-plan-mode', 'npm:@narumitw/pi-usage',
    'npm:pi-mcp-extension', 'npm:@smoose/pi-themes', 'npm:pi-tool-display',
    'npm:@juicesharp/rpiv-ask-user-question', 'npm:pi-playwright', 'npm:pi-goal-x'
)

# 只有参数中确实指向工作台组件时，才认定该 MCP 条目归工作台所有
function Test-McpEntryIsOurs([string]$name, $entry) {
    $argStr = ''
    if ($entry -and $entry.args) { $argStr = (@($entry.args) -join ' ') }
    switch ($name) {
        'seep'       { return ($argStr -like '*seep_mcp_server.py*') }
        'js-reverse' { return ($argStr -like '*js-reverse-mcp*') }
        'playwright' { return ($argStr -like '*@playwright/mcp*') }
        default      { return $false }
    }
}

# ---------------------------------------------------------------------------
# 备份：把即将被删除/修改的文件整体拷进备份目录
# ---------------------------------------------------------------------------
function Backup-Item([string]$src, [string]$backupRoot, [string]$label) {
    if (-not (Test-Path $src)) { return }
    $dst = Join-Path $backupRoot $label
    $parent = Split-Path -Parent $dst
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    try {
        Copy-Item $src $dst -Recurse -Force -ErrorAction Stop
        Write-Info "已备份: $label"
    } catch {
        Write-Warn2 "备份失败（不影响卸载）: $label"
    }
}

# ===========================================================================
# 模式 A：从备份恢复
# ===========================================================================
if ($Restore) {
    Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
    Write-Host "║   Seep Lab —— 从备份恢复                                   ║" -ForegroundColor Magenta
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Magenta

    if (-not (Test-Path $Restore)) {
        Write-Fail "备份目录不存在: $Restore"
        exit 1
    }
    Write-Step "1/2  扫描备份内容"
    $items = @(Get-ChildItem $Restore -Recurse -Force -ErrorAction SilentlyContinue)
    Write-Info "备份目录: $Restore"
    Write-Info "条目数: $($items.Count)"

    Write-Step "2/2  恢复"
    if ($DryRun) {
        foreach ($i in $items) { Write-Info "将恢复: $($i.FullName.Substring($Restore.Length).TrimStart('\'))" }
        Write-Warn2 '-DryRun 模式，未做任何修改'
        exit 0
    }
    $restored = 0
    foreach ($i in $items) {
        $rel = $i.FullName.Substring($Restore.Length).TrimStart('\')
        $dst = Join-Path $AgentDir $rel
        try {
            if ($i.PSIsContainer) {
                if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
            } else {
                $p = Split-Path -Parent $dst
                if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
                Copy-Item $i.FullName $dst -Force -ErrorAction Stop
                $restored++
            }
        } catch { Write-Fail "恢复失败: $rel" }
    }
    Write-Ok "已恢复 $restored 个文件"
    Write-Info "请完全重启 Agent 会话后生效"
    exit 0
}

# ===========================================================================
# 模式 B：卸载
# ===========================================================================
Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║   Seep 逆向工程工作台 —— 一键卸载                             ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Magenta
if ($DryRun) { Write-Warn2 'DRY-RUN 模式：只预览，不做任何修改' }

# ---------------------------------------------------------------- 1. 盘点
Write-Step '1/5  盘点将要移除的内容'
$plan = [ordered]@{}

$skillNames = Get-WorkbenchSkillNames
$skillHits = @()
if (-not $KeepSkills) {
    foreach ($n in $skillNames) {
        $p = Join-Path $SkillsDir $n
        if (Test-Path $p) { $skillHits += $n }
    }
}
$plan['技能 (skills)'] = $skillHits

$promptHits = @()
if (-not $KeepPrompts) {
    foreach ($f in @('AGENTS.md', 'SYSTEM.md')) {
        if (Test-Path (Join-Path $AgentDir $f)) { $promptHits += $f }
    }
    if (Test-Path $ExtDir) {
        foreach ($f in (Get-ChildItem $ExtDir -Filter '*.ts' -ErrorAction SilentlyContinue)) {
            $promptHits += "extensions/$($f.Name)"
        }
    }
}
$plan['提示词与扩展'] = $promptHits

$mcpCfg = Read-JsonFile $McpJson
$mcpHits = @()
if ((-not $KeepMcp) -and $mcpCfg -and $mcpCfg.mcpServers) {
    foreach ($p in $mcpCfg.mcpServers.PSObject.Properties) {
        if (Test-McpEntryIsOurs $p.Name $p.Value) { $mcpHits += $p.Name }
    }
}
$plan['MCP 条目'] = $mcpHits

$setCfg = Read-JsonFile $SetJson
$pkgHits = @()
if ((-not $KeepPackages) -and $setCfg -and $setCfg.packages) {
    foreach ($pkg in @($setCfg.packages)) {
        if ($WorkbenchPackages -contains $pkg) { $pkgHits += $pkg }
    }
}
$plan['settings packages'] = $pkgHits

$flagHits = @()
if ((-not $KeepLabFlag) -and (Test-Path $LabFlag)) { $flagHits += 'lab-mode.flag' }
$plan['实验环境标志'] = $flagHits

foreach ($k in $plan.Keys) {
    $v = $plan[$k]
    if ($v.Count -eq 0) { Write-Info "$k : （无）" }
    else { Write-Ok "$k : $($v.Count) 项 -> $($v -join ', ')" }
}

# 保护声明
Write-Step '2/5  用户自有数据保护声明'
foreach ($f in @('models.json', 'auth.json', 'sessions/', 'logs/')) {
    if (Test-Path (Join-Path $AgentDir $f)) { Write-Ok "保留: $f" }
}
$userMcp = @()
if ($mcpCfg -and $mcpCfg.mcpServers) {
    foreach ($p in $mcpCfg.mcpServers.PSObject.Properties) {
        if (-not (Test-McpEntryIsOurs $p.Name $p.Value)) { $userMcp += $p.Name }
    }
}
if ($userMcp.Count -gt 0) { Write-Ok "保留你自己的 MCP 条目: $($userMcp -join ', ')" }
$userSkills = @()
if (Test-Path $SkillsDir) {
    foreach ($d in (Get-ChildItem $SkillsDir -Directory -ErrorAction SilentlyContinue)) {
        if ($skillNames -notcontains $d.Name) { $userSkills += $d.Name }
    }
}
if ($userSkills.Count -gt 0) { Write-Ok "保留你自己安装的技能: $($userSkills -join ', ')" }

$totalToRemove = 0
foreach ($k in $plan.Keys) { $totalToRemove += $plan[$k].Count }
if ($totalToRemove -eq 0) {
    Write-Host "`n[√] 没有发现需要移除的工作台内容，系统已是干净状态。" -ForegroundColor Green
    exit 0
}

if ($DryRun) {
    Write-Host "`n[DRY-RUN] 以上 $totalToRemove 项将被移除，未做任何修改。" -ForegroundColor Yellow
    Write-Info '去掉 -DryRun 参数即可真正执行'
    exit 0
}

# ---------------------------------------------------------------- 3. 确认
if (-not $Yes) {
    Write-Host "`n即将移除以上 $totalToRemove 项。你的数据（模型凭据 / 自定义配置）不会被触碰。" -ForegroundColor Yellow
    $ans = Read-Host '确认卸载？输入 yes 继续'
    if ($ans -notin @('yes', 'y', 'Y', 'YES')) { Write-Info '已取消'; exit 0 }
}

# ---------------------------------------------------------------- 4. 执行
Write-Step '3/5  备份受影响文件'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $AgentDir "backup-uninstall-$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Write-Info "备份目录: $backupRoot"

foreach ($n in $skillHits)   { Backup-Item (Join-Path $SkillsDir $n) $backupRoot "skills/$n" }
foreach ($f in @('AGENTS.md', 'SYSTEM.md')) {
    if ($promptHits -contains $f) { Backup-Item (Join-Path $AgentDir $f) $backupRoot $f }
}
foreach ($f in (Get-ChildItem $ExtDir -Filter '*.ts' -ErrorAction SilentlyContinue)) {
    if ($promptHits -contains "extensions/$($f.Name)") { Backup-Item $f.FullName $backupRoot "extensions/$($f.Name)" }
}
if ($mcpHits.Count -gt 0 -or $pkgHits.Count -gt 0) {
    Backup-Item $McpJson $backupRoot 'mcp.json'
    Backup-Item $SetJson $backupRoot 'settings.json'
}
if ($flagHits.Count -gt 0) { Backup-Item $LabFlag $backupRoot 'lab-mode.flag' }

Write-Step '4/5  执行移除'
foreach ($n in $skillHits) {
    try {
        Remove-Item (Join-Path $SkillsDir $n) -Recurse -Force -ErrorAction Stop
        Write-Ok "已移除技能: $n"; $script:Removed++
    } catch { Write-Fail "移除技能失败: $n"; $script:Failed++ }
}
foreach ($f in $promptHits) {
    $p = Join-Path $AgentDir ($f -replace '/', '\')
    try {
        Remove-Item $p -Force -ErrorAction Stop
        Write-Ok "已移除: $f"; $script:Removed++
    } catch { Write-Fail "移除失败: $f"; $script:Failed++ }
}

# MCP：外科手术式移除，保留用户其他条目
if ($mcpHits.Count -gt 0) {
    try {
        $cfg = Read-JsonFile $McpJson
        $keep = [ordered]@{}
        foreach ($p in $cfg.mcpServers.PSObject.Properties) {
            if ($mcpHits -notcontains $p.Name) { $keep[$p.Name] = $p.Value }
        }
        $newObj = [PSCustomObject]@{ mcpServers = [PSCustomObject]$keep }
        $json = $newObj | ConvertTo-Json -Depth 20
        [System.IO.File]::WriteAllText($McpJson, $json, (New-Object System.Text.UTF8Encoding $false))
        Write-Ok "已移除 MCP 条目: $($mcpHits -join ', ')（保留 $($keep.Keys.Count) 个）"
        $script:Removed += $mcpHits.Count
    } catch { Write-Fail "mcp.json 清理失败: $($_.Exception.Message)"; $script:Failed++ }
}

# settings.json：只移除工作台加入的 packages
if ($pkgHits.Count -gt 0) {
    try {
        $cfg = Read-JsonFile $SetJson
        $remain = @()
        foreach ($pkg in @($cfg.packages)) {
            if ($WorkbenchPackages -notcontains $pkg) { $remain += $pkg }
        }
        $cfg | Add-Member -NotePropertyName 'packages' -NotePropertyValue $remain -Force
        $json = $cfg | ConvertTo-Json -Depth 20
        [System.IO.File]::WriteAllText($SetJson, $json, (New-Object System.Text.UTF8Encoding $false))
        Write-Ok "已从 settings.json 移除 $($pkgHits.Count) 个 packages（保留 $($remain.Count) 个）"
        $script:Removed += $pkgHits.Count
    } catch { Write-Fail "settings.json 清理失败: $($_.Exception.Message)"; $script:Failed++ }
}

if ($flagHits.Count -gt 0) {
    try {
        Remove-Item $LabFlag -Force -ErrorAction Stop
        Write-Ok '已移除 lab-mode.flag（实验环境已退出）'; $script:Removed++
    } catch { Write-Fail '移除 lab-mode.flag 失败'; $script:Failed++ }
}

# DSH：插件包 + 我们写的那条配置 + 状态文件（1.14.0 起的主路线）
$dshHomeDir = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
if (Test-Path $dshHomeDir) {
    $dshCli = Get-Command dsh -ErrorAction SilentlyContinue
    $dshProfilePkg = Join-Path $dshHomeDir 'profiles\web\package.json'
    $dshPatch = Join-Path $dshHomeDir 'profiles\web\cordis.patch.yml'

    $hasPlugin = $false
    if (Test-Path $dshProfilePkg) {
        try {
            $pj = Get-Content $dshProfilePkg -Raw -Encoding UTF8 | ConvertFrom-Json
            $hasPlugin = @($pj.dsh.profile.bundles) -contains 'seep-lab'
        } catch { }
    }

    if ($hasPlugin) {
        if ($dshCli) {
            & dsh plugin --profile web remove seep-lab 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Ok '已从 DSH 卸下插件包 seep-lab'; $script:Removed++ }
            else { Write-Warn '插件包卸载返回非 0，可能已不存在；配置条目仍会被清理' }
        }
        else { Write-Warn 'PATH 里没有 dsh，只能清理配置条目；如需彻底移除请手动 dsh plugin remove' }
    }

    # 我们写进 profile 的那条配置（只在能唯一定位时删，避免误伤别的条目）
    if (Test-Path $dshPatch) {
        $body = Get-Content $dshPatch -Raw -Encoding UTF8
        if ($body -match '(?m)^- id:\s*seep-workbench-boot\s*$') {
            try {
                Copy-Item $dshPatch "$dshPatch.bak" -Force
                # 删掉从这条 id 到下一个顶层列表项之间的内容
                $lines = Get-Content $dshPatch -Encoding UTF8
                $out = New-Object System.Collections.Generic.List[string]
                $skipping = $false
                foreach ($line in $lines) {
                    if ($line -match '^- id:\s*seep-workbench-boot\s*$') { $skipping = $true; continue }
                    if ($skipping -and $line -match '^- \S') { $skipping = $false }
                    if (-not $skipping) { $out.Add($line) }
                }
                $text = ($out -join "`n").TrimEnd() + "`n"
                [System.IO.File]::WriteAllText($dshPatch, $text, (New-Object System.Text.UTF8Encoding $false))
                Write-Ok '已移除 DSH profile 里的 seep-workbench-boot 配置（备份 .bak）'; $script:Removed++
            } catch { Write-Fail "DSH 配置清理失败: $($_.Exception.Message)"; $script:Failed++ }
        }
    }

    $dshStatus = Join-Path $dshHomeDir 'seep-workbench.status.json'
    if (Test-Path $dshStatus) {
        try { Remove-Item $dshStatus -Force -ErrorAction Stop; Write-Ok '已移除 DSH 插件状态文件'; $script:Removed++ }
        catch { Write-Warn '状态文件删不掉，可手动删除（不影响使用）' }
    }
}

# ---------------------------------------------------------------- 5. 可选深度清理
if ($Purge) {
    Write-Step '5/5  深度清理 (-Purge)'
    $purged = 0
    foreach ($b in (Get-ChildItem $AgentDir -Directory -Filter 'backup-*' -ErrorAction SilentlyContinue)) {
        if ($b.FullName -eq $backupRoot) { continue }  # 保留本次卸载备份
        try { Remove-Item $b.FullName -Recurse -Force -ErrorAction Stop; $purged++ }
        catch { Write-Warn2 "无法删除: $($b.Name)" }
    }
    foreach ($g in @('setup\cordis.generated.yml',
                     'Tool\scripts\compliance-relay\relay-config.json')) {
        $p = Join-Path $Root $g
        if (Test-Path $p) {
            try { Remove-Item $p -Force -ErrorAction Stop; Write-Ok "已删除生成配置: $g"; $purged++ }
            catch { Write-Warn2 "无法删除: $g" }
        }
    }
    Write-Ok "深度清理完成，共 $purged 项（本次卸载备份已保留）"
} else {
    Write-Step '5/5  深度清理'
    Write-Info '未启用 -Purge，历史备份与生成配置均已保留'
}

# ---------------------------------------------------------------- 报告
Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   ✅ 卸载完成                                                 ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Ok "已移除: $($script:Removed) 项"
if ($script:Failed -gt 0) { Write-Fail "失败: $($script:Failed) 项（多为文件被占用，关闭 Agent 后重试）" }
Write-Info "卸载备份: $backupRoot"
Write-Info "如需恢复: powershell -File .\setup\uninstall.ps1 -Restore `"$backupRoot`""
Write-Host ''
Write-Info '工作台本体目录未删除。若确认不再需要，可手动删除整个工作台文件夹。'
Write-Info '请完全重启 Agent 会话，使卸载生效。'
exit 0

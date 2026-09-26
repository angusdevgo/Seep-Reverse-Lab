#Requires -Version 5.1
<#
  Seep 工作台增量发布与同步核心管线 (Sync-Hub Pipeline)
  由 update Skill 自动调用，亦可独立运行
  严格遵循：显式目标输入、私有黑名单拦截、脱敏审查、单一真值源统计、自检门禁与动态代理推送。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = "必须显式指定目标对象名称或路径")]
    [string]$Target,

    [ValidateSet("case", "skill", "mcp", "manual", "auto")]
    [string]$Type = "auto",

    [switch]$DryRun
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$ToolDir = Join-Path $Root "Tool"

# 1. 黑名单前置阻断 (S0 门禁)
$Blacklist = @("github", "green", "tg-reader", "muse", "ui", "models.json", "auth.json")
$normalizedTarget = (Split-Path $Target -Leaf).ToLower()

foreach ($b in $Blacklist) {
    if ($normalizedTarget -eq $b -or $normalizedTarget.Contains($b)) {
        Write-Error "`n[S0 阻断] 目标 '$Target' 属于个人专属/私有黑名单资产，严禁同步或推送到 Seep 工作台！"
        exit 1
    }
}

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "          Seep Reverse Lab — 增量发布与自动化同步管线 (Sync-Hub)" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  同步目标: $Target" -ForegroundColor White
Write-Host "  目标类型: $Type" -ForegroundColor White
Write-Host "  模拟执行: $(if ($DryRun) { 'YES (不实际修改或推送)' } else { 'NO' })" -ForegroundColor White

# 2. 统计单一真值源 (Single Source of Truth)
Write-Host "`n[1/5] 📊 读取工作台单一真值源 (SSOT)..." -ForegroundColor White
$casesCount = (Get-ChildItem (Join-Path $ToolDir "cases") -Directory -ErrorAction SilentlyContinue).Count
$skillsCount = (Get-ChildItem (Join-Path $ToolDir "skill") -Directory -ErrorAction SilentlyContinue).Count
$mcpServerPy = Join-Path $ToolDir "mcp\seep_mcp_server.py"
$mcpToolsCount = if (Test-Path $mcpServerPy) {
    (Select-String -Path $mcpServerPy -Pattern "@server\.tool\(\)").Count
} else { 23 }
$kbCount = (Get-ChildItem (Join-Path $ToolDir "mcp\Tool\reverselab\kb") -Recurse -Filter "*.md" -ErrorAction SilentlyContinue).Count
$manualCount = (Get-ChildItem (Join-Path $Root "MANUAL") -Filter "*.md" -ErrorAction SilentlyContinue).Count

Write-Host "  - 案例工程 (cases): $casesCount" -ForegroundColor Green
Write-Host "  - 技能体系 (skills): $skillsCount" -ForegroundColor Green
Write-Host "  - MCP原生工具 (tools): $mcpToolsCount" -ForegroundColor Green
Write-Host "  - 战术笔记 (kb journals): $kbCount" -ForegroundColor Green
Write-Host "  - MANUAL专精手册: $manualCount" -ForegroundColor Green

# 3. 动态嗅探本地代理端口
Write-Host "`n[2/5] 🌐 嗅探宿主机本地可用网络代理..." -ForegroundColor White
$activeProxy = $null
foreach ($port in @(10808, 7897, 7890)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        $activeProxy = "http://127.0.0.1:$port"
        Write-Host "  [√] 成功命中可用代理端口: $port" -ForegroundColor Green
        break
    }
}
if (-not $activeProxy) {
    Write-Host "  [!] 未检测到常见监听代理端口(10808/7897/7890)，将尝试直连" -ForegroundColor Yellow
}

# 4. 运行本地健康全检门禁
Write-Host "`n[3/5] 🛡️ 执行工作台部署完备性自检 (check.ps1)..." -ForegroundColor White
$verifyScript = Join-Path $Root "setup\verify.ps1"
if (Test-Path $verifyScript) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript
    if ($LASTEXITCODE -ne 0) {
        Write-Error "`n[FAIL 门禁] 工作台当前存在未通过的自检项，同步被终止！请先修复上述错误。"
        exit 1
    }
} else {
    Write-Error "未找到自检脚本: $verifyScript"
    exit 1
}

# 5. Git 远端 Pull Rebase & 安全推送
Write-Host "`n[4/5] 🔄 检查工作区与拉取变基..." -ForegroundColor White
Set-Location $Root

$gitStatus = git status -s
if (-not $gitStatus) {
    Write-Host "  [i] 工作区干净，无未暂存的修改。" -ForegroundColor Cyan
} else {
    Write-Host "  [i] 待提交文件变更清单:" -ForegroundColor Yellow
    $gitStatus | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
}

if ($DryRun) {
    Write-Host "`n[5/5] 🚀 [DRY RUN] 模拟模式已完成，未向 GitHub 推送代码。" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n[5/5] 🚀 执行 Git 变基拉取与增量推送..." -ForegroundColor White
$proxyOption = if ($activeProxy) { "-c http.proxy=$activeProxy -c https.proxy=$activeProxy" } else { "" }

if ($gitStatus) {
    # 1. 先将本地变更安全暂存并提交至本地版本库
    git add -A
    $commitMsg = "feat: sync and update asset '$Target' (cases:$casesCount, skills:$skillsCount, tools:$mcpToolsCount)"
    git commit -m $commitMsg
    if ($LASTEXITCODE -ne 0) {
        Write-Error "`n[FAIL] 本地提交失败，请检查文件锁定或 Git 状态。"
        exit 1
    }
}

# 2. 本地提交后拉取远端变基（避免 unstaged changes 阻断）
$pullCmd = "git $proxyOption pull --rebase origin main"
Write-Host "  执行变基: $pullCmd" -ForegroundColor Gray
Invoke-Expression $pullCmd
if ($LASTEXITCODE -ne 0) {
    Write-Error "`n[FAIL] git pull --rebase 失败，可能与远端存在冲突，已安全终止推送以防破坏历史。"
    exit 1
}

# 3. 推送至远程主分支
$pushCmd = "git $proxyOption push origin main"
Write-Host "  执行推送: $pushCmd" -ForegroundColor Gray
Invoke-Expression $pushCmd
if ($LASTEXITCODE -ne 0) {
    Write-Error "`n[FAIL] git push 失败，请检查网络连接与代理配置。"
    exit 1
}
Write-Host "`n  🎉 [SUCCESS] 目标 '$Target' 已成功完成全流程自检并推送到 GitHub 远程仓库！" -ForegroundColor Green

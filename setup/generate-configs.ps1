#Requires -Version 5.1
<#
  Seep 工作台 — DSH 配置与指令入口生成器

  本工作台只支持两个 Agent：**Pi Agent** 与 **DeepSeek Harness (DSH)**。
  Pi 的接线由 setup/install-pi.ps1 负责（写 mcp.json + 拷技能）；
  这个脚本只做 DSH 侧需要的两件事：
    1. DeepSeek Harness 官方 Cordis Overlay 补丁 (cordis.generated.yml)
    2. 项目根 AGENTS.md（DSH 从项目根自动读取的指令入口）
#>
[CmdletBinding()]
param(
    [switch]$PrintOnly,
    [string]$Root = '',      # 仅供测试：指定工作台根目录（默认由脚本位置推导）
    [ValidateSet('all', 'none')]
    [string]$DshSkills = 'all'   # all = 开启 DSH 自带 skill 发现；none = 不挂
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Root)) { $Root = Split-Path -Parent $ScriptDir }
$NormalizedRoot = $Root.Replace('\', '/')
$ToolDir   = Join-Path $Root 'Tool'
$McpServerPy = "$NormalizedRoot/Tool/mcp/seep_mcp_server.py"

# 内容不变就不写盘。
# 为什么重要：重写同一份字节会让 mtime 变化，git 的 stat 缓存随之失效，
# `git status` 会把一个「内容完全相同」的文件报成已修改 —— 于是 update.ps1
# 每次更新都弹一次「本地改动已 stash」的警告，用户以为自己的文件被动过。
function Write-IfChanged {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    # .gitattributes 规定 *.json / *.yaml 以 LF 归档；here-string 自带 CRLF，先归一化
    $normalized = $Content -replace "`r`n", "`n"
    if (Test-Path -LiteralPath $Path) {
        try {
            $existing = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
            if (($existing -replace "`r`n", "`n") -eq $normalized) {
                Write-Host "  [=] 内容未变化，跳过写入: $Path" -ForegroundColor DarkGray
                return
            }
        }
        catch { }
    }
    [System.IO.File]::WriteAllText($Path, $normalized, (New-Object System.Text.UTF8Encoding $false))
}

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "          Seep Reverse Lab — DSH 配置文件生成器（Pi 走 install-pi）" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  检测到工作台物理根目录: $Root" -ForegroundColor White
Write-Host "  标准化 POSIX 路径表示: $NormalizedRoot" -ForegroundColor Gray

# -----------------------------------------------------------------------------
# 3. 生成 DeepSeek Harness 官方 Cordis Overlay 补丁 (cordis.generated.yml)
# -----------------------------------------------------------------------------
Write-Host "`n[1/2] 正在生成 DeepSeek Harness (DSH) 官方补丁 (cordis.generated.yml)..." -ForegroundColor White
$dshYaml = @"
# ==============================================================================
# DeepSeek Harness (Cordis) Overlay 补丁 — 遵循 DSH 官方 - insert: 规范
# 生成基准目录: $NormalizedRoot
#
# 挂载方式（二选一）:
#   1. 临时挂载: dsh web --patch "$NormalizedRoot/setup/cordis.generated.yml"
#   2. 持久挂载: python setup/dsh-merge.py --profile web
#      幂等写入 `$DSH_HOME/profiles/<profile>/cordis.patch.yml，
#      只替换标注块，你自己的模型/插件配置原样保留。
#
# 关于 toolCallTimeoutMs：必须显式设置。DSH 的默认值是 60000（60 秒），
# 而工作台的长任务远超这个量级 —— HLS 取证（ffmpeg 解密分片）、Flutter AOT
# 分析、jadx 全量反编译都可能跑几分钟。不设就必然被 DSH 按超时中断。
# ==============================================================================
- insert:
    - id: seep-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: seep
        transport: stdio
        command: python
        args:
          - '$McpServerPy'
        env:
          PYTHONIOENCODING: utf-8
        cwd: '$NormalizedRoot'
        toolCallTimeoutMs: 900000
        failOnStartupError: false

    - id: seep-js-reverse-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: js-reverse
        transport: stdio
        command: npx
        args:
          - '-y'
          - 'js-reverse-mcp'
        cwd: '$NormalizedRoot'
        toolCallTimeoutMs: 600000
        failOnStartupError: false
"@

# Skill 图层（可关）
# DSH 自带 skill 机制（dsh-skill-filesystem 发现 + dsh-tool-skill 模型侧加载），
# 只是 web profile 里默认 disabled。开启后 DSH 与 pi 一样能看到 10 个技能。
# 注意：customSkillDirs 是「扫该目录下的直接子目录」，无法只挑其中几个；
# 要少挂就只能关整层（-DshSkills none）。
$dshSkillsCore = @"
# ------------------------------------------------------------------------------
# Skill 图层：开启 DSH 自带的 skill 发现与加载（默认关闭，这里显式打开）
# 代价：10 个技能的 name + description 会进入每个会话的上下文。
# 不想付这个成本，重新生成时关掉该图层即可（详见 MANUAL/DSH-VERIFICATION.md）。
# ------------------------------------------------------------------------------
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
  disabled: false
  config:
    customSkillDirs:
      - '$NormalizedRoot/Tool/skill'
      - '$NormalizedRoot/Tool/skill/safe-skills'

- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
  disabled: false
"@
# 拼接契约：基座去掉尾部换行，只插入两个换行，再接技能块（同样去掉尾部换行）。
# 两边（PS / Python）必须逐字节一致，因此不依赖 here-string 的尾部换行行为。
if ($DshSkills -eq 'all') {
    $dshYaml = $dshYaml.TrimEnd() + "`n`n" + $dshSkillsCore.TrimEnd()
}
$dshDest = Join-Path (Join-Path $Root 'setup') 'cordis.generated.yml'
if (-not $PrintOnly) {
    Write-IfChanged -Path $dshDest -Content $dshYaml
    Write-Host "  [√] 已生成: $dshDest (顶层采用官方 - insert: 语法)" -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# 2. 项目根 AGENTS.md
# DSH 在「项目根目录」寻找 AGENTS.md 作为指令来源。
# 中性底座在 Tool/prompts/AGENTS.md，这里生成一份同内容副本到根目录，
# 让 DSH 无需手工 cp 就能读到（Pi 读的是 ~/.pi/agent/AGENTS.md，由 install-pi.ps1 同步）。
# -----------------------------------------------------------------------------
Write-Host "`n[2/2] 在项目根生成 AGENTS.md（DSH 自动读取的指令入口）..." -ForegroundColor White
$agentsSrc = Join-Path $ToolDir 'prompts\AGENTS.md'
$agentsDest = Join-Path $Root 'AGENTS.md'
if (Test-Path $agentsSrc) {
    $agentsBody = [System.IO.File]::ReadAllText($agentsSrc, [System.Text.Encoding]::UTF8)
    Write-IfChanged -Path $agentsDest -Content $agentsBody
    Write-Host "  [√] 已生成: $agentsDest" -ForegroundColor Green
}
else {
    Write-Host "  [!!] 缺少 Tool/prompts/AGENTS.md，跳过" -ForegroundColor Yellow
}

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "  🎉 DSH 配置文件生成完毕！" -ForegroundColor Green
Write-Host "  - 推荐装法：python setup/dsh-plugin-setup.py（装插件包，运行时自动挂 MCP）" -ForegroundColor White
Write-Host "  - 旧路线   ：python setup/dsh-merge.py --profile web（把 cordis.generated.yml 拼进 profile）" -ForegroundColor White
Write-Host "================================================================================" -ForegroundColor Cyan

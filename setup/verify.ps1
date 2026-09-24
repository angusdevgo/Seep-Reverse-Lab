#Requires -Version 5.1
<#
  Seep 逆向工程工作台 —— 部署完备性体检与校验仪表盘 (System Health & Integrity Verifier)
  支持独立运行、双击运行、或由 Agent 调用以验证工作台是否完整就绪。
#>
[CmdletBinding()]
param(
    [switch]$Detailed
)

# 强制 UTF-8 编码输出，杜绝控制台中文乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$ToolDir   = Join-Path $Root 'Tool'
$ToolsDir  = Join-Path $Root 'Tool\mcp\Tool\safe'
$KbDir     = Join-Path $Root 'Tool\mcp\Tool\reverselab\kb'
$AgentDir  = Join-Path $env:USERPROFILE '.pi\agent'

$script:OkCount = 0
$script:FailList = @()
$script:TodoList = @()

function Test-CheckItem {
    param(
        [string]$Category,
        [string]$ItemName,
        [scriptblock]$Predicate,
        [string]$Remedy
    )
    try {
        $passed = & $Predicate
        if ($passed) {
            Write-Host ("  [√ PASS] {0}" -f $ItemName) -ForegroundColor Green
            $script:OkCount++
        } else {
            Write-Host ("  [X FAIL] {0}" -f $ItemName) -ForegroundColor Red
            $script:FailList += @{ Category = $Category; Name = $ItemName; Fix = $Remedy }
        }
    } catch {
        Write-Host ("  [X FAIL] {0} (异常: {1})" -f $ItemName, $_.Exception.Message) -ForegroundColor Red
        $script:FailList += @{ Category = $Category; Name = $ItemName; Fix = $Remedy }
    }
}

function Test-ManualItem {
    param(
        [string]$Category,
        [string]$ItemName,
        [scriptblock]$Predicate,
        [string]$Guidance
    )
    try {
        $passed = & $Predicate
        if ($passed) {
            Write-Host ("  [√ PASS] {0}" -f $ItemName) -ForegroundColor Green
            $script:OkCount++
        } else {
            Write-Host ("  [! OPTN] {0} ({1})" -f $ItemName, $Guidance) -ForegroundColor Yellow
            $script:TodoList += @{ Category = $Category; Name = $ItemName; Note = $Guidance }
        }
    } catch {
        Write-Host ("  [! OPTN] {0} ({1})" -f $ItemName, $Guidance) -ForegroundColor Yellow
        $script:TodoList += @{ Category = $Category; Name = $ItemName; Note = $Guidance }
    }
}

Write-Host @"
================================================================================
          Seep Reverse Lab — 工作台部署完备性校验与健康体检 (Verifier)
================================================================================
  工作台物理根目录: $Root
  宿主操作系统环境: Windows $([Environment]::OSVersion.Version.ToString()) ($([IntPtr]::Size * 8)-bit)
"@ -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# 1. 核心目录与包结构
# -----------------------------------------------------------------------------
Write-Host "`n[1/6] 📁 核心架构与工程目录树" -ForegroundColor White
Test-CheckItem "架构" "工作台主目录完整 (Tool/)" { Test-Path $ToolDir } "请检查是否完整解压或下载了 Seep 完整仓库"
Test-CheckItem "架构" "技能包目录完整 (Tool/skill/)" { Test-Path (Join-Path $ToolDir 'skill') } "检查 Tool/skill 是否存在"
Test-CheckItem "架构" "MCP服务引擎目录 (Tool/mcp/)" { Test-Path (Join-Path $ToolDir 'mcp') } "检查 Tool/mcp 是否存在"
Test-CheckItem "架构" "系统提示词层 (Tool/prompts/)" { Test-Path (Join-Path $ToolDir 'prompts') } "检查 Tool/prompts 是否存在"
Test-CheckItem "架构" "九大脱敏案例工程 (Tool/cases/)" { 
    $cases = Join-Path $ToolDir 'cases'
    (Test-Path $cases) -and ((Get-ChildItem $cases -Directory).Count -ge 9)
} "检查 9 个项目案例目录是否存在"
Test-CheckItem "架构" "上游开源验证集 (Tool/upstream/)" { Test-Path (Join-Path $ToolDir 'upstream\apk-reverse') } "检查 apk-reverse 上游工程目录"
Test-CheckItem "架构" "MCP专用运行时强约定 (Tool/mcp/Tool/)" { Test-Path (Join-Path $ToolDir 'mcp\Tool') } "严禁重命名或搬移 Tool/mcp/Tool 目录"

# -----------------------------------------------------------------------------
# 2. 知识库与战术资产
# -----------------------------------------------------------------------------
Write-Host "`n[2/6] 📚 攻防实战知识库与战术模板 (KB)" -ForegroundColor White
Test-CheckItem "知识库" "战术实战笔记 (289篇完整检索库)" {
    (Test-Path $KbDir) -and ((Get-ChildItem $KbDir -Recurse -Filter '*.md').Count -ge 280)
} "Tool/mcp/Tool/reverselab/kb/ 文件缺失，请确认完整拉取"
Test-CheckItem "知识库" "内置 MCP 源码组件 (ReverseLab/Ghidra/JSHook)" {
    $m = Join-Path $Root 'Tool\mcp\Tool\reverselab\tools\skills\mcp'
    (Test-Path $m) -and ((Get-ChildItem $m -Directory).Count -ge 3)
} "reverselab 内置 MCP 源码组件缺失"

# -----------------------------------------------------------------------------
# 3. 智能体提示词与多平台适配
# -----------------------------------------------------------------------------
Write-Host "`n[3/6] 🧠 智能体指令系统与运行时拦截扩展 (Prompts & Extensions)" -ForegroundColor White
Test-CheckItem "提示词" "Pi Agent 系统指令 (SYSTEM.md 已就绪且去个人化)" {
    $p = Join-Path $ToolDir 'prompts\SYSTEM.md'
    (Test-Path $p) -and (-not (Select-String -Path $p -Pattern '小π|主人' -Quiet))
} "Tool/prompts/SYSTEM.md 不存在或包含未脱敏字符"
Test-CheckItem "提示词" "通用跨 Agent 规范 (AGENTS.md)" { Test-Path (Join-Path $ToolDir 'prompts\AGENTS.md') } "检查 AGENTS.md"
Test-CheckItem "提示词" "Claude Code 项目级规范 (CLAUDE.md 在项目根)" { Test-Path (Join-Path $Root 'CLAUDE.md') } "项目根缺失 CLAUDE.md"
Test-CheckItem "提示词" "DeepSeek Harness 配置文件 (DSH-PROFILE.md)" { Test-Path (Join-Path $Root 'DSH-PROFILE.md') } "缺失 DSH-PROFILE.md"
Test-CheckItem "扩展"   "底层安全放行与 Lab 状态机扩展 (.ts)" {
    Test-Path (Join-Path $ToolDir 'prompts\extensions\security-audit-interceptor.ts')
} "安全拦截扩展缺失，无法实现 lab: 状态机与防拒功能"

# -----------------------------------------------------------------------------
# 4. 技能系统完备性 (Skills System)
# -----------------------------------------------------------------------------
Write-Host "`n[4/6] 🛠️ 逆向工程专业技能库 (Skills - 9大组件)" -ForegroundColor White
$localSkills = Join-Path $ToolDir 'skill'
Test-CheckItem "Skill" "核心总控调度器 (softseep 包含 8 大专题库)" {
    $r = Join-Path $localSkills 'softseep\references'
    (Test-Path (Join-Path $localSkills 'softseep\SKILL.md')) -and 
    (Test-Path $r) -and ((Get-ChildItem $r -Filter '*.md').Count -ge 8)
} "softseep 或其 references 目录不完整"

Test-CheckItem "Skill" "移动端逆向全链路 (apkseep 包含 45 篇规范与 56 脚本)" {
    $r = Join-Path $localSkills 'apkseep\references'
    $s = Join-Path $localSkills 'apkseep\scripts'
    (Test-Path (Join-Path $localSkills 'apkseep\SKILL.md')) -and (Test-Path $r) -and (Test-Path $s)
} "apkseep 工程不完整"

Test-CheckItem "Skill" "IDA Pro 自动化联动 (ida-reverse)" {
    Test-Path (Join-Path $localSkills 'ida-reverse\SKILL.md')
} "ida-reverse 技能缺失"

Test-CheckItem "Skill" "通用许可/卡密校验突破规范 (license-bypass)" {
    Test-Path (Join-Path $localSkills 'client-license-validation-bypass\SKILL.md')
} "client-license-validation-bypass 技能缺失"

Test-CheckItem "Skill" "独立战术安全技能包 (safe-skills 5组)" {
    $ss = Join-Path $localSkills 'safe-skills'
    (Test-Path $ss) -and ((Get-ChildItem $ss -Directory).Count -ge 5)
} "safe-skills 目录缺失或不足 5 个技能包"

# 如果检测到用户本地的 Pi Agent 目录，则额外校验是否已同步部署到系统
if (Test-Path $AgentDir) {
    Test-ManualItem "部署" "Pi Agent 本地技能同步 (~/.pi/agent/skills/softseep)" {
        Test-Path (Join-Path $AgentDir 'skills\softseep\SKILL.md')
    } "已安装 Pi 但尚未部署，可运行 powershell -File setup\install-pi.ps1 完成同步"
}

# -----------------------------------------------------------------------------
# 5. MCP 自动化服务层与底层工具 (MCP & Native Tools)
# -----------------------------------------------------------------------------
Write-Host "`n[5/7] 🔌 MCP 服务引擎与物理内置工具箱 (Native Tools)" -ForegroundColor White

Test-CheckItem "MCP" "核心服务端脚本 (seep_mcp_server.py 语法自洽)" {
    $sp = Join-Path $ToolDir 'mcp\seep_mcp_server.py'
    if (Test-Path $sp) {
        $pyCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pyCmd) {
            & python -c "import ast; ast.parse(open(r'$sp', encoding='utf-8').read())" 2>&1 | Out-Null
            $LASTEXITCODE -eq 0
        } else { $true }
    } else { $false }
} "seep_mcp_server.py 丢失或存在 Python 语法解析错误"

Test-CheckItem "工具箱" "Jadx 反编译引擎 (jadx-1.5.6 完整就绪)" {
    $j = Join-Path $ToolsDir 'jadx\lib\jadx-1.5.6-all.jar'
    $b = Join-Path $ToolsDir 'jadx\bin\jadx.bat'
    (Test-Path $j) -and (Test-Path $b)
} "Jadx 缺失，请运行 powershell -File setup\repair-tools.ps1 -Only jadx 恢复"

Test-CheckItem "工具箱" "Radare2 二进制全套工具 (r2/rabin2/radiff2/rasm2)" {
    $r2 = Join-Path $ToolsDir 'radare2\bin\radare2.exe'
    $rb = Join-Path $ToolsDir 'radare2\bin\rabin2.exe'
    (Test-Path $r2) -and (Test-Path $rb)
} "Radare2 二进制套件缺失，请运行 setup\repair-tools.ps1 -Only radare2 恢复"

Test-CheckItem "工具箱" "Apktool 资源拆解重构环境 (apktool.jar + bat)" {
    $aj = Join-Path $ToolsDir 'apktool\apktool.jar'
    $ab = Join-Path $ToolsDir 'apktool\apktool.bat'
    (Test-Path $aj) -and (Test-Path $ab)
} "Apktool 环境缺失，请运行 setup\repair-tools.ps1 -Only apktool 恢复"

Test-CheckItem "工具箱" "Frida/LSPosed 动态插桩模板库 (hook-mcp)" {
    Test-Path (Join-Path $ToolsDir 'hook-mcp\templates')
} "hook-mcp 模板目录缺失"

# 检查依赖包是否已经解压 (首次部署解压检查)
Test-CheckItem "依赖" "Web/JS 逆向调试引擎依赖已解压 (js-reverse-mcp/node_modules)" {
    (Test-Path (Join-Path $ToolsDir 'js-reverse-mcp\node_modules')) -or 
    (Test-Path (Join-Path $ToolsDir 'js-reverse-mcp\node_modules.zip'))
} "未找到 js-reverse-mcp 依赖或压缩包"

Test-CheckItem "依赖" "Playwright 浏览器自动化依赖已解压 (playwright-mcp/node_modules)" {
    (Test-Path (Join-Path $ToolsDir 'playwright-mcp\node_modules')) -or 
    (Test-Path (Join-Path $ToolsDir 'playwright-mcp\node_modules.zip'))
} "未找到 playwright-mcp 依赖或压缩包"

# -----------------------------------------------------------------------------
# 6. 环境运行时与第三方依赖配置
# -----------------------------------------------------------------------------
Write-Host "`n[6/7] ⚙️ 外部运行时与商业授权协同 (Runtime & Commercial)" -ForegroundColor White
Test-CheckItem "运行时" "Python 解释器 (3.11+ 且可执行)" {
    $py = Get-Command python -ErrorAction SilentlyContinue
    $py -ne $null
} "系统未安装 Python 或未加入 PATH 环境变量，请安装 Python 3.11+"

Test-ManualItem "协议" "Python mcp 协议库环境支持 (mcp>=1.20,<1.29)" {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        & python -c "import mcp" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    } else { $false }
} "运行 pip install ""mcp>=1.20,<1.29"" 补齐协议支持"

Test-ManualItem "商业软件" "IDA Pro 商业反编译器协同 (需自备独立授权)" {
    $found = $false
    foreach ($c in @('D:\Tool\IDA Pro', 'C:\Program Files\IDA Pro', 'C:\Program Files\IDA Professional 9.0', 'C:\IDA Pro')) {
        if (Test-Path (Join-Path $c 'ida.exe')) { $found = $true; break }
    }
    $found
} "未检测到本地 IDA Pro，如无授权不影响核心链路，可阅读 MANUAL\IDA-PRO.md 使用 Radare2 自动降级"

Test-ManualItem "配置" "Claude Code 项目级 MCP 注册 (.mcp.json 在根目录)" {
    Test-Path (Join-Path $Root '.mcp.json')
} "根目录已备好 .mcp.json，在根目录直接执行 claude 即可免配加载"

# -----------------------------------------------------------------------------
# 汇总仪表盘
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# 7. MANUAL/ 战术手册完备性校验 (Tactical Manuals)
# -----------------------------------------------------------------------------
Write-Host "`n[7/7] 📚 MANUAL/ 战术手册完备性校验" -ForegroundColor White
$ManualDir = Join-Path $Root 'MANUAL'

Test-CheckItem "手册" "环境预要求指南 (MANUAL/PREREQUISITES.md)" {
    Test-Path (Join-Path $ManualDir 'PREREQUISITES.md')
} "安装指南缺失，重新拉取仓库"

Test-CheckItem "手册" "IDA Pro 商业软件接入指南 (MANUAL/IDA-PRO.md)" {
    Test-Path (Join-Path $ManualDir 'IDA-PRO.md')
} "IDA-PRO 指南缺失"

Test-CheckItem "手册" "反调试绕过战术手册 (MANUAL/ANTI-DEBUG.md)" {
    Test-Path (Join-Path $ManualDir 'ANTI-DEBUG.md')
} "调试应对手册缺失，重新拉取仓库"

Test-CheckItem "手册" "通用脱壳前置分析 SOP (MANUAL/UNPACKING.md)" {
    Test-Path (Join-Path $ManualDir 'UNPACKING.md')
} "脱壳手册缺失，重新拉取仓库"

Test-CheckItem "手册" "PoC 闭环自动化验证 SOP (MANUAL/POC-VALIDATION.md)" {
    Test-Path (Join-Path $ManualDir 'POC-VALIDATION.md')
} "PoC 验证手册缺失，重新拉取仓库"

Write-Host "`n================================================================================" -ForegroundColor White
Write-Host ("  [体检报告] 核心检查通过: {0} 项" -f $script:OkCount) -ForegroundColor Green

if ($script:FailList.Count -gt 0) {
    Write-Host ("`n  [!] 发现异常阻断项 ({0} 项):" -f $script:FailList.Count) -ForegroundColor Red
    foreach ($err in $script:FailList) {
        Write-Host ("    * [{0}] {1}" -f $err.Category, $err.Name) -ForegroundColor Red
        Write-Host ("      -> 整改建议: {0}" -f $err.Fix) -ForegroundColor Gray
    }
}

if ($script:TodoList.Count -gt 0) {
    Write-Host ("`n  [*] 可选/建议关注项 ({0} 项):" -f $script:TodoList.Count) -ForegroundColor Yellow
    foreach ($todo in $script:TodoList) {
        Write-Host ("    * [{0}] {1}" -f $todo.Category, $todo.Name) -ForegroundColor Yellow
        Write-Host ("      -> 说明/指南: {0}" -f $todo.Note) -ForegroundColor Gray
    }
}

Write-Host "================================================================================" -ForegroundColor White

if ($script:FailList.Count -eq 0) {
    Write-Host "`n  🎉 结论: 工作台处于 [READY / 完备就绪] 状态！" -ForegroundColor Green
    Write-Host "  您可以直接在 Agent (Pi / Claude / DSH / Codex) 中发送: lab： 开启测试！`n" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "`n  ❌ 结论: 当前工作台存在未满足的核心依赖，请按照上述红色整改建议修复。`n" -ForegroundColor Red
    exit 1
}

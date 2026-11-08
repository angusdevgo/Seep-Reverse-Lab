#Requires -Version 5.1
<#
  Seep 逆向工程工作台 —— 部署完备性体检与校验仪表盘 (System Health & Integrity Verifier)
  支持独立运行、双击运行、或由 Agent 调用以验证工作台是否完整就绪。
  支持 -Detailed / -Audit 参数输出基于 MANUAL/DEPLOYMENT-CHECKLIST.md 的结构化双向校对看板。
#>
[CmdletBinding()]
param(
    [Alias("Audit")]
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
$ManualDir = Join-Path $Root 'MANUAL'
$localSkills = Join-Path $ToolDir 'skill'

$script:OkCount = 0
$script:FailList = @()
$script:TodoList = @()

# 结构化校对明细表（供 Detailed 模式使用）
$script:AuditTable = [System.Collections.ArrayList]::new()

# 解析一个「真的能执行」的 Python 解释器。
# 为什么不直接用 `python`：Windows 上 `python` 可能是
#   · Microsoft Store 的占位别名（执行即弹商店，退出码非 0）
#   · 指向已删除 venv 的 .cmd 垫片（例如 ~/.pi/agent/bin/python.cmd）
#   · 某个没装 mcp 的发行版解释器
# 直接调用会让体检把「解释器不可用」误报成「功能损坏」，所以先探测再使用。
function Resolve-VerifyPython {
    $cands = @()
    if ($env:SEEP_PYTHON) { $cands += $env:SEEP_PYTHON }
    foreach ($v in @(
            (Join-Path $AgentDir 'seep-venv\Scripts\python.exe'),
            (Join-Path $AgentDir 'seep-venv/bin/python')
        )) {
        if (Test-Path -LiteralPath $v) { $cands += $v }
    }
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath) { $cands += $onPath.Source }
    foreach ($p in @(
            'C:\Program Files\Python312\python.exe',
            'C:\Program Files\Python311\python.exe',
            'C:\Program Files\Python310\python.exe'
        )) {
        if (Test-Path -LiteralPath $p) { $cands += $p }
    }
    foreach ($x in ($cands | Select-Object -Unique)) {
        if ([string]::IsNullOrWhiteSpace($x)) { continue }
        if (-not (Test-Path -LiteralPath $x)) { continue }
        try {
            & $x -c "import sys" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $x }
        }
        catch { }
    }
    return $null
}

function Test-CheckItem {
    param(
        [string]$Category,
        [string]$ItemName,
        [scriptblock]$Predicate,
        [string]$Remedy,
        [string]$Expected = "存在且完整",
        [string]$TargetLocation = ""
    )
    $actualStr = ""
    try {
        $passed = & $Predicate
        if ($passed) {
            Write-Host ("  [√ PASS] {0}" -f $ItemName) -ForegroundColor Green
            $script:OkCount++
            $script:AuditTable.Add([PSCustomObject]@{
                Category = $Category
                Name = $ItemName
                Target = $TargetLocation
                Expected = $Expected
                Actual = "通过"
                Status = "🟢 READY"
                Note = "完备就绪"
            }) | Out-Null
        } else {
            Write-Host ("  [X FAIL] {0}" -f $ItemName) -ForegroundColor Red
            $script:FailList += @{ Category = $Category; Name = $ItemName; Fix = $Remedy }
            $script:AuditTable.Add([PSCustomObject]@{
                Category = $Category
                Name = $ItemName
                Target = $TargetLocation
                Expected = $Expected
                Actual = "缺失/异常"
                Status = "🔴 MISSING"
                Note = $Remedy
            }) | Out-Null
        }
    } catch {
        Write-Host ("  [X FAIL] {0} (异常: {1})" -f $ItemName, $_.Exception.Message) -ForegroundColor Red
        $script:FailList += @{ Category = $Category; Name = $ItemName; Fix = $Remedy }
        $script:AuditTable.Add([PSCustomObject]@{
            Category = $Category
            Name = $ItemName
            Target = $TargetLocation
            Expected = $Expected
            Actual = "异常: $($_.Exception.Message)"
            Status = "🔴 MISSING"
            Note = $Remedy
        }) | Out-Null
    }
}

function Test-ManualItem {
    param(
        [string]$Category,
        [string]$ItemName,
        [scriptblock]$Predicate,
        [string]$Guidance,
        [string]$Expected = "可选扩展",
        [string]$TargetLocation = ""
    )
    try {
        $passed = & $Predicate
        if ($passed) {
            Write-Host ("  [√ PASS] {0}" -f $ItemName) -ForegroundColor Green
            $script:OkCount++
            $script:AuditTable.Add([PSCustomObject]@{
                Category = $Category
                Name = $ItemName
                Target = $TargetLocation
                Expected = $Expected
                Actual = "已配置/已连接"
                Status = "🟢 READY"
                Note = "功能正常"
            }) | Out-Null
        } else {
            Write-Host ("  [! OPTN] {0} ({1})" -f $ItemName, $Guidance) -ForegroundColor Yellow
            $script:TodoList += @{ Category = $Category; Name = $ItemName; Note = $Guidance }
            $script:AuditTable.Add([PSCustomObject]@{
                Category = $Category
                Name = $ItemName
                Target = $TargetLocation
                Expected = $Expected
                Actual = "未配置 (自动降级)"
                Status = "🟡 DEGRADED"
                Note = $Guidance
            }) | Out-Null
        }
    } catch {
        Write-Host ("  [! OPTN] {0} ({1})" -f $ItemName, $Guidance) -ForegroundColor Yellow
        $script:TodoList += @{ Category = $Category; Name = $ItemName; Note = $Guidance }
        $script:AuditTable.Add([PSCustomObject]@{
            Category = $Category
            Name = $ItemName
            Target = $TargetLocation
            Expected = $Expected
            Actual = "未配置 (自动降级)"
            Status = "🟡 DEGRADED"
            Note = $Guidance
        }) | Out-Null
    }
}

Write-Host @"
================================================================================
          Seep Reverse Lab — 工作台部署完备性校验与健康体检 (Verifier)
================================================================================
  工作台物理根目录: $Root
  宿主操作系统环境: Windows $([Environment]::OSVersion.Version.ToString()) ($([IntPtr]::Size * 8)-bit)
  校对基准手册: MANUAL/DEPLOYMENT-CHECKLIST.md
"@ -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# 1. 核心目录与包结构
# -----------------------------------------------------------------------------
Write-Host "`n[1/10] 📁 核心架构与工程目录树" -ForegroundColor White
Test-CheckItem "架构" "工作台主目录完整 (Tool/)" { Test-Path $ToolDir } "请检查是否完整解压或下载了 Seep 完整仓库" "Tool/ 存在" "$Root\Tool"
Test-CheckItem "架构" "技能包目录完整 (Tool/skill/)" { Test-Path (Join-Path $ToolDir 'skill') } "检查 Tool/skill 是否存在" "Tool/skill 存在" "$ToolDir\skill"
Test-CheckItem "架构" "MCP服务引擎目录 (Tool/mcp/)" { Test-Path (Join-Path $ToolDir 'mcp') } "检查 Tool/mcp 是否存在" "Tool/mcp 存在" "$ToolDir\mcp"
Test-CheckItem "架构" "系统提示词层 (Tool/prompts/)" { Test-Path (Join-Path $ToolDir 'prompts') } "检查 Tool/prompts 是否存在" "Tool/prompts 存在" "$ToolDir\prompts"
Test-CheckItem "架构" "十四大脱敏案例工程 (Tool/cases/)" { 
    $cases = Join-Path $ToolDir 'cases'
    (Test-Path $cases) -and ((Get-ChildItem $cases -Directory).Count -ge 14)
} "检查 14 个项目案例目录是否存在" "≥14 个项目工程" "$ToolDir\cases"
Test-CheckItem "架构" "上游开源验证集 (Tool/upstream/ 3大开源项目)" { 
    (Test-Path (Join-Path $ToolDir 'upstream\apk-reverse')) -and
    (Test-Path (Join-Path $ToolDir 'upstream\open-tgtylab')) -and
    (Test-Path (Join-Path $ToolDir 'upstream\open-reverselab'))
} "检查 apk-reverse, open-tgtylab, open-reverselab 上游工程目录是否完备" "3 大完整上游" "$ToolDir\upstream"
Test-CheckItem "架构" "MCP专用运行时强约定 (Tool/mcp/Tool/)" { Test-Path (Join-Path $ToolDir 'mcp\Tool') } "严禁重命名或搬移 Tool/mcp/Tool 目录" "运行时目录存在" "$ToolDir\mcp\Tool"

# -----------------------------------------------------------------------------
# 1b. 版本与更新链路
# -----------------------------------------------------------------------------
Test-CheckItem "版本" "版本标识与变更日志 (VERSION + CHANGELOG.md)" {
    (Test-Path (Join-Path $Root 'VERSION')) -and (Test-Path (Join-Path $Root 'CHANGELOG.md'))
} "缺失 VERSION 或 CHANGELOG.md，重新拉取仓库" "两者在位" "$Root\VERSION"

Test-CheckItem "版本" "已有用户一键更新脚本 (update.ps1 + update.sh)" {
    (Test-Path (Join-Path $Root 'setup\update.ps1')) -and (Test-Path (Join-Path $Root 'setup\update.sh'))
} "更新脚本缺失，重新拉取仓库" "两个脚本在位" "$Root\setup"

Test-CheckItem "架构" "上游定点防外溢规则与同步引擎 (upstream-rules.json + sync-upstream.py)" {
    (Test-Path (Join-Path $Root 'setup\upstream-rules.json')) -and
    (Test-Path (Join-Path $Root 'setup\sync-upstream.py')) -and
    (Test-Path (Join-Path $Root 'setup\sync-upstream.ps1')) -and
    (Test-Path (Join-Path $Root 'update.bat'))
} "上游规则或同步引擎缺失，请重新拉取仓库" "规则清单、引擎与批处理在位" "$Root\setup\upstream-rules.json"

Test-CheckItem "版本" "一键卸载脚本 (uninstall.ps1 + uninstall.sh)" {
    (Test-Path (Join-Path $Root 'setup\uninstall.ps1')) -and (Test-Path (Join-Path $Root 'setup\uninstall.sh'))
} "卸载脚本缺失，重新拉取仓库" "两个脚本在位" "$Root\setup"

# -----------------------------------------------------------------------------
# 2. 知识库与战术资产
# -----------------------------------------------------------------------------
Write-Host "`n[2/10] 📚 攻防实战知识库与战术模板 (KB)" -ForegroundColor White
Test-CheckItem "知识库" "战术实战笔记 (289篇完整检索库)" {
    (Test-Path $KbDir) -and ((Get-ChildItem $KbDir -Recurse -Filter '*.md').Count -ge 280)
} "Tool/mcp/Tool/reverselab/kb/ 文件缺失，请确认完整拉取" "≥289 篇笔记" "$KbDir"
Test-CheckItem "知识库" "内置 MCP 源码组件 (ReverseLab/Ghidra/JSHook)" {
    $m = Join-Path $Root 'Tool\mcp\Tool\reverselab\tools\skills\mcp'
    (Test-Path $m) -and ((Get-ChildItem $m -Directory).Count -ge 3)
} "reverselab 内置 MCP 源码组件缺失" "3 组 MCP 源码" "$Root\Tool\mcp\Tool\reverselab\tools\skills\mcp"

# -----------------------------------------------------------------------------
# 3. 智能体提示词与多平台适配
# -----------------------------------------------------------------------------
Write-Host "`n[3/10] 🧠 智能体指令系统与运行时拦截扩展 (Prompts & Extensions)" -ForegroundColor White
Test-CheckItem "提示词" "Pi Agent 系统指令 (SYSTEM.md 已就绪且去个人化)" {
    $p = Join-Path $ToolDir 'prompts\SYSTEM.md'
    (Test-Path $p) -and (-not (Select-String -Path $p -Pattern '小π|主人' -Quiet))
} "Tool/prompts/SYSTEM.md 不存在或包含未脱敏字符" "无脱敏漏洞" "$ToolDir\prompts\SYSTEM.md"
Test-CheckItem "提示词" "通用跨 Agent 规范 (AGENTS.md)" { Test-Path (Join-Path $ToolDir 'prompts\AGENTS.md') } "检查 AGENTS.md" "规范文件存在" "$ToolDir\prompts\AGENTS.md"
Test-CheckItem "提示词" "Claude Code 项目级规范 (CLAUDE.md 在项目根)" { Test-Path (Join-Path $Root 'CLAUDE.md') } "项目根缺失 CLAUDE.md" "CLAUDE.md 在根目录" "$Root\CLAUDE.md"
Test-CheckItem "提示词" "DeepSeek Harness 配置文件 (DSH-PROFILE.md)" { Test-Path (Join-Path $Root 'DSH-PROFILE.md') } "缺失 DSH-PROFILE.md" "DSH-PROFILE.md 在根目录" "$Root\DSH-PROFILE.md"
Test-CheckItem "扩展"   "底层安全放行与 Lab 状态机扩展 (.ts)" {
    Test-Path (Join-Path $ToolDir 'prompts\extensions\security-audit-interceptor.ts')
} "安全拦截扩展缺失，无法实现 lab: 状态机与防拒功能" "扩展文件在位" "$ToolDir\prompts\extensions\security-audit-interceptor.ts"

# -----------------------------------------------------------------------------
# 4. 技能系统完备性 (Skills System)
# -----------------------------------------------------------------------------
$skillDirs = @(Get-ChildItem -Path (Join-Path $ToolDir 'skill') -Directory -ErrorAction SilentlyContinue)
$skillDirCount = $skillDirs.Count
# safe-skills 是一个聚合目录，内部再含多组技能；按「实际技能数」报数避免误读
$safeSkillCount = 0
$safeDir = Join-Path $ToolDir 'skill\safe-skills'
if (Test-Path $safeDir) { $safeSkillCount = @(Get-ChildItem $safeDir -Directory).Count }
$skillTotal = $skillDirCount - 1 + $safeSkillCount
Write-Host "`n[4/10] 🛠️ 逆向工程专业技能库 (Skills - $skillTotal 个技能 / $skillDirCount 个目录)" -ForegroundColor White
Test-CheckItem "Skill" "核心总控调度器 (softseep 包含 10 大专题库)" {
    $r = Join-Path $localSkills 'softseep\references'
    (Test-Path (Join-Path $localSkills 'softseep\SKILL.md')) -and 
    (Test-Path $r) -and ((Get-ChildItem $r -Filter '*.md').Count -ge 10)
} "softseep 或其 references 目录不完整" "SKILL.md + ≥10 refs" "$localSkills\softseep"

Test-CheckItem "Skill" "移动端逆向全链路 (apkseep 包含 45 篇规范与 56 脚本)" {
    $r = Join-Path $localSkills 'apkseep\references'
    $s = Join-Path $localSkills 'apkseep\scripts'
    (Test-Path (Join-Path $localSkills 'apkseep\SKILL.md')) -and (Test-Path $r) -and (Test-Path $s)
} "apkseep 工程不完整" "SKILL.md + 45 refs + 56 scripts" "$localSkills\apkseep"

Test-CheckItem "Skill" "Windows PE 深水区 (exe-reverse 包含 41 篇规范与 16 脚本)" {
    $r = Join-Path $localSkills 'exe-reverse\references'
    $s = Join-Path $localSkills 'exe-reverse\scripts'
    (Test-Path (Join-Path $localSkills 'exe-reverse\SKILL.md')) -and
    (Test-Path $r) -and (Test-Path $s) -and
    ((Get-ChildItem $r -Recurse -Filter '*.md').Count -ge 41) -and
    ((Get-ChildItem $s -File).Count -ge 16)
} "exe-reverse 工程不完整，请重跑 setup\install-pi.ps1" "SKILL.md + 41 refs + 16 scripts" "$localSkills\exe-reverse"

Test-CheckItem "Skill" "IDA Pro 自动化联动 (ida-reverse)" {
    Test-Path (Join-Path $localSkills 'ida-reverse\SKILL.md')
} "ida-reverse 技能缺失" "SKILL.md 在位" "$localSkills\ida-reverse"

Test-CheckItem "Skill" "通用许可/卡密校验突破规范 (license-bypass)" {
    Test-Path (Join-Path $localSkills 'client-license-validation-bypass\SKILL.md')
} "client-license-validation-bypass 技能缺失" "SKILL.md 在位" "$localSkills\client-license-validation-bypass"

Test-CheckItem "Skill" "Web / 流媒体取证 (webseep 包含 SKILL.md + 3 refs + 模板)" {
    $r = Join-Path $localSkills 'webseep\references'
    (Test-Path (Join-Path $localSkills 'webseep\SKILL.md')) -and
    (Test-Path $r) -and ((Get-ChildItem $r -Filter '*.md').Count -ge 3)
} "webseep 工程不完整，请重跑 setup\install-pi.ps1" "SKILL.md + 3 refs + templates" "$localSkills\webseep"

Test-CheckItem "Skill" "独立战术安全技能包 (safe-skills 5组)" {
    $ss = Join-Path $localSkills 'safe-skills'
    (Test-Path $ss) -and ((Get-ChildItem $ss -Directory).Count -ge 5)
} "safe-skills 目录缺失或不足 5 个技能包" "5 组独立技能包" "$localSkills\safe-skills"

# SKILL.md 带 UTF-8 BOM 时，YAML frontmatter 解析器无法识别首行 `---`，
# 整条技能会被 DSH / Claude Code 等 Agent 静默跳过（参见 GitHub Issue #6）。
Test-CheckItem "Skill" "技能 SKILL.md 无 UTF-8 BOM（否则被 Agent 静默跳过）" {
    $bad = @(Get-ChildItem -Path (Join-Path $ToolDir 'skill') -Recurse -Filter 'SKILL.md' -ErrorAction SilentlyContinue |
        Where-Object {
            $b = [System.IO.File]::ReadAllBytes($_.FullName)
            ($b.Length -ge 3) -and ($b[0] -eq 0xEF) -and ($b[1] -eq 0xBB) -and ($b[2] -eq 0xBF)
        })
    -not $bad
} "存在带 BOM 的 SKILL.md，Agent 会静默跳过该技能；请运行 python setup/clean-format.py 修复" "全部无 BOM" "Tool/skill/**/SKILL.md"

# 如果检测到用户本地的 Pi Agent 目录，则额外校验是否已同步部署到系统
if (Test-Path $AgentDir) {
    Test-ManualItem "部署" "Pi Agent 本地技能同步 (~/.pi/agent/skills/softseep)" {
        Test-Path (Join-Path $AgentDir 'skills\softseep\SKILL.md')
    } "已安装 Pi 但尚未部署，可运行 powershell -File setup\install-pi.ps1 完成同步" "已同步到用户主目录" "$AgentDir\skills\softseep"
}

# -----------------------------------------------------------------------------
# 5. MCP 自动化服务层与底层工具 (MCP & Native Tools)
# -----------------------------------------------------------------------------
Write-Host "`n[5/10] 🔌 MCP 服务引擎与物理内置工具箱 (Native Tools)" -ForegroundColor White

# 只解析一次，后续所有需要跑 Python 的检查点统一复用它
$script:VerifyPython = Resolve-VerifyPython

# 工具数以源码为准动态统计，避免版本迭代后断言过时导致「体检假红」
$seepServerPath = Join-Path $ToolDir 'mcp\seep_mcp_server.py'
$seepToolCount = if (Test-Path $seepServerPath) {
    @(Select-String -Path $seepServerPath -Pattern '^def seep_\w+\(' -AllMatches).Count
} else { 0 }

Test-CheckItem "MCP" "Python 解释器可用于运行时校验 (语法 / 冒烟 / 规则同步)" {
    $null -ne $script:VerifyPython
} "未找到可执行的 Python。若 PATH 上的 python 是商店占位别名或失效垫片，请显式设置 SEEP_PYTHON 或安装 Python 3.11+" "解释器可执行且能 import" "SEEP_PYTHON / ~/.pi/agent/seep-venv"

Test-CheckItem "MCP" "核心服务端脚本 (seep_mcp_server.py 语法自洽)" {
    $sp = Join-Path $ToolDir 'mcp\seep_mcp_server.py'
    if (-not (Test-Path $sp)) { return $false }
    if (-not $script:VerifyPython) { return $true }   # 解释器不可用由上一项单独报，不在这里重复罚
    & $script:VerifyPython -c "import ast; ast.parse(open(r'$sp', encoding='utf-8').read())" 2>&1 | Out-Null
    ($LASTEXITCODE -eq 0)
} "seep_mcp_server.py 丢失或存在 Python 语法解析错误" "$seepToolCount 个原生工具定义" "$ToolDir\mcp\seep_mcp_server.py"

# 语法合法 ≠ 能在 stdio 下工作：subprocess.run 派生点若漏了 stdin=DEVNULL，
# 子进程会继承 MCP 自己的 JSON-RPC 管道，Python 子解释器卡在启动阶段，
# 工具表现为永久挂起直到客户端超时（issue #13）。这一层只有跑到真实调用才暴露，
# 所以用冒烟脚本的 --quick 静态层兜住：零依赖、毫秒级、能直接点出行号。
Test-CheckItem "MCP" "stdio 子进程不继承 stdin (issue #13 回归防护)" {
    $smoke = Join-Path $ToolDir 'mcp\test_stdio_smoke.py'
    if (-not (Test-Path $smoke)) { return $true }   # 旧版本无此脚本时不判定，避免误报
    if (-not $script:VerifyPython) { return $true }  # 解释器不可用由专门项报
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $script:VerifyPython $smoke --quick 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $prevEap
    }
} "subprocess 调用缺少 stdin=DEVNULL，stdio 模式下 seep_pe_* 会挂死（详见 issue #13）" "全部调用点已隔离" "$ToolDir\mcp\test_stdio_smoke.py"

Test-CheckItem "工具箱" "Jadx 反编译引擎 (jadx-1.5.6 完整就绪)" {
    $j = Join-Path $ToolsDir 'jadx\lib\jadx-1.5.6-all.jar'
    $b = Join-Path $ToolsDir 'jadx\bin\jadx.bat'
    (Test-Path $j) -and (Test-Path $b)
} "Jadx 缺失，请运行 powershell -File setup\repair-tools.ps1 -Only jadx 恢复" "jadx.bat + jar" "$ToolsDir\jadx"

Test-CheckItem "工具箱" "Radare2 二进制全套工具 (r2/rabin2/radiff2/rasm2)" {
    $r2 = Join-Path $ToolsDir 'radare2\bin\radare2.exe'
    $rb = Join-Path $ToolsDir 'radare2\bin\rabin2.exe'
    (Test-Path $r2) -and (Test-Path $rb)
} "Radare2 二进制套件缺失，请运行 setup\repair-tools.ps1 -Only radare2 恢复" "全套二进制在位" "$ToolsDir\radare2"

Test-CheckItem "工具箱" "Apktool 资源拆解重构环境 (apktool.jar + bat)" {
    $aj = Join-Path $ToolsDir 'apktool\apktool.jar'
    $ab = Join-Path $ToolsDir 'apktool\apktool.bat'
    (Test-Path $aj) -and (Test-Path $ab)
} "Apktool 环境缺失，请运行 setup\repair-tools.ps1 -Only apktool 恢复" "apktool.jar + bat" "$ToolsDir\apktool"

Test-CheckItem "工具箱" "Frida/LSPosed 动态插桩模板库 (hook-mcp)" {
    Test-Path (Join-Path $ToolsDir 'hook-mcp\templates')
} "hook-mcp 模板目录缺失" "templates 目录在位" "$ToolsDir\hook-mcp\templates"

# 检查依赖包是否已经解压 (首次部署解压检查)
Test-CheckItem "依赖" "Web/JS 逆向调试引擎依赖已解压 (js-reverse-mcp/node_modules)" {
    (Test-Path (Join-Path $ToolsDir 'js-reverse-mcp\node_modules')) -or 
    (Test-Path (Join-Path $ToolsDir 'js-reverse-mcp\node_modules.zip'))
} "未找到 js-reverse-mcp 依赖或压缩包" "node_modules 已就绪" "$ToolsDir\js-reverse-mcp"

Test-CheckItem "依赖" "Playwright 浏览器自动化依赖已解压 (playwright-mcp/node_modules)" {
    (Test-Path (Join-Path $ToolsDir 'playwright-mcp\node_modules')) -or 
    (Test-Path (Join-Path $ToolsDir 'playwright-mcp\node_modules.zip'))
} "未找到 playwright-mcp 依赖或压缩包" "node_modules 已就绪" "$ToolsDir\playwright-mcp"

# -----------------------------------------------------------------------------
# 6. 环境运行时与第三方依赖配置
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 5b. 外部能力包可用性（不只看文件在不在，而是这个工具现在能不能真跑）
#     这些程序不在仓库里（体积 / 平台 / 版本耦合），所以缺失不阻塞部署：
#     用 Test-ManualItem 归入「可选/建议关注」，判为 🟡 DEGRADED 而不是 🔴 MISSING。
# -----------------------------------------------------------------------------
Write-Host "`n[6/10] 🧰 外部能力包可用性 (Web / Android / 扫描器)" -ForegroundColor White

$capWebLib = Join-Path $Root 'Tool\scripts\lib\WebToolbox.ps1'
$capAndLib = Join-Path $Root 'Tool\scripts\lib\AndroidToolbox.ps1'
if (Test-Path $capWebLib) { . $capWebLib }
if (Test-Path $capAndLib) { . $capAndLib }

$capGroups = @(
    @{ Name = 'Web 取证';        Tools = @('ffmpeg', 'ffprobe'); Purpose = 'HLS 六类根因判定（防盗链 / AES-128 / DRM）'; Fix = 'setup\install-capabilities.ps1 -Only web' },
    @{ Name = 'Flutter AOT';     Tools = @('aotopsy');           Purpose = 'Dart AOT (libapp.so) 静态分析与符号还原';   Fix = 'setup\install-capabilities.ps1 -Only aotopsy' },
    @{ Name = 'Android 动态';    Tools = @('frida', 'objection'); Purpose = '动态插桩 / SSL Pinning 绕过 / 内存脱壳';   Fix = 'setup\install-capabilities.ps1 -Only android' },
    @{ Name = '加固指纹';        Tools = @('apkid');             Purpose = 'APKiD 查壳 / 反调试 / 混淆器识别';          Fix = 'setup\install-capabilities.ps1 -Only android' },
    @{ Name = '扫描器（可选）';  Tools = @('nuclei', 'ffuf');    Purpose = '模板化漏扫与目录爆破';                      Fix = 'setup\install-capabilities.ps1 -Only scanners' }
)

foreach ($g in $capGroups) {
    $found = @()
    $lost  = @()
    foreach ($t in $g.Tools) {
        $p = $null
        if (Get-Command Resolve-AndroidTool -ErrorAction SilentlyContinue) { $p = Resolve-AndroidTool -Name $t }
        if (-not $p -and (Get-Command Resolve-WebTool -ErrorAction SilentlyContinue)) { $p = Resolve-WebTool -Name $t }
        if ($p) { $found += $t } else { $lost += $t }
    }
    $itemName = "{0} ({1})" -f $g.Name, ($g.Tools -join ' + ')
    $expected = "可执行文件在 PATH 或工具箱内"
    Test-ManualItem "能力" $itemName {
        ($lost.Count -eq 0)
    } ("缺 {0}；补全: powershell -File {1}" -f ($lost -join ', '), $g.Fix) $expected ""
}


Write-Host "`n[7/10] ⚙️ 外部运行时与商业授权协同 (Runtime & Commercial)" -ForegroundColor White

Test-CheckItem "运行时" "Python 解释器 (3.11+ 且可执行)" {
    $null -ne $script:VerifyPython
} "系统未安装 Python 或未加入 PATH 环境变量，请安装 Python 3.11+（或用 SEEP_PYTHON 指定）" "Python 3.11+" "PATH / SEEP_PYTHON"

Test-ManualItem "协议" "Python mcp 协议库环境支持 (mcp>=1.20,<1.29)" {
    if (-not $script:VerifyPython) { return $false }
    & $script:VerifyPython -c "import mcp" 2>&1 | Out-Null
    ($LASTEXITCODE -eq 0)
} "运行 pip install ""mcp>=1.20,<1.29"" 补齐协议支持" "mcp 库已安装" "Python site-packages"

Test-ManualItem "商业软件" "IDA Pro 商业反编译器协同 (需自备独立授权)" {
    $found = $false
    foreach ($c in @('D:\Tool\IDA Pro', 'C:\Program Files\IDA Pro', 'C:\Program Files\IDA Professional 9.0', 'C:\IDA Pro')) {
        if (Test-Path (Join-Path $c 'ida.exe')) { $found = $true; break }
    }
    $found
} "未检测到本地 IDA Pro，如无授权不影响核心链路，系统自动降级使用 Radare2（详见 MANUAL\IDA-PRO.md）" "商业授权可选" "本地安装目录"

Test-ManualItem "配置" "Claude Code 项目级 MCP 注册 (.mcp.json 在根目录)" {
    Test-Path (Join-Path $Root '.mcp.json')
} "根目录已备好 .mcp.json，在根目录直接执行 claude 即可免配加载" ".mcp.json 存在" "$Root\.mcp.json"

# -----------------------------------------------------------------------------
# 7. MANUAL/ 战术手册完备性校验 (Tactical Manuals)
# -----------------------------------------------------------------------------
Write-Host "`n[8/10] 📚 MANUAL/ 战术手册完备性校验" -ForegroundColor White

Test-CheckItem "手册" "环境预要求指南 (MANUAL/PREREQUISITES.md)" {
    Test-Path (Join-Path $ManualDir 'PREREQUISITES.md')
} "安装指南缺失，重新拉取仓库" "文件在位" "$ManualDir\PREREQUISITES.md"

Test-CheckItem "手册" "IDA Pro 商业软件接入指南 (MANUAL/IDA-PRO.md)" {
    Test-Path (Join-Path $ManualDir 'IDA-PRO.md')
} "IDA-PRO 指南缺失" "文件在位" "$ManualDir\IDA-PRO.md"

Test-CheckItem "手册" "反调试绕过战术手册 (MANUAL/ANTI-DEBUG.md)" {
    Test-Path (Join-Path $ManualDir 'ANTI-DEBUG.md')
} "调试应对手册缺失，重新拉取仓库" "文件在位" "$ManualDir\ANTI-DEBUG.md"

Test-CheckItem "手册" "通用脱壳前置分析 SOP (MANUAL/UNPACKING.md)" {
    Test-Path (Join-Path $ManualDir 'UNPACKING.md')
} "脱壳手册缺失，重新拉取仓库" "文件在位" "$ManualDir\UNPACKING.md"

Test-CheckItem "手册" "PoC 闭环自动化验证 SOP (MANUAL/POC-VALIDATION.md)" {
    Test-Path (Join-Path $ManualDir 'POC-VALIDATION.md')
} "PoC 验证手册缺失，重新拉取仓库" "文件在位" "$ManualDir\POC-VALIDATION.md"

Test-CheckItem "手册" "全景部署与多 Agent 集成指南 (MANUAL/DEPLOYMENT.md)" {
    Test-Path (Join-Path $ManualDir 'DEPLOYMENT.md')
} "部署手册缺失，重新拉取仓库" "文件在位" "$ManualDir\DEPLOYMENT.md"

Test-CheckItem "手册" "官方部署资产核验基准清单 (MANUAL/DEPLOYMENT-CHECKLIST.md)" {
    Test-Path (Join-Path $ManualDir 'DEPLOYMENT-CHECKLIST.md')
} "核验清单缺失，重新拉取仓库" "SSOT 清单在位" "$ManualDir\DEPLOYMENT-CHECKLIST.md"

Test-CheckItem "手册" "跨平台运行与战术等价指南 (MANUAL/CROSS-PLATFORM.md)" {
    Test-Path (Join-Path $ManualDir 'CROSS-PLATFORM.md')
} "跨平台手册缺失，重新拉取仓库" "文件在位" "$ManualDir\CROSS-PLATFORM.md"

Test-CheckItem "手册" "合规转译中继与防拒体系 (MANUAL/COMPLIANCE-RELAY.md)" {
    Test-Path (Join-Path $ManualDir 'COMPLIANCE-RELAY.md')
} "合规中继手册缺失，重新拉取仓库" "文件在位" "$ManualDir\COMPLIANCE-RELAY.md"

# -----------------------------------------------------------------------------
# 8. 合规转译中继（网络层防拒）
# -----------------------------------------------------------------------------
Write-Host "`n[9/10] 🌐 合规转译中继与规则同步校验" -ForegroundColor White
$RelayDir = Join-Path $ToolDir 'scripts\compliance-relay'

Test-CheckItem "中继" "中继主程序 (relay.py 纯标准库实现)" {
    Test-Path (Join-Path $RelayDir 'relay.py')
} "relay.py 缺失，重新拉取仓库" "relay.py 在位" "$RelayDir\relay.py"

Test-CheckItem "中继" "规则提取器 (extract-rules.py)" {
    Test-Path (Join-Path $RelayDir 'extract-rules.py')
} "extract-rules.py 缺失，重新拉取仓库" "提取器在位" "$RelayDir\extract-rules.py"

Test-CheckItem "中继" "上下文守卫白名单 (guard-prefixes.json)" {
    Test-Path (Join-Path $RelayDir 'guard-prefixes.json')
} "guard-prefixes.json 缺失，重新拉取仓库" "白名单在位" "$RelayDir\guard-prefixes.json"

Test-CheckItem "中继" "规则表与 TS 源同步 (sensitive-rules.json)" {
    $rules = Join-Path $RelayDir 'sensitive-rules.json'
    if (-not (Test-Path $rules)) { return $false }
    if (-not $script:VerifyPython) { return (Test-Path $rules) }
    Push-Location $RelayDir
    try {
        & $script:VerifyPython extract-rules.py --check 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    } finally { Pop-Location }
} "规则表与 TS 源不一致，请运行 python Tool/scripts/compliance-relay/extract-rules.py" "与 TS 源同步" "$RelayDir\sensitive-rules.json"

Test-CheckItem "中继" "中继单元测试套件 (tests/test_relay.py)" {
    Test-Path (Join-Path $RelayDir 'tests\test_relay.py')
} "测试套件缺失，重新拉取仓库" "测试套件在位" "$RelayDir\tests\test_relay.py"

# -----------------------------------------------------------------------------
# 9. 脱敏与隐私走查（递归全深度）
# -----------------------------------------------------------------------------
Write-Host "`n[10/10] 🔒 脱敏与个人隐私走查 (递归全深度扫描)" -ForegroundColor White

# 个人隐私模式：绝对路径 / 个人身份 / 私有邮箱 / 私有域名 / 裸用户名
$PrivacyPattern = 'C:[\\/]{1,2}Users[\\/]{1,2}Angus|AngusDevLab|angusdevlab|angus\.vip@|angusdev\.top|\bAngus\b'

# 排除：第三方依赖、上游镜像、构建产物，以及扫描器自身（其模式定义会自匹配）
$PrivacyExcludeRegex = '\\node_modules\\|\\__pycache__\\|\\Tool\\upstream\\|\\Tool\\mcp\\Tool\\|\\\.git\\|\\dist\\'
# 安装时由脚本生成的本地配置：内含本机绝对路径属正常现象，且已被 .gitignore 排除。
# 非 git（压缩包）部署时它们会留在磁盘上，必须一并排除，否则每次体检都误报。
$PrivacyExcludeNames = @(
    'verify.ps1', 'verify.sh',
    'opencode.jsonc', 'cordis.generated.yml', 'relay-config.json',
    'tool-index.json', 'tool-index.md'
)
$BinaryExt = @('.exe','.dll','.so','.dylib','.jar','.zip','.7z','.png','.jpg','.jpeg','.gif','.ico','.pdf','.bin','.dmp','.pyc','.idb','.i64','.ttf','.woff','.woff2')

Test-CheckItem "脱敏" "个人隐私零残留 (已跟踪文件全深度扫描)" {
    $PrivacyPathExclude = '^(setup/verify\.(ps1|sh))$|^Tool/(upstream|mcp/Tool)/'
    $PrivacyExtExclude = '\.(exe|dll|so|dylib|jar|zip|7z|png|jpg|jpeg|gif|ico|pdf|bin|dmp|pyc|idb|i64|ttf|woff|woff2)$'

    if (Test-Path (Join-Path $Root '.git')) {
        # 只扫描将被发布的 git 跟踪文件（本地生成物已 gitignore，不属发布范围）
        $tracked = & git -C $Root -c core.quotepath=false ls-files 2>$null
        if (-not $tracked) { return $true }
        $files = @($tracked |
            Where-Object { $_ -notmatch $PrivacyPathExclude -and $_ -notmatch $PrivacyExtExclude } |
            ForEach-Object { Join-Path $Root ($_ -replace '/', '\') } |
            Where-Object { Test-Path -LiteralPath $_ })
        if ($files.Count -eq 0) { return $true }
        $hits = Select-String -Path $files -Pattern $PrivacyPattern -CaseSensitive -ErrorAction SilentlyContinue
        return (-not $hits)
    }

    # 非 git 环境：回退到文件系统扫描（排除依赖与构建产物）
    $hits = Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -notmatch $PrivacyExcludeRegex -and
                $PrivacyExcludeNames -notcontains $_.Name -and
                $BinaryExt -notcontains $_.Extension.ToLower()
            } |
            Select-String -Pattern $PrivacyPattern -CaseSensitive -ErrorAction SilentlyContinue
    -not $hits
} "发现个人隐私残留，请立即脱敏后重新提交" "零残留" "$(if (Test-Path (Join-Path $Root '.git')) { 'git 已跟踪文件（排除第三方依赖与上游镜像）' } else { '工作树（排除依赖、上游镜像与安装生成的本地配置）' })"

Test-CheckItem "脱敏" "含本机路径的生成物未被 git 追踪" {
    if (-not (Test-Path (Join-Path $Root '.git'))) { return $true }
    $tracked = & git -C $Root ls-files 2>$null
    $mustIgnore = @('opencode.jsonc', 'setup/cordis.generated.yml', 'Tool/scripts/compliance-relay/relay-config.json')
    foreach ($f in $mustIgnore) {
        if ($tracked -contains $f) { return $false }
    }
    $true
} "生成物含本机绝对路径或访问令牌，不应入库；请从索引移除并确认 .gitignore" "未被追踪" "git index"

Test-ManualItem "脱敏" "目标产品名残留统计 (功能性标识符可保留)" {
    $cases = Join-Path $ToolDir 'cases'
    if (-not (Test-Path $cases)) { return $true }
    $names = 'xyplorer|bandizip|boosterx|1218\.io'
    $hits = Get-ChildItem -Path $cases -Recurse -File -ErrorAction SilentlyContinue |
            Select-String -Pattern $names -ErrorAction SilentlyContinue
    -not $hits
} "存在目标产品名（含 README 已声明的功能性必需标识符，如注册表路径 / API 域名 / 代码符号）；如为叙述性提及请脱敏" "零残留" "$cases"

# -----------------------------------------------------------------------------
# 详细校对模式输出 (-Detailed / -Audit)
# -----------------------------------------------------------------------------
if ($Detailed) {
    Write-Host "`n================================================================================" -ForegroundColor Cyan
    Write-Host "       📊 官方基准核对报表 (Detailed Baseline vs Actual Alignment Table)" -ForegroundColor Cyan
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host ("{0,-8} | {1,-35} | {2,-15} | {3,-15} | {4}" -f "类别", "资产/组件名称", "官方期望值", "实测状态", "说明与降级指引") -ForegroundColor White
    Write-Host ("-" * 105) -ForegroundColor Gray
    foreach ($row in $script:AuditTable) {
        $color = switch ($row.Status) {
            "🟢 READY" { [ConsoleColor]::Green }
            "🟡 DEGRADED" { [ConsoleColor]::Yellow }
            "🔴 MISSING" { [ConsoleColor]::Red }
            default { [ConsoleColor]::White }
        }
        $line = "{0,-8} | {1,-35} | {2,-15} | {3,-15} | {4}" -f $row.Category, $row.Name, $row.Expected, $row.Status, $row.Note
        Write-Host $line -ForegroundColor $color
    }
    Write-Host ("-" * 105) -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# 汇总仪表盘
# -----------------------------------------------------------------------------
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
    Write-Host "  基准清单对照完成，核心资产全部对齐。" -ForegroundColor Green
    Write-Host "  您可以直接在 Agent (Pi / Claude / DSH / Codex) 中发送: lab： 开启测试！`n" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "`n  ❌ 结论: 当前工作台存在未满足的核心依赖，请按照上述红色整改建议修复。`n" -ForegroundColor Red
    exit 1
}

#Requires -Version 5.1
<#
  Seep 工作台 —— 装完自检
  输出 READY 或列出待手工项
#>
[CmdletBinding()]
param()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$ToolDir   = Join-Path $Root 'Tool'
$ToolsDir  = Join-Path $Root 'Tool\mcp\Tool\safe'     # seep MCP 硬编码要求
$KbDir     = Join-Path $Root 'Tool\mcp\Tool\reverselab\kb'
$AgentDir  = Join-Path $env:USERPROFILE '.pi\agent'

$script:Ok = 0
$script:Bad = @()
$script:Manual = @()

function Check($name, [scriptblock]$test, [string]$fix) {
    try {
        $r = & $test
        if ($r) { Write-Host ("  [OK]   {0}" -f $name) -ForegroundColor Green; $script:Ok++ }
        else    { Write-Host ("  [FAIL] {0}" -f $name) -ForegroundColor Red;    $script:Bad += "$name  -> $fix" }
    } catch {
        Write-Host ("  [FAIL] {0}  ({1})" -f $name, $_.Exception.Message) -ForegroundColor Red
        $script:Bad += "$name  -> $fix"
    }
}

function CheckManual($name, [scriptblock]$test, [string]$note) {
    try {
        if (& $test) { Write-Host ("  [OK]   {0}" -f $name) -ForegroundColor Green; $script:Ok++ }
        else { Write-Host ("  [TODO] {0}  ({1})" -f $name, $note) -ForegroundColor Yellow; $script:Manual += "$name  -> $note" }
    } catch {
        Write-Host ("  [TODO] {0}  ({1})" -f $name, $note) -ForegroundColor Yellow
        $script:Manual += "$name  -> $note"
    }
}

Write-Host @"
================================================================
  Seep 工作台 — 自检
================================================================
  根目录: $Root
"@ -ForegroundColor White

# ---------------------------------------------------------------- 结构
Write-Host "`n  ---- 目录结构 ----" -ForegroundColor Cyan
Check 'Tool/ 存在'         { Test-Path $ToolDir }                               '检查包是否完整解压'
Check 'Tool/skill/ 存在'   { Test-Path (Join-Path $ToolDir 'skill') }             '重新解压'
Check 'Tool/mcp/ 存在'     { Test-Path (Join-Path $ToolDir 'mcp') }               '重新解压'
Check 'Tool/prompts/ 存在' { Test-Path (Join-Path $ToolDir 'prompts') }           '重新解压'
Check 'Tool/cases/ 存在'   { Test-Path (Join-Path $ToolDir 'cases') }             '重新解压'
Check 'Tool/docs/ 存在'    { Test-Path (Join-Path $ToolDir 'docs') }              '重新解压'
Check 'Tool/scripts/ 存在' { Test-Path (Join-Path $ToolDir 'scripts') }           '重新解压'
Check 'Tool/upstream/ 存在'{ Test-Path (Join-Path $ToolDir 'upstream') }          '重新解压'
Check 'seep MCP Tool/ 存在'{ Test-Path (Join-Path $ToolDir 'mcp\Tool') }         '重新解压'

# ---------------------------------------------------------------- 知识库
Write-Host "`n  ---- 知识库（seep_kb_* 依赖）----" -ForegroundColor Cyan
Check 'kb/ 有 ≥289 篇文章' {
    (Test-Path $KbDir) -and ((Get-ChildItem $KbDir -Recurse -Filter '*.md').Count -ge 280)
} 'Tool/mcp/Tool/reverselab/kb/ 缺失或不足'

Check 'kb/tools/skills/mcp/ 有 3 个 MCP 源码' {
    $m = Join-Path $Root 'Tool\mcp\Tool\reverselab\tools\skills\mcp'
    (Test-Path $m) -and ((Get-ChildItem $m -Directory).Count -ge 3)
} 'reverselab 的 MCP 源码缺失'

# ---------------------------------------------------------------- Skill
Write-Host "`n  ---- Skill（安装后）----" -ForegroundColor Cyan
foreach ($s in @('softseep', 'apkseep', 'ida-reverse', 'client-license-validation-bypass')) {
    Check "skill: $s" { Test-Path (Join-Path (Join-Path $AgentDir 'skills') $s) } '重跑 install-pi.ps1'
}
Check 'softseep 有 8 个 references' {
    $r = Join-Path $AgentDir 'skills\softseep\references'
    (Test-Path $r) -and ((Get-ChildItem $r -Filter '*.md').Count -ge 8)
} '重跑 install-pi.ps1'

# ---------------------------------------------------------------- 提示词
Write-Host "`n  ---- 提示词与扩展 ----" -ForegroundColor Cyan
Check 'SYSTEM.md'        { Test-Path (Join-Path $AgentDir 'SYSTEM.md') }        '重跑 install-pi.ps1'
Check 'AGENTS.md'        { Test-Path (Join-Path $AgentDir 'AGENTS.md') }        '重跑 install-pi.ps1'
Check '扩展 security-audit-interceptor.ts' {
    Test-Path (Join-Path $AgentDir 'extensions\security-audit-interceptor.ts')
} '重跑 install-pi.ps1'

# ---------------------------------------------------------------- MCP 配置
Write-Host "`n  ---- MCP 配置 ----" -ForegroundColor Cyan
$mcpPath = Join-Path $AgentDir 'mcp.json'
Check 'mcp.json 存在' { Test-Path $mcpPath } '重跑 install-pi.ps1'
if (Test-Path $mcpPath) {
    $raw = Get-Content $mcpPath -Raw -Encoding UTF8
    Check 'mcp.json 无 <SEEP_ROOT> 残留' { $raw -notmatch '<SEEP_ROOT>' } '手工替换占位符'
    CheckManual 'mcp.json 无 <IDA_*> 残留' { $raw -notmatch '<IDA_ROOT>|<IDA_PYTHON>' } '未装 IDA 时正常（见 MANUAL\IDA-PRO.md）'
    CheckManual 'playwright token 已填' { $raw -notmatch '<YOUR_PLAYWRIGHT_TOKEN>' } '不用浏览器自动化可忽略'
    Check 'seep 条目已注册' { $raw -match '"seep"' } '手工添加或重跑 install-pi.ps1'
}

# ---------------------------------------------------------------- 外部工具
Write-Host "`n  ---- 外部工具 ----" -ForegroundColor Cyan
CheckManual 'radare2（seep_r2_* 依赖）' {
    (Test-Path (Join-Path $ToolsDir 'radare2\bin\radare2.exe')) -or (Get-Command r2 -ErrorAction SilentlyContinue)
} '跑 setup\repair-tools.ps1 -Only radare2'

CheckManual 'jadx（seep_apk_decompile 依赖）' {
    (Test-Path (Join-Path $ToolsDir 'jadx\bin\jadx.bat')) -or (Get-Command jadx -ErrorAction SilentlyContinue)
} '跑 setup\repair-tools.ps1 -Only jadx'

CheckManual 'apktool（seep_apk_unpack 依赖）' {
    (Test-Path (Join-Path $ToolsDir 'apktool\apktool.jar')) -or (Get-Command apktool -ErrorAction SilentlyContinue)
} '跑 setup\repair-tools.ps1 -Only apktool'

CheckManual 'IDA Pro（ida MCP 依赖）' {
    $found = $false
    foreach ($c in @('D:\Tool\IDA Pro', 'C:\Program Files\IDA Pro', 'C:\IDA Pro')) {
        if (Test-Path (Join-Path $c 'ida.exe')) { $found = $true; break }
    }
    $found
} '未装则 ida MCP 不可用，用 seep_r2_* 替代（见 MANUAL\IDA-PRO.md）'

# ---------------------------------------------------------------- Python
Write-Host "`n  ---- Python 依赖 ----" -ForegroundColor Cyan
Check 'python 可用' { Get-Command python -ErrorAction SilentlyContinue } '安装 Python 3.11+ 并加入 PATH'
Check 'mcp 库可导入' {
    & python -c "import mcp" 2>&1 | Out-Null
    $LASTEXITCODE -eq 0
} 'pip install "mcp>=1.20,<1.29"'
CheckManual 'pytest 可用' {
    & python -m pytest --version 2>&1 | Out-Null
    $LASTEXITCODE -eq 0
} 'pip install pytest'

# ---------------------------------------------------------------- seep MCP 启动
Write-Host "`n  ---- seep MCP 启动测试 ----" -ForegroundColor Cyan
$seepPy = Join-Path $ToolDir 'mcp\seep_mcp_server.py'
if (Test-Path $seepPy) {
    Check 'seep_mcp_server.py 语法可解析' {
        & python -c "import ast,sys; ast.parse(open(r'$seepPy',encoding='utf-8').read())" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    } '文件损坏，重新解压'
} else {
    Write-Host '  [FAIL] seep_mcp_server.py 不存在' -ForegroundColor Red
    $script:Bad += 'seep_mcp_server.py 缺失 -> 重新解压'
}

# ---------------------------------------------------------------- 脱敏复检
Write-Host "`n  ---- 脱敏复检（案例层）----" -ForegroundColor Cyan
$cases = Join-Path $ToolDir 'cases'
if (Test-Path $cases) {
    Check '案例层无产品名残留' {
        -not (Select-String -Path (Join-Path $cases '*\*') -Pattern 'xyplorer|mumu|bandizip|idman|listary|snipaste|startallback|crystalidea|netease' -Quiet -ErrorAction SilentlyContinue)
    } '包被污染，请重新获取'
}

# ---------------------------------------------------------------- 汇总
Write-Host "`n=================================================================" -ForegroundColor White
Write-Host ("  通过 {0} 项" -f $script:Ok) -ForegroundColor Green
if ($script:Bad.Count -gt 0) {
    Write-Host ("  失败 {0} 项:" -f $script:Bad.Count) -ForegroundColor Red
    $script:Bad | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
if ($script:Manual.Count -gt 0) {
    Write-Host ("  待手工 {0} 项:" -f $script:Manual.Count) -ForegroundColor Yellow
    $script:Manual | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}

if ($script:Bad.Count -eq 0 -and $script:Manual.Count -eq 0) {
    Write-Host "`n  READY" -ForegroundColor Green
    Write-Host "  下一步: 重启 pi -> 输入  lab：" -ForegroundColor Cyan
    exit 0
} elseif ($script:Bad.Count -eq 0) {
    Write-Host "`n  部分就绪（核心可用，待手工项不影响主链路）" -ForegroundColor Yellow
    Write-Host "  下一步: 重启 pi -> 输入  lab：" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "`n  未就绪 —— 请先解决失败项" -ForegroundColor Red
    exit 1
}

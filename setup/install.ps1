#Requires -Version 5.1
<#
  Seep 逆向工程工作台 —— 一键安装总控 (加强交互与无损部署版)
  包含：
    1. 解压离线依赖 (node_modules.zip)
    2. Python 协议依赖安装
    3. Pi Agent / Claude Code / DSH / OpenCode 配置生成
    4. 外部能力包（Web 取证 / Android 工具箱 / 可选扫描器）
    5. 智能 IDA Pro 探测与自定义路径交互引导
    6. 全维度健康核验 + 能力看板
#>
[CmdletBinding()]
param(
    [string]$IdaRoot = '',        # 自定义 IDA Pro 安装目录
    [switch]$SkipPython,          # 跳过 Python 依赖
    [switch]$SkipPi,              # 跳过 pi 环境配置
    [switch]$SkipTools,           # 跳过 IDA Pro 配置
    [switch]$SkipCapabilities,    # 跳过外部能力包（ffmpeg / frida / APKiD / Aotopsy）
    [switch]$WithWeb,             # 顺带装 Web 取证（ffmpeg，约 80 MB 下载）
    [switch]$WithAndroid,         # 顺带装 Android 动态（frida / APKiD，需 pip）
    [switch]$WithScanners,        # 顺带装 nuclei / ffuf
    [switch]$SkipDsh,             # 跳过 DeepSeek Harness 补丁挂载
    [switch]$OnlyVerify,          # 仅跑自检
    [switch]$NonInteractive       # 非交互静默模式
)

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$AgentDir  = Join-Path $env:USERPROFILE '.pi\agent'

$script:Failed = @()

function Write-Step($title) {
    Write-Host "`n>>> $title" -ForegroundColor Cyan
}

function Write-Ok($msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "    [!!] $msg" -ForegroundColor Yellow
}

function Write-Err($msg) {
    Write-Host "    [FAIL] $msg" -ForegroundColor Red
}

function Write-Info($msg) {
    Write-Host "    [..] $msg" -ForegroundColor DarkGray
}

function Test-Environment {
    Write-Step '检测基础运行环境'

    # Python
    # 注意：不能只看 Get-Command 有没有结果。Windows 上 `python` 可能是
    #   · Microsoft Store 的占位别名（执行即弹商店，非零退出）
    #   · 指向已删除 venv 的 .cmd 垫片
    # 这类情况下 `& python --version` 会打印「系统找不到指定的路径」，
    # 但如果不看退出码就会误报 OK，后面所有依赖 Python 的步骤才连环失败。
    $pyCands = @()
    if ($env:SEEP_PYTHON) { $pyCands += $env:SEEP_PYTHON }
    foreach ($v in @(
            (Join-Path $AgentDir 'seep-venv\Scripts\python.exe'),
            (Join-Path $AgentDir 'seep-venv/bin/python')
        )) { if (Test-Path -LiteralPath $v) { $pyCands += $v } }
    $pyOnPath = Get-Command python -ErrorAction SilentlyContinue
    if ($pyOnPath) { $pyCands += $pyOnPath.Source }
    foreach ($c in ($pyCands | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $c)) { continue }
        $ver = (& $c --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $ver -match '^Python \d+\.\d+') {
            Write-Ok "Python 可用: $ver ($c)"
            $env:SEEP_PYTHON = $c
            break
        }
        Write-Warn "跳过不可用的 Python 候选: $c -> $ver"
    }
    if (-not $env:SEEP_PYTHON -or -not (Test-Path -LiteralPath $env:SEEP_PYTHON)) {
        Write-Err '未找到可用的 Python。请安装 Python 3.11+，或用 SEEP_PYTHON 指定解释器路径'
        $script:Failed += 'Python'
    }

    # Node.js
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        $ver = & node --version 2>&1
        Write-Ok "Node.js 可用: $ver"
    } else {
        Write-Warn '未找到 Node.js（可选，用于 JS 逆向与 Playwright 自动化）'
    }

    # Git
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        $ver = & git --version 2>&1
        Write-Ok "Git 可用: $ver"
    } else {
        Write-Warn '未找到 Git'
    }

    # 内置工具检查
    $toolsDir = Join-Path $Root 'Tool\mcp\Tool\safe'
    if (Test-Path $toolsDir) {
        $need = @('Tool\mcp\Tool\safe\radare2\bin\radare2.exe',
                  'Tool\mcp\Tool\safe\jadx\bin\jadx.bat',
                  'Tool\mcp\Tool\safe\apktool\apktool.jar',
                  'Tool\mcp\Tool\reverselab\kb')
        $miss = @()
        foreach ($n in $need) { if (-not (Test-Path (Join-Path $Root $n))) { $miss += $n } }
        if ($miss.Count -eq 0) { Write-Ok '内置离线逆向工具箱完整' }
        else { Write-Warn "内置工具缺失 $($miss.Count) 项（可用 repair-tools.ps1 修复）" }
    }
}

# ---------------------------------------------------------------- 主流程
Write-Host @"
================================================================
  Seep 逆向工程工作台 — 官方部署流水线 (Installer)
================================================================
  工作台物理根目录: $Root
"@ -ForegroundColor White

if ($OnlyVerify) {
    & (Join-Path $ScriptDir 'verify.ps1') -Detailed
    exit $LASTEXITCODE
}

# 首次部署：解压 node_modules（GitHub clone 后只需一次）
if (-not (Test-Path (Join-Path $Root 'Tool\mcp\Tool\safe\js-reverse-mcp\node_modules')) -or
    -not (Test-Path (Join-Path $Root 'Tool\mcp\Tool\safe\playwright-mcp\node_modules'))) {
    Write-Step '解压离线依赖包（首次部署）'
    & (Join-Path $ScriptDir 'extract-deps.ps1')
}

Test-Environment

if ($script:Failed.Count -gt 0) {
    Write-Err "环境检测失败: $($script:Failed -join ', ')"
    Write-Host "`n请先解决上述问题（见 MANUAL\PREREQUISITES.md），然后重新运行。" -ForegroundColor Yellow
    exit 1
}

if (-not $SkipPython) {
    Write-Step '安装 Python 协议依赖'
    & (Join-Path $ScriptDir 'install-python.ps1')
    if ($LASTEXITCODE -ne 0) { $script:Failed += 'python-deps' }
}

if (-not $SkipPi) {
    Write-Step '配置 Pi Agent 环境 (增量合并 mcp.json 与 settings.json)'
    & (Join-Path $ScriptDir 'install-pi.ps1')
    if ($LASTEXITCODE -ne 0) { $script:Failed += 'pi' }
}

# 自动生成 Claude / OpenCode / DSH 配置文件
Write-Step '生成多 Agent 配置文件 (.mcp.json / opencode.jsonc / cordis.generated.yml)'
& (Join-Path $ScriptDir 'generate-configs.ps1')

# -----------------------------------------------------------------------------
# DeepSeek Harness：~/.dsh 存在时才挂载，避免给没装 DSH 的用户制造无关步骤
# -----------------------------------------------------------------------------
if (-not $SkipDsh) {
    $dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
    if (Test-Path $dshHome) {
        Write-Step '挂载 DeepSeek Harness MCP 补丁'
        $dshMerge = Join-Path $ScriptDir 'dsh-merge.py'
        $dshPy = if ($env:SEEP_PYTHON) { $env:SEEP_PYTHON } else { 'python' }
        if (Test-Path $dshMerge) {
            try {
                & $dshPy $dshMerge --root $Root 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
                if ($LASTEXITCODE -eq 0) { Write-Ok 'DSH cordis.patch.yml 已挂载（自定义配置保留）' }
                else { Write-Warn "DSH 挂载返回码 $LASTEXITCODE（不影响其他 Agent）" }
            }
            catch { Write-Warn "DSH 挂载失败：$($_.Exception.Message)（不影响其他 Agent）" }
        }
        else { Write-Warn '缺少 setup\dsh-merge.py，跳过 DSH 挂载' }
    }
    else {
        Write-Info "未检测到 DSH（$dshHome），跳过；装了 DSH 后重跑本脚本即可自动挂载"
    }
}

# -----------------------------------------------------------------------------
# 外部能力包：MCP 有 38 个工具，其中一部分算力来自仓库外的程序
# （ffmpeg / frida / APKiD / Aotopsy / nuclei / ffuf）。这一层以前完全没覆盖，
# 结果就是「工具在 tools/list 里看得见，一调用却返回未部署」。
# 纪律：默认只装零成本件（Aotopsy 从仓库复制，不联网）；需要下载/装包的
#       组件必须显式点名；任何组件失败都只警告，绝不中断部署。
# -----------------------------------------------------------------------------
if (-not $SkipCapabilities) {
    $capScript = Join-Path $ScriptDir 'install-capabilities.ps1'
    if (Test-Path $capScript) {
        $capOnly = @()
        if ($WithWeb)      { $capOnly += 'web' }
        if ($WithAndroid)  { $capOnly += 'android' }
        if ($WithScanners) { $capOnly += 'scanners' }
        if ($capOnly.Count -eq 0) { $capOnly = @('auto') }

        Write-Step "补齐外部能力包（$(($capOnly -join ', '))）"
        try {
            & $capScript -Only $capOnly 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        }
        catch {
            Write-Warn "能力包步骤异常：$($_.Exception.Message)（不影响工作台其余功能）"
        }
        if ($capOnly -contains 'auto') {
            Write-Host '    [..] 提示：ffmpeg / frida / APKiD 需要下载或装包，默认不装。' -ForegroundColor DarkGray
            Write-Host '         一条命令全补：powershell -File setup\install-capabilities.ps1 -Only all' -ForegroundColor DarkGray
        }
    }
    else {
        Write-Warn "未找到 setup\install-capabilities.ps1，跳过能力包步骤"
    }
}

if (-not $SkipTools) {
    Write-Step '配置与探测 IDA Pro（商业软件，需自备授权）'
    $idaParams = @{}
    if ($IdaRoot -ne '') { $idaParams['IdaRoot'] = $IdaRoot }
    if (-not $NonInteractive) { $idaParams['Interactive'] = $true }
    & (Join-Path $ScriptDir 'install-ida.ps1') @idaParams
    # IDA 缺失不算失败（有免费 Radare2 替代路线）
}

Write-Step '执行官方基准完备性自检 (verify.ps1 -Detailed)'
& (Join-Path $ScriptDir 'verify.ps1') -Detailed

# ---------------------------------------------------------------- 总结
Write-Host "`n=================================================================" -ForegroundColor White
if ($script:Failed.Count -eq 0) {
    Write-Host '  🎉 恭喜！Seep 工作台全套组件已部署完成！' -ForegroundColor Green
} else {
    Write-Host "  [!!] 部分非关键步骤失败: $($script:Failed -join ', ')" -ForegroundColor Yellow
}
Write-Host "=================================================================" -ForegroundColor White

Write-Host @"

开工指南:
  1) 重新打开终端启动 Agent (Pi / Claude Code / DSH / OpenCode)
  2) 在对话框中输入:  lab： 即可开启白盒测试！

"@ -ForegroundColor Cyan

exit ($(if ($script:Failed.Count -eq 0) { 0 } else { 1 }))

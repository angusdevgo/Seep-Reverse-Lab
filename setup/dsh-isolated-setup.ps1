#Requires -Version 5.1
<#
  DeepSeek Harness 隔离部署器
  ============================================================================
  在一个**独立文件夹**里部署供 DSH 使用的工作台接入，全程不碰你的 Pi Agent。

  它做什么
    1. 在 <LabDir>\.dsh 建立独立的 DSH_HOME（不动 ~/.dsh）
    2. 让 DSH 自举 web profile（首次会从内置模板生成）
    3. 生成多 Agent 配置（写在工作台仓库内，幂等）
    4. 把 seep 补丁挂载进**隔离的** DSH_HOME
    5. 端到端验证：按 DSH 合成后的配置真启动 MCP，数工具
    6. 拍 pi agent 指纹快照并前后比对，证明没被污染

  它不做什么
    · 不跑 install-pi.ps1 —— 因此不会改 ~/.pi/agent 的 skill / mcp.json
    · 不跑 install-ida.ps1 —— 因此不会改 ~/.pi/agent/mcp.json 的 ida 条目
    · 不安装/修改任何全局依赖

  用法
    powershell -File setup\dsh-isolated-setup.ps1
    powershell -File setup\dsh-isolated-setup.ps1 -LabDir "D:\dsh-lab"
    powershell -File setup\dsh-isolated-setup.ps1 -Profile web
    powershell -File setup\dsh-isolated-setup.ps1 -Force     # 重建（会先备份旧 lab）

  前置：dsh 已在 PATH（npm i -g @deepseek-ai/dsh）。
#>
[CmdletBinding()]
param(
    [string]$LabDir = (Join-Path $env:USERPROFILE 'Desktop\dsh-lab'),
    [string]$Profile = 'web',
    [string]$Python = '',
    [switch]$Force,
    [switch]$SkipVerify
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$LabDsh    = Join-Path $LabDir '.dsh'

function Step($m) { Write-Host "`n>>> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Warn2($m){ Write-Host "    [!!] $m" -ForegroundColor Yellow }
function Info($m) { Write-Host "    [..] $m" -ForegroundColor DarkGray }
function Fail2($m){ Write-Host "    [FAIL] $m" -ForegroundColor Red }

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "          DeepSeek Harness 隔离部署（不影响 Pi Agent）" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "  工作台根目录 : $Root"
Write-Host "  Lab 目录     : $LabDir"
Write-Host "  隔离 DSH_HOME: $LabDsh"
Write-Host "  Profile      : $Profile"

# ---------------------------------------------------------------- 0. 前置检查
Step '0/6  前置检查'

$dsh = (Get-Command dsh -ErrorAction SilentlyContinue)
if (-not $dsh) { Fail2 '未找到 dsh，请先 npm i -g @deepseek-ai/dsh'; exit 1 }
Ok "dsh: $((& dsh --version 2>&1 | Select-Object -First 1))"

$py = $Python
if ([string]::IsNullOrWhiteSpace($py)) {
    foreach ($c in @(
            $env:SEEP_PYTHON,
            (Join-Path $env:USERPROFILE '.pi\agent\seep-venv\Scripts\python.exe'),
            'python'
        )) {
        if ([string]::IsNullOrWhiteSpace($c)) { continue }
        if ($c -eq 'python') {
            $p = Get-Command python -ErrorAction SilentlyContinue
            if (-not $p) { continue }
            $c = $p.Source
        }
        if (-not (Test-Path -LiteralPath $c)) { continue }
        & $c -c "import mcp" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $py = $c; break }
    }
}
if ([string]::IsNullOrWhiteSpace($py)) {
    Fail2 '找不到已安装 mcp 库的 Python；用 -Python 指定，或先跑 setup\install-python.ps1'
    exit 1
}
Ok "Python: $py"

# ---------------------------------------------------------------- 1. 建 lab
Step '1/6  建立隔离 DSH_HOME'
if (Test-Path $LabDir) {
    if (-not $Force) {
        Info "Lab 目录已存在，沿用（要重建请加 -Force）"
    }
    else {
        $bak = "$LabDir.bak-" + (Get-Date -Format 'yyyyMMdd-HHmmss')
        Move-Item -LiteralPath $LabDir -Destination $bak
        Ok "旧 Lab 已备份: $bak"
    }
}
New-Item -ItemType Directory -Force -Path $LabDsh | Out-Null
Ok "DSH_HOME: $LabDsh"

# ---------------------------------------------------------------- 2. 快照（部署前）
Step '2/6  拍 pi agent 指纹快照（部署前）'
$before = Join-Path $LabDir 'pi-agent-before.json'
& $py (Join-Path $ScriptDir 'pi-agent-snapshot.py') snapshot $before 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

# ---------------------------------------------------------------- 3. 自举 profile
Step '3/6  让 DSH 自举 profile'
$env:DSH_HOME = $LabDsh
& dsh --profile $Profile --dump-config 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Fail2 "DSH 自举失败（profile=$Profile）"; exit 1 }
Ok "profile 已就绪: $(Join-Path $LabDsh "profiles\$Profile\cordis.patch.yml")"

# ---------------------------------------------------------------- 4. 生成配置 + 挂载
Step '4/6  生成配置并挂载 seep 补丁'
& $py (Join-Path $ScriptDir 'generate-configs.py') --root $Root 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Warn2 'generate-configs 失败（继续尝试挂载）' } else { Ok '配置文件已生成（写入工作台仓库，幂等）' }

& $py (Join-Path $ScriptDir 'dsh-merge.py') --root $Root --dsh-home $LabDsh --profile $Profile --python $py 2>&1 |
    ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
if ($LASTEXITCODE -ne 0) { Fail2 '挂载失败'; exit 1 }
Ok 'seep 补丁已挂载进隔离 DSH_HOME'

# ---------------------------------------------------------------- 5. 端到端验证
if (-not $SkipVerify) {
    Step '5/6  端到端验证（按 DSH 合成配置真启动 MCP）'
    & $py (Join-Path $ScriptDir 'test_dsh_mount.py') --profile $Profile 2>&1 |
        ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    if ($LASTEXITCODE -ne 0) { Warn2 '端到端验证未通过，见上方输出' }
    else { Ok 'MCP 工具已在 DSH 配置树中可用' }
}
else { Step '5/6  端到端验证（已跳过 -SkipVerify）' }

# ---------------------------------------------------------------- 6. 漂移比对
Step '6/6  pi agent 漂移比对'
$after = Join-Path $LabDir 'pi-agent-after.json'
& $py (Join-Path $ScriptDir 'pi-agent-snapshot.py') snapshot $after 2>&1 | Out-Null
& $py (Join-Path $ScriptDir 'pi-agent-snapshot.py') diff $before $after 2>&1 |
    ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
$drift = $LASTEXITCODE

# ---------------------------------------------------------------- 汇总
Write-Host "`n================================================================================" -ForegroundColor Cyan
if ($drift -eq 0) {
    Write-Host "  ✅ 隔离部署完成：DSH 可用，且 pi agent 零改动" -ForegroundColor Green
}
else {
    Write-Host "  ⚠️  隔离部署完成，但检测到 pi agent 有漂移，见上方清单" -ForegroundColor Yellow
}
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host @"

  如何启动这个隔离的 DSH
    `$env:DSH_HOME = "$LabDsh"
    dsh --profile $Profile

  之后每次开会话都要带上 DSH_HOME（或写进系统环境变量）。
  Windows 一次性设置（当前用户）：
    [Environment]::SetEnvironmentVariable('DSH_HOME','$LabDsh','User')

  工具在 DSH 里的名字
    mcp__seep__seep_pe_triage 这种形式（mcp__<serverName>__<原始工具名>）

  注意：隔离 DSH_HOME 是全新的，没有登录态
    · 首次启动需要在 DSH 里重新登录 / 配置模型；
    · 若不想重新登录，可手动把 ~/.dsh/.credentials.yaml 复制到
      $LabDsh\.credentials.yaml（内含凭据，自行评估风险）。

  卸载
    python setup/dsh-merge.py --dsh-home "$LabDsh" --remove
    或直接删掉 $LabDir

"@ -ForegroundColor Gray

exit $([int]($drift -ne 0))

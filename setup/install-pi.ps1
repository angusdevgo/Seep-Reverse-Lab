#Requires -Version 5.1
<#
  Seep 工作台 —— pi 环境配置
  1. 备份现有配置
  2. 复制 Skill / 提示词 / 扩展
  3. 生成 mcp.json（替换占位符）
  4. 写 settings.json（packages 列表）
  5. 安装 pi 扩展包
#>
[CmdletBinding()]
param(
    [switch]$NoBackup,
    [switch]$SkipPackages
)

$ErrorActionPreference = 'Continue'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root      = Split-Path -Parent $ScriptDir
$ToolDir   = Join-Path $Root 'Tool'
$AgentDir  = Join-Path $env:USERPROFILE '.pi\agent'
$SkillsDir = Join-Path $AgentDir 'skills'
$ExtDir    = Join-Path $AgentDir 'extensions'

function Write-Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "    [!!] $m" -ForegroundColor Yellow }
function Write-Info($m) { Write-Host "    [..] $m" -ForegroundColor Gray }

New-Item -ItemType Directory -Force -Path $AgentDir, $SkillsDir, $ExtDir | Out-Null

# ---------------------------------------------------------------- 1. 备份
if (-not $NoBackup) {
    $stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = Join-Path $AgentDir "_backup_$stamp"
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    $n = 0
    foreach ($f in @('SYSTEM.md', 'AGENTS.md', 'mcp.json', 'settings.json')) {
        $src = Join-Path $AgentDir $f
        if (Test-Path $src) { Copy-Item $src (Join-Path $backup $f) -Force; $n++ }
    }
    if (Test-Path $ExtDir) {
        $eb = Join-Path $backup 'extensions'
        New-Item -ItemType Directory -Force -Path $eb | Out-Null
        Get-ChildItem $ExtDir -Filter '*.ts' -ErrorAction SilentlyContinue |
            ForEach-Object { Copy-Item $_.FullName $eb -Force; $n++ }
    }
    Write-Ok "已备份 $n 个文件 -> $backup"
}

# ---------------------------------------------------------------- 2. Skill
$srcSkills = Join-Path $ToolDir 'skill'
if (Test-Path $srcSkills) {
    foreach ($s in (Get-ChildItem $srcSkills -Directory)) {
        if ($s.Name -eq 'safe-skills') {
            foreach ($sub in (Get-ChildItem $s.FullName -Directory)) {
                $dst = Join-Path $SkillsDir $sub.Name
                if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
                Copy-Item $sub.FullName $dst -Recurse -Force
            }
            Write-Ok 'safe-skills 5 个 -> skills/'
        } else {
            $dst = Join-Path $SkillsDir $s.Name
            if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
            Copy-Item $s.FullName $dst -Recurse -Force
            Write-Ok "skill: $($s.Name)"
        }
    }
} else { Write-Warn "未找到 $srcSkills" }

# ---------------------------------------------------------------- 3. 提示词 + 扩展
$srcPrompt = Join-Path $ToolDir 'prompts'
foreach ($f in @('SYSTEM.md', 'AGENTS.md')) {
    $src = Join-Path $srcPrompt $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $AgentDir $f) -Force; Write-Ok "prompt: $f" }
    else { Write-Warn "未找到 $f" }
}
$srcExt = Join-Path $srcPrompt 'extensions'
if (Test-Path $srcExt) {
    foreach ($f in (Get-ChildItem $srcExt -Filter '*.ts')) {
        Copy-Item $f.FullName (Join-Path $ExtDir $f.Name) -Force
        Write-Ok "extension: $($f.Name)"
    }
}

# ---------------------------------------------------------------- 4. mcp.json
$tpl = Join-Path $ToolDir 'mcp\mcp.json.template'
if (Test-Path $tpl) {
    $content = Get-Content $tpl -Raw -Encoding UTF8
    $content = $content.Replace('<SEEP_ROOT>', $Root)

    # 探测 IDA
    $idaRoot = $null
    foreach ($cand in @('D:\Tool\IDA Pro', 'C:\Program Files\IDA Pro', 'C:\IDA Pro')) {
        if (Test-Path (Join-Path $cand 'ida.exe')) { $idaRoot = $cand; break }
    }
    if ($idaRoot) {
        $idaPy = Join-Path $idaRoot 'python311\python.exe'
        $content = $content.Replace('<IDA_ROOT>', $idaRoot)
        $content = $content.Replace('<IDA_PYTHON>', $idaPy)
        Write-Ok "探测到 IDA: $idaRoot"
    } else {
        Write-Warn '未探测到 IDA Pro，mcp.json 中 ida 条目保留占位符（见 MANUAL\IDA-PRO.md）'
    }

    $dstMcp = Join-Path $AgentDir 'mcp.json'
    Set-Content -Path $dstMcp -Value $content -Encoding UTF8
    Write-Ok "mcp.json 已生成 -> $dstMcp"

    if ($content -match '<YOUR_PLAYWRIGHT_TOKEN>') {
        Write-Info 'playwright token 仍为占位符（不用浏览器自动化可忽略）'
    }
} else { Write-Warn "未找到 $tpl" }

# ---------------------------------------------------------------- 5. settings.json
$dstSettings = Join-Path $AgentDir 'settings.json'
$packages = @(
    'npm:pi-open-tui',
    'npm:pi-web-access',
    'npm:@juicesharp/rpiv-todo',
    'npm:@narumitw/pi-btw',
    'npm:@narumitw/pi-plan-mode',
    'npm:@narumitw/pi-usage',
    'npm:pi-mcp-extension',
    'npm:@smoose/pi-themes',
    'npm:pi-tool-display',
    'npm:@juicesharp/rpiv-ask-user-question',
    'npm:pi-playwright',
    'npm:pi-goal-x'
)

$settings = $null
if (Test-Path $dstSettings) {
    try { $settings = Get-Content $dstSettings -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $settings = $null }
}
if ($null -eq $settings) { $settings = [pscustomobject]@{} }

$settings | Add-Member -NotePropertyName 'packages' -NotePropertyValue $packages -Force
$settings | ConvertTo-Json -Depth 10 | Set-Content -Path $dstSettings -Encoding UTF8
Write-Ok "settings.json 已写入 $($packages.Count) 个 packages"

# ---------------------------------------------------------------- 6. 安装扩展包
if (-not $SkipPackages) {
    $pi = Get-Command pi -ErrorAction SilentlyContinue
    if ($pi) {
        Write-Info 'pi update --extensions ...'
        & pi update --extensions 2>&1 | ForEach-Object { Write-Info $_ }
        if ($LASTEXITCODE -eq 0) { Write-Ok 'pi 扩展包已更新' }
        else { Write-Warn 'pi update 失败，可稍后手动执行：pi update --extensions' }
    } else {
        Write-Warn '未找到 pi 命令，跳过扩展包安装'
        Write-Info '安装 pi 后手动执行：pi update --extensions'
    }
}

Write-Host "`n    提示：需重启 pi 使 Skill / 提示词 / MCP 生效" -ForegroundColor Yellow
exit 0

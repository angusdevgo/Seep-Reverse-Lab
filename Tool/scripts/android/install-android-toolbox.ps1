#requires -Version 5
<#
.SYNOPSIS
    部署 / 修复 Seep Android 外部工具箱（Frida + objection + frida-dexdump + APKiD + Aotopsy）。

.DESCRIPTION
    把动态插桩与 Flutter AOT 分析能力落地到本机工具箱目录（默认 D:\Tool\Android），
    并在 Seep Lab中建立统一垫片（shim）与解析层，使 MCP / 脚本 / Agent 都能直接调用。

    幂等：重复执行只做增量补齐，不会破坏已有 venv 或用户自装包。

    安装产物：
      <root>\frida-env\        独立 Python venv（frida/frida-tools/objection/frida-dexdump/apkid）
      <root>\aotopsy\          aotopsy.exe + ghidra_scripts + ida_scripts
      <root>\bin\              frida / objection / apkid / aotopsy 等 .cmd 垫片
      <root>\bin 加入用户 PATH（-SkipPath 可跳过）

.PARAMETER Root
    工具箱根目录，默认取 $env:SEEP_ANDROID_TOOLBOX，否则 D:\Tool\Android。

.PARAMETER PythonExe
    用于创建 venv 的 Python 解释器。默认自动挑选 3.10 ~ 3.13（frida 无 3.14 预编译轮子）。

.PARAMETER Only
    只安装指定组件（frida | apkid | aotopsy | shims）。默认全部。

.PARAMETER SkipPath
    不修改用户 PATH 环境变量。

.PARAMETER AotopsySource
    Aotopsy 源目录，默认 <repo>\Tool\aotopsy。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1 -Only apkid -SkipPath
#>
[CmdletBinding()]
param(
    [string]$Root,
    [string]$PythonExe,
    [ValidateSet('all', 'frida', 'apkid', 'aotopsy', 'shims')]
    [string[]]$Only = @('all'),
    [switch]$SkipPath,
    [string]$AotopsySource
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

. (Join-Path $PSScriptRoot '..\lib\AndroidToolbox.ps1')

$wantAll = $Only -contains 'all'
function Test-Want {
    param([string]$Name)
    return ($wantAll -or ($Only -contains $Name))
}

if ([string]::IsNullOrWhiteSpace($Root)) { $Root = Get-AndroidToolboxRoot }
$binDir = Join-Path $Root 'bin'
$venvDir = Join-Path $Root 'frida-env'
$aotopsyDir = Join-Path $Root 'aotopsy'

if ([string]::IsNullOrWhiteSpace($AotopsySource)) {
    $AotopsySource = Join-Path $PSScriptRoot '..\..\aotopsy'
}

Write-Host "== Seep Android 工具箱部署 ==" -ForegroundColor Cyan
Write-Host "  Root      : $Root"
Write-Host "  Components: $($Only -join ', ')"
Write-Host ""

foreach ($d in @($Root, $binDir)) {
    if (-not (Test-Path -LiteralPath $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "  [mkdir] $d" -ForegroundColor DarkGray
    }
}

# ---------------------------------------------------------------------------
# 1. 选择 Python 解释器（frida 需要 <= 3.13 的预编译轮子）
# ---------------------------------------------------------------------------
function Resolve-BootstrapPython {
    param([string]$Preferred)

    if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
        if (-not (Test-Path -LiteralPath $Preferred)) { throw "指定的 Python 不存在: $Preferred" }
        return $Preferred
    }

    $candidates = @()
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($v in @('3.12', '3.11', '3.13', '3.10')) {
            try {
                $p = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $p) { $candidates += $p.Trim() }
            }
            catch { }
        }
    }
    foreach ($c in @(
            # uv installed Python: version in the path varies per machine, match it
            (Get-ChildItem "$env:APPDATA\uv\python\cpython-3.1*-windows-*\python.exe" -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName),
            'C:\Program Files\Python312\python.exe',
            'C:\Program Files\Python311\python.exe',
            'C:\Program Files\Python310\python.exe'
        )) {
        if (Test-Path -LiteralPath $c) { $candidates += $c }
    }

    foreach ($c in $candidates) {
        if (-not (Test-Path -LiteralPath $c)) { continue }
        try {
            $ver = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            $ver = $ver.Trim()
            $minor = [int]($ver.Split('.')[1])
            $major = [int]($ver.Split('.')[0])
            if ($major -eq 3 -and $minor -ge 10 -and $minor -le 13) { return $c }
        }
        catch { }
    }

    throw "未找到可用的 Python 3.10~3.13（frida 暂无 3.14 轮子）。请用 -PythonExe 显式指定。"
}

# ---------------------------------------------------------------------------
# 2. Frida 生态 + APKiD（同一个 venv）
# ---------------------------------------------------------------------------
$needVenv = (Test-Want 'frida') -or (Test-Want 'apkid')
if ($needVenv) {
    $venvPy = Join-Path $venvDir 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPy)) {
        $py = Resolve-BootstrapPython -Preferred $PythonExe
        Write-Host "[venv] 使用 Python: $py" -ForegroundColor Green
        & $py -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "创建 venv 失败: $venvDir" }
    }
    else {
        Write-Host "[venv] 已存在，复用: $venvDir" -ForegroundColor DarkGray
    }

    $packages = @()
    if (Test-Want 'frida') { $packages += @('frida', 'frida-tools', 'objection', 'frida-dexdump') }
    if (Test-Want 'apkid') { $packages += @('apkid') }

    Write-Host "[pip] 安装: $($packages -join ' ')" -ForegroundColor Green
    & $venvPy -m pip install --upgrade --quiet $packages
    if ($LASTEXITCODE -ne 0) { throw "pip 安装失败（检查网络 / 代理）" }
}

# ---------------------------------------------------------------------------
# 3. Aotopsy（纯 Go 单文件，直接从仓库 Tool/aotopsy 复制，无需构建）
# ---------------------------------------------------------------------------
if (Test-Want 'aotopsy') {
    $srcExe = Join-Path $AotopsySource 'aotopsy.exe'
    if (Test-Path -LiteralPath $srcExe) {
        if (-not (Test-Path -LiteralPath $aotopsyDir)) {
            New-Item -ItemType Directory -Path $aotopsyDir -Force | Out-Null
        }
        Copy-Item -Path (Join-Path $AotopsySource '*') -Destination $aotopsyDir -Recurse -Force
        Write-Host "[aotopsy] 已部署: $aotopsyDir" -ForegroundColor Green
    }
    else {
        Write-Warning "未找到 Aotopsy 源 ($srcExe)，跳过。可手动下载后放到 $aotopsyDir"
    }
}

# ---------------------------------------------------------------------------
# 4. 统一垫片（shims）——让 PATH 上只有短名字
# ---------------------------------------------------------------------------
if (Test-Want 'shims') {
    $shimMap = [ordered]@{
        'frida'            = (Join-Path $venvDir 'Scripts\frida.exe')
        'frida-ps'         = (Join-Path $venvDir 'Scripts\frida-ps.exe')
        'frida-trace'      = (Join-Path $venvDir 'Scripts\frida-trace.exe')
        'frida-ls-devices' = (Join-Path $venvDir 'Scripts\frida-ls-devices.exe')
        'frida-apk'        = (Join-Path $venvDir 'Scripts\frida-apk.exe')
        'objection'        = (Join-Path $venvDir 'Scripts\objection.exe')
        'frida-dexdump'    = (Join-Path $venvDir 'Scripts\frida-dexdump.exe')
        'apkid'            = (Join-Path $venvDir 'Scripts\apkid.exe')
        'aotopsy'          = (Join-Path $aotopsyDir 'aotopsy.exe')
    }

    foreach ($k in $shimMap.Keys) {
        $target = $shimMap[$k]
        $shimPath = Join-Path $binDir "$k.cmd"
        if (-not (Test-Path -LiteralPath $target)) {
            Write-Host "  [shim:skip] $k （目标缺失: $target）" -ForegroundColor DarkYellow
            continue
        }
        $content = "@echo off`r`n`"$target`" %*`r`n"
        Set-Content -LiteralPath $shimPath -Value $content -Encoding ASCII
        Write-Host "  [shim] $k.cmd" -ForegroundColor DarkGray
    }

    if (-not $SkipPath) {
        $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
        if ([string]::IsNullOrWhiteSpace($userPath)) { $userPath = '' }
        if (($userPath -split ';') -notcontains $binDir) {
            $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $binDir } else { $userPath.TrimEnd(';') + ';' + $binDir }
            [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
            Write-Host "[path] 已加入用户 PATH: $binDir" -ForegroundColor Green
        }
        else {
            Write-Host "[path] 已在用户 PATH 中: $binDir" -ForegroundColor DarkGray
        }
    }
}

# ---------------------------------------------------------------------------
# 5. 就绪看板
# ---------------------------------------------------------------------------
Write-Host ""
$status = Get-AndroidToolboxStatus
Write-Host "== 就绪看板 ==" -ForegroundColor Cyan
foreach ($row in $status.Tools) {
    $mark = if ($row.Ready) { 'READY  ' } else { 'MISSING' }
    $color = if ($row.Ready) { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1,-16} {2}" -f $mark, $row.Tool, $row.Path) -ForegroundColor $color
}
Write-Host ""
Write-Host "提示：新开的终端才会带上新的 PATH。当前会话内可直接用绝对路径调用。" -ForegroundColor DarkGray

# AndroidToolbox.ps1 - Android 外部工具箱统一解析层（Frida / objection / APKiD / Aotopsy）
#
# 设计目标：Seep Lab不把上 GB 的 Python 生态塞进仓库，而是统一"指向"本机工具箱，
# 并保证任何一台机器上路径不同也能自动探测到。
#
# 探测优先级：
#   1. 环境变量 SEEP_ANDROID_TOOLBOX 指定的根目录
#   2. 默认根目录 D:\Tool\Android   （Windows，本项目约定安装位）
#   3. 各工具在系统 PATH 中的可执行文件（Linux / macOS / 换机器的场景）
#
# 工具箱标准布局（由 Tool/scripts/android/install-android-toolbox.ps1 建立）：
#   <root>\bin\            统一 .cmd 垫片目录（建议加入 PATH）
#   <root>\frida-env\      Python venv: frida / frida-tools / objection / frida-dexdump / apkid
#   <root>\aotopsy\        aotopsy.exe + ghidra_scripts + ida_scripts
#   <root>\platform-tools\ adb

function Get-AndroidToolboxRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:SEEP_ANDROID_TOOLBOX)) {
        return $env:SEEP_ANDROID_TOOLBOX
    }
    return 'D:\Tool\Android'
}

function Get-AndroidToolboxBinDir {
    return (Join-Path (Get-AndroidToolboxRoot) 'bin')
}

function Get-AndroidVenvScriptsDir {
    return (Join-Path (Get-AndroidToolboxRoot) 'frida-env\Scripts')
}

<#
.SYNOPSIS
    解析 Android 工具箱中某个工具的可执行路径。
.DESCRIPTION
    依次查找：<root>\bin\<name>.cmd → <root>\frida-env\Scripts\<name>.exe →
    <root>\aotopsy\<name>.exe → 系统 PATH。找不到返回 $null（不抛异常）。
#>
function Resolve-AndroidTool {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $root = Get-AndroidToolboxRoot
    $candidates = @(
        (Join-Path $root "bin\$Name.cmd"),
        (Join-Path $root "frida-env\Scripts\$Name.exe"),
        (Join-Path $root "aotopsy\$Name.exe"),
        (Join-Path $root "$Name\bin\$Name.bat"),
        (Join-Path $root "$Name.exe")
    )

    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }

    $onPath = Get-Command $Name -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    # adb 常见位于 platform-tools
    $adb = Join-Path $root 'platform-tools\adb.exe'
    if ($Name -eq 'adb' -and (Test-Path -LiteralPath $adb)) { return $adb }

    return $null
}

<#
.SYNOPSIS
    判断工具是否就绪，返回布尔值。
#>
function Test-AndroidTool {
    param([Parameter(Mandatory = $true)][string]$Name)
    return ($null -ne (Resolve-AndroidTool -Name $Name))
}

<#
.SYNOPSIS
    运行工具箱内的某个工具，并把 stdout/stderr/exitcode 合并输出。
#>
function Invoke-AndroidTool {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string[]]$Arguments = @(),
        [int]$TimeoutSeconds = 0
    )

    $exe = Resolve-AndroidTool -Name $Name
    if (-not $exe) {
        throw "工具未就绪: $Name （请先运行 Tool/scripts/android/install-android-toolbox.ps1）"
    }

    if ($TimeoutSeconds -le 0) {
        & $exe @Arguments 2>&1
        return
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    foreach ($a in $Arguments) { [void]$psi.ArgumentList.Add($a) }

    $proc = [System.Diagnostics.Process]::Start($psi)
    $out = $proc.StandardOutput.ReadToEndAsync()
    $err = $proc.StandardError.ReadToEndAsync()
    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
        try { $proc.Kill($true) } catch { }
        throw "工具执行超时 (>${TimeoutSeconds}s): $Name"
    }
    Write-Output $out.Result
    Write-Output $err.Result
}

<#
.SYNOPSIS
    以“干净文本”方式调用外部工具：把 stderr（aotopsy/frida 会往 stderr 写正常进度）
    与 stdout 合并输出为纯字符串，并将其中的 NativeCommandError 折叠成一行文本。
.DESCRIPTION
    直接写 `& $exe 2>&1` 在 $ErrorActionPreference='Continue' 下会把 stderr 渲染成
    带 CategoryInfo / FullyQualifiedErrorId 的错误块，污染输出与取证日志。
#>
function Invoke-AndroidNative {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @(),
        [switch]$Quiet
    )

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $line = if ($_ -is [System.Management.Automation.ErrorRecord]) {
                # 空 stderr 行会变成 Message 为空的 ErrorRecord，ToString() 会输出类型名，需要丢弃
                $msg = ''
                try { $msg = $_.Exception.Message } catch { $msg = '' }
                if ($msg) { $msg } else { '' }
            }
            else { "$_" }
            if ([string]::IsNullOrWhiteSpace($line)) { return }
            if (-not $Quiet) { Write-Host "  $line" } else { $line }
        }
    }
    finally { $ErrorActionPreference = $prevEap }
}

<#
.SYNOPSIS
    输出 Android 工具箱整体就绪看板（供 verify / recon 复用）。
#>
function Get-AndroidToolboxStatus {
    $root = Get-AndroidToolboxRoot
    $tools = [ordered]@{
        'frida'         = 'Frida 动态插桩主程序 (frida CLI)'
        'frida-ps'      = 'Frida 进程枚举'
        'frida-trace'   = 'Frida 调用追踪'
        'objection'     = 'objection 运行时自动化 (SSL Pinning / Root 绕过)'
        'frida-dexdump' = 'frida-dexdump 内存脱壳'
        'apkid'         = 'APKiD 查壳 / 反调试 / 混淆指纹'
        'aotopsy'       = 'Aotopsy Flutter AOT (libapp.so) 分析器'
    }

    $rows = foreach ($k in $tools.Keys) {
        $p = Resolve-AndroidTool -Name $k
        [pscustomobject]@{
            Tool     = $k
            Ready    = [bool]$p
            Path     = if ($p) { $p } else { '—' }
            Purpose  = $tools[$k]
        }
    }

    $adb = Resolve-AndroidTool -Name 'adb'
    $rows += [pscustomobject]@{
        Tool    = 'adb'
        Ready   = [bool]$adb
        Path    = if ($adb) { $adb } else { '—' }
        Purpose = 'Android Debug Bridge（设备连接）'
    }

    return [pscustomobject]@{
        Root  = $root
        Tools = $rows
    }
}

#requires -Version 5
<#
.SYNOPSIS
    Android 目标一键 Recon —— 查壳 / 结构清点 / 清单摘要 / Flutter AOT 判定，一次出画像。

.DESCRIPTION
    Seep 的 Zero-Waste Recon 落地脚本：在写第一行 Hook 之前，先用 60 秒把"这是什么应用、
    怎么防的、该走哪条路"全部量化，避免一上来就盲啃 JADX。

    产出四块：
      1. 加固与对抗指纹   —— APKiD：packer / protector / anti_vm / anti_debug / obfuscator
      2. 包体结构        —— DEX 数量与体积、SO 数量、架构、assets 异常目录
      3. 清单摘要        —— 包名 / 版本 / SDK / 启动组件 / 危险权限 / exported 组件 / allowBackup
      4. 技术栈判定      —— Flutter(是否检出 libapp.so + Dart 版本) / RN / UniApp / 原生

    最终给出「路线建议」：脱壳优先 / 伪装优先 / Flutter AOT 优先 / 直接静态。

.PARAMETER ApkPath
    目标 APK（可用 -ApkPath a.apk,b.apk 或多次 -ApkPath）。

.PARAMETER OutDir
    证据落盘目录，默认 `.\recon\<apk名>\`。同时写出 recon.json 与 recon.md。

.PARAMETER SkipAotopsy
    跳过 Flutter AOT 扫描（更快）。

.PARAMETER SkipAapt
    跳过清单摘要（无 aapt/aapt2 时自动跳过）。

.EXAMPLE
    powershell -File Tool\scripts\android\android-recon.ps1 -ApkPath .\target.apk

.EXAMPLE
    powershell -File Tool\scripts\android\android-recon.ps1 -ApkPath .\a.apk,.\b.apk -OutDir .\recon
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$ApkPath,

    [string]$OutDir,
    [switch]$SkipAotopsy,
    [switch]$SkipAapt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

. (Join-Path $PSScriptRoot '..\lib\AndroidToolbox.ps1')

Add-Type -AssemblyName System.IO.Compression.FileSystem

# ---------------------------------------------------------------------------
# 工具解析
# ---------------------------------------------------------------------------
$apkid = Resolve-AndroidTool -Name 'apkid'
$aotopsy = Resolve-AndroidTool -Name 'aotopsy'

function Resolve-Aapt {
    $root = Get-AndroidToolboxRoot
    $btRoot = Join-Path $root 'build-tools'
    if (Test-Path -LiteralPath $btRoot) {
        $versions = Get-ChildItem -LiteralPath $btRoot -Directory | Sort-Object Name -Descending
        foreach ($v in $versions) {
            $a2 = Join-Path $v.FullName 'aapt2.exe'
            if (Test-Path -LiteralPath $a2) { return $a2 }
            $a1 = Join-Path $v.FullName 'aapt.exe'
            if (Test-Path -LiteralPath $a1) { return $a1 }
        }
    }
    $cmd = Get-Command aapt2 -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$aapt = Resolve-Aapt

$targets = @()
# 兼容 `powershell -File ... -ApkPath a.apk,b.apk` 把逗号列表当单一字符串传入的情形
$expanded = @()
foreach ($p in $ApkPath) {
    if ($null -eq $p) { continue }
    foreach ($piece in ([string]$p -split ',')) {
        $t = $piece.Trim().Trim('"').Trim("'")
        if (-not [string]::IsNullOrWhiteSpace($t)) { $expanded += $t }
    }
}
foreach ($p in $expanded) {
    $full = Resolve-Path -LiteralPath $p -ErrorAction SilentlyContinue
    if (-not $full) { Write-Warning "目标不存在，跳过: $p"; continue }
    $targets += $full.Path
}
if ($targets.Count -eq 0) { throw "没有任何有效 APK 路径" }

if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path (Get-Location).Path 'recon' }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

# ---------------------------------------------------------------------------
# 逐目标分析
# ---------------------------------------------------------------------------
function Get-ApkStructure {
    param([string]$ApkFile)

    $result = [ordered]@{
        size_mb    = [math]::Round((Get-Item -LiteralPath $ApkFile).Length / 1MB, 2)
        dex        = @()
        so         = @()
        abis       = @()
        assets     = @()
        has_flutter = $false
        has_libapp  = $false
        libapp_path = $null
    }

    $zip = [System.IO.Compression.ZipFile]::OpenRead($ApkFile)
    try {
        foreach ($e in $zip.Entries) {
            $n = $e.FullName
            if ($n -match '^classes[0-9]*\.dex$') {
                $result.dex += [pscustomobject]@{ Name = $n; MB = [math]::Round($e.Length / 1MB, 2) }
            }
            elseif ($n -like 'lib/*' -and $n.EndsWith('.so')) {
                $parts = $n.Split('/')
                $abi = if ($parts.Count -ge 3) { $parts[1] } else { '?' }
                $result.so += [pscustomobject]@{ Name = $parts[-1]; Abi = $abi; MB = [math]::Round($e.Length / 1MB, 2) }
                if ($result.abis -notcontains $abi) { $result.abis += $abi }
                if ($parts[-1] -eq 'libflutter.so') { $result.has_flutter = $true }
                if ($parts[-1] -eq 'libapp.so') { $result.has_libapp = $true; $result.libapp_path = $n }
            }
            elseif ($n -like 'assets/*') {
                # 只记一层目录名，识别二次打包壳的内嵌包与加固载荷目录
                $segs = $n.Split('/')
                if ($segs.Count -ge 2) {
                    $top = "assets/$($segs[1])"
                    if ($result.assets -notcontains $top -and $result.assets.Count -lt 40) { $result.assets += $top }
                }
                if ($n -like 'assets/*.apk' -or $n -like 'assets/base.apk') { $result.has_libapp = $result.has_libapp }
            }
        }
    }
    finally { $zip.Dispose() }

    return $result
}

function Get-ApkManifestSummary {
    param([string]$ApkFile)

    if (-not $aapt) { return $null }
    $out = & $aapt dump badging $ApkFile 2>&1 | Out-String
    if ([string]::IsNullOrWhiteSpace($out) -or $out -match 'ERROR|error:') { return $null }

    $summary = [ordered]@{
        package       = $null
        version_name  = $null
        version_code  = $null
        sdk           = $null
        target_sdk    = $null
        launchable    = $null
        permissions   = @()
        cleartext     = $null
        allow_backup  = $null
    }

    foreach ($line in ($out -split "`r?`n")) {
        if ($line -match "^package: name='([^']+)' versionCode='([^']*)' versionName='([^']*)'") {
            $summary.package = $Matches[1]; $summary.version_code = $Matches[2]; $summary.version_name = $Matches[3]
        }
        # aapt2 输出为 minSdkVersion，aapt1 输出为 sdkVersion，两者都要兼容
        elseif ($line -match "^(min)?sdkVersion:'([^']+)'") { $summary.sdk = $Matches[2] }
        elseif ($line -match "^targetSdkVersion:'([^']+)'") { $summary.target_sdk = $Matches[1] }
        elseif ($line -match "launchable-activity: name='([^']+)'") { $summary.launchable = $Matches[1] }
        elseif ($line -match '^uses-permission: name=') {
            $perm = ($line -split "name='")[1]
            if ($perm) { $summary.permissions += ($perm -split "'")[0] }
        }
    }

    # allowBackup / usesCleartextTraffic 需看 XML，用 aapt2 dump xmltree
    # 行格式：A: http://schemas.android.com/apk/res/android:allowBackup(0x01010280)=true
    $treeOut = & $aapt dump xmltree $ApkFile --file AndroidManifest.xml 2>&1 | Out-String
    if ($treeOut -match 'allowBackup\([^)]*\)=(true|false)') {
        $summary.allow_backup = ($Matches[1] -eq 'true')
    }
    if ($treeOut -match 'usesCleartextTraffic\([^)]*\)=(true|false)') {
        $summary.cleartext = ($Matches[1] -eq 'true')
    }

    return $summary
}

function Get-ApkidMatches {
    param([string]$ApkFile)

    if (-not $apkid) { return $null }
    $rawText = (Invoke-AndroidNative -Exe $apkid -Arguments @('-j', $ApkFile) -Quiet) -join "`n"
    $start = $rawText.IndexOf('{')
    if ($start -lt 0) { return $null }
    try { $doc = $rawText.Substring($start).Trim() | ConvertFrom-Json } catch { return $null }

    $agg = [ordered]@{}
    foreach ($f in $doc.files) {
        if (-not $f.matches) { continue }
        $short = if ($f.filename -like '*!*') { ($f.filename -split '!')[-1] } else { Split-Path -Leaf $f.filename }
        foreach ($prop in $f.matches.PSObject.Properties) {
            if (-not $agg.Contains($prop.Name)) { $agg[$prop.Name] = @() }
            $entry = "$short :: $(@($prop.Value) -join ', ')"
            if ($agg[$prop.Name] -notcontains $entry) { $agg[$prop.Name] += $entry }
        }
    }
    return $agg
}

$reportAll = @()

foreach ($apk in $targets) {
    $leaf = [System.IO.Path]::GetFileNameWithoutExtension($apk)
    $caseDir = Join-Path $OutDir $leaf
    if (-not (Test-Path -LiteralPath $caseDir)) { New-Item -ItemType Directory -Path $caseDir -Force | Out-Null }

    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host " 目标: $(Split-Path -Leaf $apk)" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan

    # 1. 结构清点
    Write-Host "[1/4] 包体结构清点 ..." -ForegroundColor Yellow
    $struct = Get-ApkStructure -ApkFile $apk
    Write-Host "  体积      : $($struct.size_mb) MB"
    Write-Host "  DEX       : $($struct.dex.Count) 个 (合计 $([math]::Round(($struct.dex | Measure-Object -Property MB -Sum).Sum,2)) MB)"
    Write-Host "  SO        : $($struct.so.Count) 个 / ABI: $($struct.abis -join ', ')"
    Write-Host "  Flutter   : libflutter=$(if($struct.has_flutter){'YES'}else{'no'})  libapp=$(if($struct.has_libapp){'YES'}else{'no'})"

    # 2. 加固指纹
    Write-Host "[2/4] APKiD 加固与对抗指纹 ..." -ForegroundColor Yellow
    $apkidAgg = Get-ApkidMatches -ApkFile $apk
    if ($null -eq $apkidAgg) {
        Write-Host "  APKiD 不可用或解析失败，跳过" -ForegroundColor DarkYellow
    }
    else {
        foreach ($k in $apkidAgg.Keys) {
            Write-Host ("  {0,-14}: {1}" -f $k, (($apkidAgg[$k]) -join ' | '))
        }
    }

    # 3. 清单摘要
    Write-Host "[3/4] 清单摘要 ..." -ForegroundColor Yellow
    $manifest = $null
    if ($SkipAapt -or -not $aapt) {
        Write-Host "  跳过（无 aapt/aapt2 或已 -SkipAapt）" -ForegroundColor DarkYellow
    }
    else {
        $manifest = Get-ApkManifestSummary -ApkFile $apk
        if ($null -eq $manifest) {
            Write-Host "  aapt 解析失败，跳过" -ForegroundColor DarkYellow
        }
        else {
            Write-Host "  包名      : $($manifest.package)  v$($manifest.version_name) ($($manifest.version_code))"
            Write-Host "  SDK       : min=$($manifest.sdk)  target=$($manifest.target_sdk)"
            Write-Host "  入口      : $($manifest.launchable)"
            Write-Host "  允许备份  : $($manifest.allow_backup)   明文HTTP: $($manifest.cleartext)"
            $danger = @('SEND_SMS', 'READ_SMS', 'RECEIVE_SMS', 'READ_CONTACTS', 'READ_CALL_LOG', 'CAMERA', 'RECORD_AUDIO',
                'ACCESS_FINE_LOCATION', 'READ_EXTERNAL_STORAGE', 'WRITE_EXTERNAL_STORAGE', 'MANAGE_EXTERNAL_STORAGE',
                'REQUEST_INSTALL_PACKAGES', 'SYSTEM_ALERT_WINDOW', 'QUERY_ALL_PACKAGES')
            $hit = @()
            foreach ($p in $manifest.permissions) {
                foreach ($d in $danger) {
                    if ($p.EndsWith($d)) { $hit += $p.Split('.')[-1] }
                }
            }
            Write-Host "  权限总数  : $($manifest.permissions.Count)   敏感: $(if($hit.Count){$hit -join ', '}else{'无'})"
        }
    }

    # 4. Flutter AOT
    Write-Host "[4/4] 技术栈 / Flutter AOT 判定 ..." -ForegroundColor Yellow
    $dartInfo = $null
    if ($SkipAotopsy) {
        Write-Host "  已 -SkipAotopsy，跳过" -ForegroundColor DarkYellow
    }
    elseif (-not $aotopsy) {
        Write-Host "  Aotopsy 未部署，跳过（install-android-toolbox.ps1 -Only aotopsy）" -ForegroundColor DarkYellow
    }
    elseif (-not $struct.has_libapp) {
        Write-Host "  未发现 libapp.so → 非 Flutter，或已被加固剥离" -ForegroundColor DarkGray
    }
    else {
        Invoke-AndroidNative -Exe $aotopsy -Arguments @('find-libapp', '-apk', $apk, '-out', $caseDir) -Quiet | Out-Null        $jf = Get-ChildItem -LiteralPath $caseDir -Filter '*_find_libapp.json' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($jf) {
            try { $lj = Get-Content -LiteralPath $jf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $lj = $null }
            if ($lj -and $lj.found) {
                $dartInfo = $lj.best
                Write-Host "  Dart AOT  : $($lj.best.path_in_apk)" -ForegroundColor Green
                Write-Host "  Dart 版本 : $($lj.best.dart_version)   Snapshot: $($lj.best.snapshot_hash)"
            }
        }
    }

    # 5. 路线建议
    Write-Host ""
    Write-Host "  >>> 路线建议" -ForegroundColor Magenta
    $hasPacker = $false
    $hasAntiVm = $false
    if ($null -ne $apkidAgg) {
        $hasPacker = $apkidAgg.Contains('packer') -or $apkidAgg.Contains('protector')
        $hasAntiVm = $apkidAgg.Contains('anti_vm') -or $apkidAgg.Contains('anti_debug')
    }

    $routes = @()
    if ($hasPacker) { $routes += "① 加壳 → 先内存脱壳：frida-dexdump-run.ps1 -Package <pkg> -Spawn -DeepSearch" }
    if ($hasAntiVm) { $routes += "② 反调试/反模拟器 → 先伪装：objection-run.ps1 -Package <pkg>（android root disable）" }
    if ($null -ne $dartInfo) { $routes += "③ Flutter/Dart AOT → 走 Aotopsy：aotopsy-run.ps1 -Target <apk> -Action signal -Decompile" }
    if ($routes.Count -eq 0) { $routes += "① 无壳无强对抗 → 可直接 JADX-GUI + decode.ps1 静态推进" }

    foreach ($r in $routes) { Write-Host "  $r" -ForegroundColor Magenta }

    # 落盘
    $record = [ordered]@{
        apk        = $apk
        scanned_at = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')
        structure  = $struct
        apkid      = $apkidAgg
        manifest   = $manifest
        dart       = $dartInfo
        routes     = $routes
    }
    $jsonPath = Join-Path $caseDir 'recon.json'
    ($record | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $jsonPath -Encoding utf8
    Write-Host ""
    Write-Host "  [证据] $jsonPath" -ForegroundColor DarkGray

    $reportAll += $record
}

Write-Host ""
Write-Host "Recon 完成。共 $($reportAll.Count) 个目标，证据目录: $OutDir" -ForegroundColor Green

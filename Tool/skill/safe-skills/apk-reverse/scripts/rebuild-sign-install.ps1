#requires -Version 7

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [string]$OutDir,

    [string]$BaseName,

    [string]$KeystorePath = (Join-Path $PSScriptRoot '..\debug.keystore'),

    [string]$KeyAlias = 'androiddebugkey',

    [string]$StorePass = 'android',

    [string]$KeyPass = 'android',

    [string]$DeviceSerial,

    [switch]$Install,

    [switch]$Reinstall,

    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-ToolPath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $toolRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
    $sdkRoots = @(
        $env:ANDROID_HOME
        $env:ANDROID_SDK_ROOT
        (Join-Path $env:LOCALAPPDATA 'Android\Sdk')
        (Join-Path $env:USERPROFILE 'AppData\Local\Android\Sdk')
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

    $buildTools = @()
    foreach ($sdk in $sdkRoots) {
        $btDir = Join-Path $sdk 'build-tools'
        if (Test-Path $btDir) {
            $buildTools += Get-ChildItem $btDir -Directory -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending
        }
    }

    $zipaligns = @()
    $apksigners = @()
    foreach ($bt in $buildTools) {
        $zipaligns += (Join-Path $bt.FullName 'zipalign.exe')
        $apksigners += (Join-Path $bt.FullName 'apksigner.bat')
    }

    $adbs = @()
    foreach ($sdk in $sdkRoots) {
        $adbs += (Join-Path $sdk 'platform-tools\adb.exe')
    }

    $keytools = @()
    if ($env:JAVA_HOME) {
        $keytools += (Join-Path $env:JAVA_HOME 'bin\keytool.exe')
    }
    $keytools += @(
        (Join-Path $env:ProgramFiles 'Android\Android Studio\jbr\bin\keytool.exe')
    )

    $fallbacks = @{
        'apktool' = @(
            (Join-Path $toolRoot 'apktool\apktool.bat')
        )
        'zipalign' = $zipaligns
        'apksigner' = $apksigners
        'keytool' = $keytools
        'adb' = $adbs
    }

    if ($fallbacks.Contains($Name)) {
        foreach ($candidate in $fallbacks[$Name]) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                return $candidate
            }
        }
    }

    throw "Missing required CLI tool: $Name"
}

function Ensure-DebugKeystore {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Keytool,
        [Parameter(Mandatory = $true)][string]$Alias,
        [Parameter(Mandatory = $true)][string]$StorePassword,
        [Parameter(Mandatory = $true)][string]$KeyPassword
    )

    if (Test-Path -LiteralPath $Path) {
        return
    }

    $parent = Split-Path -Path $Path -Parent
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    & $Keytool -genkeypair -v -keystore $Path -storepass $StorePassword -keypass $KeyPassword -alias $Alias -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Android Debug,O=OpenCode,C=CN'
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to generate debug keystore.'
    }
}

if (-not (Test-Path -LiteralPath $ProjectDir)) {
    throw "Project directory not found: $ProjectDir"
}

if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $projectParent = Split-Path -Path $ProjectDir -Parent
    if ([string]::IsNullOrWhiteSpace($projectParent)) {
        $projectParent = [System.IO.Directory]::GetCurrentDirectory()
    }
    $OutDir = $projectParent
}

$apktool = Get-ToolPath -Name 'apktool'
$zipalign = Get-ToolPath -Name 'zipalign'
$apksigner = Get-ToolPath -Name 'apksigner'
$keytool = Get-ToolPath -Name 'keytool'
$adb = Get-ToolPath -Name 'adb'

Ensure-DebugKeystore -Path $KeystorePath -Keytool $keytool -Alias $KeyAlias -StorePassword $StorePass -KeyPassword $KeyPass

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$name = if ($BaseName) { $BaseName } else { Split-Path -Path $ProjectDir -Leaf }
$unsignedApk = Join-Path $OutDir ($name + '-unsigned.apk')
$alignedApk = Join-Path $OutDir ($name + '-aligned.apk')
$signedApk = Join-Path $OutDir ($name + '-signed.apk')

if ($Clean) {
    foreach ($path in @($unsignedApk, $alignedApk, $signedApk)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

& $apktool b $ProjectDir -o $unsignedApk
if ($LASTEXITCODE -ne 0) {
    throw 'apktool build failed.'
}

& $zipalign -f -p 4 $unsignedApk $alignedApk
if ($LASTEXITCODE -ne 0) {
    throw 'zipalign failed.'
}

Copy-Item -LiteralPath $alignedApk -Destination $signedApk -Force
& $apksigner sign --ks $KeystorePath --ks-key-alias $KeyAlias --ks-pass "pass:$StorePass" --key-pass "pass:$KeyPass" --out $signedApk $alignedApk
if ($LASTEXITCODE -ne 0) {
    throw 'apksigner sign failed.'
}

& $apksigner verify --print-certs $signedApk
if ($LASTEXITCODE -ne 0) {
    throw 'apksigner verify failed.'
}

"unsigned_apk=$unsignedApk"
"aligned_apk=$alignedApk"
"signed_apk=$signedApk"
"keystore=$KeystorePath"

if ($Install) {
    $installArgs = @()
    if ($DeviceSerial) {
        $installArgs += '-s'
        $installArgs += $DeviceSerial
    }
    $installArgs += 'install'
    if ($Reinstall) {
        $installArgs += '-r'
    }
    $installArgs += $signedApk

    & $adb @installArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'adb install failed.'
    }

    "install_device=$DeviceSerial"
}

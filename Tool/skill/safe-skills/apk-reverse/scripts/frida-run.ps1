#requires -Version 7

[CmdletBinding()]
param(
    [string]$Package,

    [string]$Process,

    [string]$RemoteHost = '127.0.0.1:27042',

    [string]$ScriptPath,

    [switch]$Usb,

    [switch]$Spawn,

    [switch]$Pause,

    [switch]$ListDevices,

    [switch]$ListProcesses
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-ToolPath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        # Prefer PATH / Python Scripts next to current interpreter
        $pyScripts = @()
        try {
            $py = (Get-Command python -ErrorAction Stop).Source
            $pyScripts += (Join-Path (Split-Path $py -Parent) 'Scripts')
        } catch {}
        $pyScripts += @(
            (Join-Path $env:APPDATA 'Python\Python312\Scripts')
            (Join-Path $env:APPDATA 'Python\Python313\Scripts')
            (Join-Path $env:APPDATA 'Python\Python314\Scripts')
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\Scripts')
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\Scripts')
        )
        foreach ($dir in $pyScripts) {
            if (-not $dir) { continue }
            $candidate = Join-Path $dir "$Name.exe"
            if (Test-Path -LiteralPath $candidate) {
                return $candidate
            }
        }

        throw "Missing required CLI tool: $Name (install frida-tools: pip install frida-tools)"
    }
    return $cmd.Source
}

$fridaLsDevices = Get-ToolPath -Name 'frida-ls-devices'
$fridaPs = Get-ToolPath -Name 'frida-ps'
$frida = Get-ToolPath -Name 'frida'
$python = Get-Command python -ErrorAction SilentlyContinue

if (-not $python) {
    throw 'Missing required CLI tool: python'
}

$pythonExe = $python.Source

if ($ListDevices) {
    & $pythonExe -c "import frida; [print(f'{d.id}`t{d.type}`t{d.name}') for d in frida.enumerate_devices()]"
    exit $LASTEXITCODE
}

$target = if ($Package) { $Package } elseif ($Process) { $Process } else { '' }
if ([string]::IsNullOrWhiteSpace($target) -and -not $ListProcesses) {
    throw 'Provide -Package or -Process, or use -ListProcesses.'
}

$deviceFlag = if ($Usb) { '-U' } else { '-H' }

if ($ListProcesses) {
    $escapedRemoteHost = $RemoteHost.Replace("'", "''")
    $pythonFlag = if ($Usb) { 'usb' } else { 'remote-host' }
    & $pythonExe -c "import frida; manager = frida.get_device_manager(); device = frida.get_usb_device() if '$pythonFlag' == 'usb' else manager.add_remote_device('$escapedRemoteHost'); [print(f'{p.pid}`t{p.name}') for p in device.enumerate_processes()]"
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "Frida script not found: $ScriptPath"
}

$args = @($deviceFlag)
if (-not $Usb) {
    $args += $RemoteHost
}
if ($Spawn) {
    $args += '-f'
} else {
    $args += '-n'
}
$args += $target
$args += '-l'
$args += $ScriptPath
if (-not $Pause) {
    $args += '--no-pause'
}

& $frida @args
exit $LASTEXITCODE

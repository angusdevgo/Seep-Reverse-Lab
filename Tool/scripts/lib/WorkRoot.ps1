Set-StrictMode -Version Latest

function Resolve-ReverseProjectRoot {
    [CmdletBinding()]
    param(
        [AllowEmptyString()]
        [string]$RequestedRoot = ''
    )

    $root = if ([string]::IsNullOrWhiteSpace($RequestedRoot)) {
        (Get-Location).ProviderPath
    } else {
        $RequestedRoot
    }

    if ([string]::IsNullOrWhiteSpace($root)) {
        throw 'Unable to resolve the analysis project root.'
    }

    if (-not (Test-Path -LiteralPath $root)) {
        New-Item -ItemType Directory -Force -Path $root | Out-Null
    }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "Project root is not a directory: $root"
    }

    $item = Get-Item -LiteralPath $root
    if ($item.PSProvider.Name -ne 'FileSystem') {
        throw "Project root must use the FileSystem provider: $root"
    }

    return $item.FullName
}

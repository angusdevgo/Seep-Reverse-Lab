function Ensure-Pnpm {
    Ensure-NodeRuntime
    $dependency = Get-BootstrapDependency -Name 'pnpm'
    $pnpm = Get-NodeCommandPath -Name 'pnpm'
    $currentVersion = ''
    if ($pnpm) {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $versionOutput = @(& $pnpm --version 2>$null)
            $versionExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        $versionLine = $versionOutput | Select-Object -First 1
        if ($versionExitCode -eq 0 -and $null -ne $versionLine) {
            $currentVersion = ([string]$versionLine).Trim()
        }
    }
    if ($currentVersion -ne [string]$dependency.version) {
        $npm = Get-NodeCommandPath -Name 'npm'
        if ([string]::IsNullOrWhiteSpace($npm)) {
            throw 'npm is not available after Node.js installation.'
        }
        & $npm install -g ([string]$dependency.package)
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install pinned pnpm dependency $($dependency.package)."
        }
    }
}

function Assert-GitCheckoutState {
    param(
        [Parameter(Mandatory = $true)][string]$GitPath,
        [Parameter(Mandatory = $true)][string]$CheckoutPath,
        [Parameter(Mandatory = $true)][string]$PinnedCommit
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $resolvedOutput = @(& $GitPath -C $CheckoutPath rev-parse HEAD 2>$null)
        $resolveExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $resolvedLine = $resolvedOutput | Select-Object -First 1
    $resolvedCommit = if ($null -eq $resolvedLine) { '' } else { ([string]$resolvedLine).Trim() }
    if ($resolveExitCode -ne 0 -or $resolvedCommit -ne $PinnedCommit) {
        throw "Checkout verification failed: expected $PinnedCommit, got $resolvedCommit ($CheckoutPath)"
    }
    try {
        $ErrorActionPreference = 'Continue'
        $status = @(& $GitPath -C $CheckoutPath status --porcelain --untracked-files=all 2>$null)
        $statusExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($statusExitCode -ne 0) {
        throw "Cannot inspect checkout state: $CheckoutPath"
    }
    if ($status.Count -gt 0) {
        throw "Checkout has local changes; refusing to execute it: $CheckoutPath"
    }
}

function Move-BootstrapDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    [IO.Directory]::Move($Source, $Destination)
}

function Ensure-GitCloneInstall {
    param(
        [Parameter(Mandatory = $true)]$Definition,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    $git = Get-FirstCommandPath -Names @('git')
    if ([string]::IsNullOrWhiteSpace($git)) {
        throw 'git is required for git-clone bootstrap definitions.'
    }

    $pinnedCommit = if ($Definition.PSObject.Properties['pinnedCommit']) { [string]$Definition.pinnedCommit } else { '' }
    if ([string]::IsNullOrWhiteSpace($pinnedCommit)) {
        throw "Git capability $($Definition.repo) must define pinnedCommit."
    }

    if ((Test-Path -LiteralPath $TargetPath -PathType Container) -and (Test-Path -LiteralPath (Join-Path $TargetPath '.git'))) {
        Assert-GitCheckoutState -GitPath $git -CheckoutPath $TargetPath -PinnedCommit $pinnedCommit
        return $true
    }
    if (Test-Path -LiteralPath $TargetPath) {
        throw "Install path exists but is not a git checkout: $TargetPath"
    }

    $parent = Split-Path -Path $TargetPath -Parent
    Ensure-DownloadDirectory -Path $parent
    $stagePath = Join-Path $parent ('.reverse-bootstrap-{0}' -f [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stagePath | Out-Null
    try {
        & $git init --quiet $stagePath
        if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
        & $git -C $stagePath remote add origin $Definition.repo
        if ($LASTEXITCODE -ne 0) { throw 'git remote add failed' }
        & $git -C $stagePath fetch --depth 1 origin $pinnedCommit
        if ($LASTEXITCODE -ne 0) { throw 'git fetch failed' }
        & $git -C $stagePath checkout --quiet --detach FETCH_HEAD
        if ($LASTEXITCODE -ne 0) { throw 'git checkout failed' }
        Assert-GitCheckoutState -GitPath $git -CheckoutPath $stagePath -PinnedCommit $pinnedCommit
        Move-BootstrapDirectory -Source $stagePath -Destination $TargetPath
        if (-not (Test-Path -LiteralPath (Join-Path $TargetPath '.git') -PathType Container)) {
            throw "Failed to promote staged checkout to $TargetPath"
        }
    }
    finally {
        if (Test-Path -LiteralPath $stagePath) {
            Remove-Item -LiteralPath $stagePath -Recurse -Force
        }
    }

    return $true
}

function Invoke-AnythingAnalyzerPinnedInstall {
    param(
        [Parameter(Mandatory = $true)][string]$RepoDir,
        [Parameter(Mandatory = $true)][string]$PnpmPath,
        [Parameter(Mandatory = $true)][string]$GitPath,
        [Parameter(Mandatory = $true)][string]$PinnedCommit,
        [string]$VsBuildToolsError = ''
    )

    $workspacePath = Join-Path $RepoDir 'pnpm-workspace.yaml'
    $workspaceExisted = Test-Path -LiteralPath $workspacePath -PathType Leaf
    $workspaceBytes = if ($workspaceExisted) { [IO.File]::ReadAllBytes($workspacePath) } else { $null }

    Push-Location $RepoDir
    try {
        Approve-AnythingAnalyzerBuildScripts -RepoDir $RepoDir
        if (-not (Test-AnythingAnalyzerElectronHealthy -RepoDir $RepoDir -PnpmPath $PnpmPath)) {
            $nodeModules = Join-Path $RepoDir 'node_modules'
            Remove-Item -LiteralPath $nodeModules -Recurse -Force -ErrorAction SilentlyContinue
        }

        & $PnpmPath install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) {
            if ($VsBuildToolsError) { throw "pnpm install failed for anything-analyzer. Visual Studio Build Tools auto-install also failed earlier: $VsBuildToolsError" }
            throw 'pnpm install failed for anything-analyzer.'
        }
        & $PnpmPath rebuild electron esbuild better-sqlite3
        if ($LASTEXITCODE -ne 0) {
            if ($VsBuildToolsError) { throw "pnpm rebuild failed for anything-analyzer. Visual Studio Build Tools auto-install also failed earlier: $VsBuildToolsError" }
            throw 'pnpm rebuild failed for anything-analyzer.'
        }
        if (-not (Test-AnythingAnalyzerElectronHealthy -RepoDir $RepoDir -PnpmPath $PnpmPath)) {
            throw 'anything-analyzer Electron dependency is still unhealthy after pnpm rebuild.'
        }
    }
    finally {
        Pop-Location
        if ($workspaceExisted) {
            [IO.File]::WriteAllBytes($workspacePath, $workspaceBytes)
        }
        elseif (Test-Path -LiteralPath $workspacePath) {
            Remove-Item -LiteralPath $workspacePath -Force
        }
    }

    Assert-GitCheckoutState -GitPath $GitPath -CheckoutPath $RepoDir -PinnedCommit $PinnedCommit
}

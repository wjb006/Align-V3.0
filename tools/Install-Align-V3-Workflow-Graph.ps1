# Align V3.0 workflow graph installer and verification runner.
# The checkout is found from this script's own folder, so it can be launched
# from any directory. It switches only the local checkout to the feature
# branch. It never deploys or changes hosting/DNS.
[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$FeatureBranch = "codex/v3-workflow-graph-installer",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$RepoSlug = "wjb006/Align-V3.0"
$LogRoot = Join-Path $env:LOCALAPPDATA "AlignV3\WorkflowGraphInstaller"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RunRoot = Join-Path $LogRoot $Stamp
$LogFile = Join-Path $RunRoot "install.log"
$BackupRoot = Join-Path $RunRoot "backup"
$OriginalBranch = $null
$Switched = $false
$Passed = $false

New-Item -ItemType Directory -Path $RunRoot -Force | Out-Null
Start-Transcript -Path $LogFile -Force | Out-Null

function Write-Result([string]$Name, [bool]$Ok, [string]$Detail) {
    $mark = if ($Ok) { "[PASS]" } else { "[FAIL]" }
    Write-Host "$mark $Name - $Detail" -ForegroundColor $(if ($Ok) { "Green" } else { "Red" })
}

function Find-GitTopLevel {
    param([string]$Start)
    if ([string]::IsNullOrWhiteSpace($Start)) { return $null }
    if (-not (Test-Path -LiteralPath $Start)) { return $null }
    $resolved = (Resolve-Path -LiteralPath $Start).Path
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $toplevel = & git -C $resolved rev-parse --show-toplevel 2>$null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0 -or [string]::IsNullOrWhiteSpace([string]$toplevel)) { return $null }
    return ([string]$toplevel).Trim()
}

function Find-AlignRepositoryRoot {
    param([string]$Requested)
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git was not found on PATH, so the Align checkout could not be located."
    }
    $starts = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        # An explicit folder may be the checkout or any directory inside it.
        # Git walks upward to the real root; do not require .git in that exact folder.
        $starts.Add($Requested)
    } else {
        # This script lives inside the checkout. Prefer that over the shell's
        # current folder, which may be a different directory or another repository.
        if ($PSScriptRoot) { $starts.Add($PSScriptRoot) }
        $starts.Add((Get-Location).Path)
    }
    foreach ($start in $starts) {
        $found = Find-GitTopLevel $start
        if ($found) { return $found }
    }
    $looked = ($starts | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ', '
    throw "Could not find the Align checkout: .git was not found above $looked. Pass -RepositoryRoot as a folder inside the wjb006/Align-V3.0 checkout."
}

try {
    $root = Find-AlignRepositoryRoot $RepositoryRoot
    $remote = (& git -C $root remote get-url origin 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $remote -notmatch 'github\.com[:/]wjb006/Align-V3\.0(?:\.git)?$') {
        throw "Wrong repository origin. Expected github.com/wjb006/Align-V3.0; found: $remote"
    }
    Write-Result "Repository identity" $true $remote

    $dirty = (& git -C $root status --porcelain 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect Git working tree." }
    if ($dirty) {
        throw "Working tree is not clean. Commit or safely stash your work before running; no files were changed."
    }
    Write-Result "Working tree" $true "Clean; no local changes will be overwritten."

    $OriginalBranch = (& git -C $root branch --show-current 2>&1 | Out-String).Trim()
    if (-not $OriginalBranch) { throw "Detached HEAD detected. Switch to a named branch first." }

    $backupPaths = @(
        "static/owner-builder.js",
        "static/owner-builder.css",
        "static/owner-builder.html",
        "builder_workflow.py",
        "owner_builder.py",
        "test_owner_builder.py",
        "BUILD_CHECKLIST.md"
    )
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($relative in $backupPaths) {
        $source = Join-Path $root ($relative -replace '/', '\')
        if (Test-Path -LiteralPath $source) {
            $destination = Join-Path $BackupRoot ($relative -replace '/', '\')
            New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $destination -Force
        }
    }
    Write-Result "Backup" $true "Relevant source and test files copied to $BackupRoot"

    & git -C $root fetch origin $FeatureBranch
    if ($LASTEXITCODE -ne 0) { throw "Git fetch failed for origin/$FeatureBranch." }

    $localFeature = (& git -C $root branch --list $FeatureBranch 2>&1 | Out-String).Trim()
    if ($localFeature) {
        & git -C $root switch $FeatureBranch
        if ($LASTEXITCODE -ne 0) { throw "Could not switch to $FeatureBranch." }
        $Switched = $true
        & git -C $root merge --ff-only "origin/$FeatureBranch"
        if ($LASTEXITCODE -ne 0) { throw "Local feature branch cannot fast-forward to origin/$FeatureBranch. No reset was attempted; review the branch manually." }
    } else {
        & git -C $root switch --create $FeatureBranch --track "origin/$FeatureBranch"
        if ($LASTEXITCODE -ne 0) { throw "Could not switch to $FeatureBranch." }
        $Switched = $true
    }
    Write-Result "Install branch" $true "Checked out $FeatureBranch locally; no production deployment performed."

    if (-not $SkipTests) {
        Push-Location -LiteralPath $root
        try {
            $python = Get-Command py -ErrorAction SilentlyContinue
            if ($python) {
                & py -3.12 -m pytest -q
                $testExit = $LASTEXITCODE
                if ($testExit -ne 0) {
                    # Fall back to the active Python only if the Python 3.12 launcher is unavailable.
                    $versionProbe = & py -3.12 --version 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        $pythonExe = Get-Command python -ErrorAction SilentlyContinue
                        if (-not $pythonExe) { throw "Python 3.12 and python were not found." }
                        & python -m pytest -q
                        $testExit = $LASTEXITCODE
                    }
                }
            } else {
                $pythonExe = Get-Command python -ErrorAction SilentlyContinue
                if (-not $pythonExe) { throw "Python was not found. Install Python 3.12 and pytest, then rerun." }
                & python -m pytest -q
                $testExit = $LASTEXITCODE
            }
        } finally {
            Pop-Location
        }
        if ($testExit -ne 0) { throw "Pytest failed with exit code $testExit." }
        Write-Result "Regression tests" $true "pytest completed successfully."
    } else {
        Write-Result "Regression tests" $false "Skipped by explicit -SkipTests switch; install is not verified."
    }

    $Passed = -not $SkipTests
    if ($Passed) {
        Write-Result "Overall" $true "Feature branch installed locally and regression suite passed."
    } else {
        Write-Result "Overall" $false "Feature branch checked out, but verification was skipped."
    }
}
catch {
    Write-Result "Overall" $false $_.Exception.Message
    if ($Switched -and $OriginalBranch) {
        Write-Host "Rolling back local checkout to $OriginalBranch ..."
        $rollbackRoot = if ($root) { $root } else { $RepositoryRoot }
        & git -C $rollbackRoot switch $OriginalBranch
        if ($LASTEXITCODE -eq 0) {
            Write-Result "Rollback" $true "Returned to $OriginalBranch. Backup retained at $BackupRoot"
        } else {
            Write-Result "Rollback" $false "Automatic branch switch failed. Backup retained at $BackupRoot"
        }
    }
    Write-Host "Log: $LogFile"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}

Write-Host ""
Write-Host "Log: $LogFile"
Write-Host "Backup: $BackupRoot"
if (-not $Passed) { exit 1 }
exit 0

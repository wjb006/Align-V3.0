# Align V3.0 workflow graph installer and verification runner
# Run from the root of a clean clone of https://github.com/wjb006/Align-V3.0
# This switches only the local checkout to the feature branch. It never deploys or changes hosting/DNS.
[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Get-Location).Path,
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

try {
    $root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
    if (-not (Test-Path (Join-Path $root ".git"))) {
        throw "RepositoryRoot is not a Git checkout: $root"
    }
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
    } else {
        & git -C $root switch --create $FeatureBranch --track "origin/$FeatureBranch"
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not switch to $FeatureBranch." }
    $Switched = $true
    Write-Result "Install branch" $true "Checked out $FeatureBranch locally; no production deployment performed."

    if (-not $SkipTests) {
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
        & git -C $RepositoryRoot switch $OriginalBranch
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

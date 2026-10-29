#requires -Version 5.1
<#
.SYNOPSIS
  Control the live Align folder.

.DESCRIPTION
  The live folder is this directory (also available as C:\Align\Live).
  An update replaces tracked files here. It does not copy the app into
  another folder, and it leaves the database, credentials and virtual
  environment in place.

.EXAMPLE
  .\align.ps1 update
  .\align.ps1 start
  .\align.ps1 status
  .\align.ps1 stop
  .\align.ps1 wifi
  .\align.ps1 studio
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [Alias('Command')]
    [ValidateSet('update', 'start', 'stop', 'status', 'wifi', 'studio')]
    [string]$Section = 'start',
    [int]$Port = 8001
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ----- Section: Live folder -----
$LiveRoot = [IO.Path]::GetFullPath($PSScriptRoot)
if ($LiveRoot -match '(?i)\\Align\\Align_App\\') {
    throw "This is a nested copy, not the live folder: $LiveRoot. Run C:\Align\Live\align.ps1."
}
Set-Location -LiteralPath $LiveRoot

$stateDir = Join-Path $LiveRoot '.align'
$statePath = Join-Path $stateDir 'server.json'
$outPath = Join-Path $stateDir 'server-out.log'
$errPath = Join-Path $stateDir 'server-err.log'
$python = Join-Path $LiveRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
}

function Read-State {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    try { return Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json }
    catch { return $null }
}

function Get-Health($state) {
    if (-not $state) { return $null }
    try {
        return Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/health" -f $state.port) -TimeoutSec 3
    } catch { return $null }
}

function Test-PortHealthy([string]$CheckPort) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CheckPort/api/health" -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Test-AlignProcess([int]$statePid) {
    $record = Get-CimInstance Win32_Process -Filter "ProcessId=$statePid" -ErrorAction SilentlyContinue
    if (-not $record -or -not $record.CommandLine) { return $false }
    $launchPath = (Join-Path $LiveRoot 'launch.py').ToLowerInvariant()
    $commandLine = $record.CommandLine.ToLowerInvariant()
    if ($commandLine.Contains($launchPath)) { return $true }
    $exe = [string]$record.ExecutablePath
    return $commandLine.Contains('launch.py') -and $exe -and $exe.ToLowerInvariant().StartsWith($LiveRoot.ToLowerInvariant())
}

function Write-Status($state, $health) {
    if (-not $state) { Write-Host 'Align is not running (no state file).'; return }
    if ($health) {
        Write-Host ("Align is running (PID {0}, port {1}, mode {2})." -f $state.pid, $state.port, $health.mode)
        Write-Host ("Build {0}; database available={1}; migrations available={2}, applied={3}." -f `
            $health.version.build, $health.database.available, $health.migrations.available, $health.migrations.applied)
    } else {
        Write-Host ("Align state exists for PID {0}, but /api/health is unavailable." -f $state.pid) -ForegroundColor Yellow
    }
}

# ----- Section: Update -----
# Replaces tracked files in the live folder. Databases, keys and .venv stay.
function Update-Live {
    foreach ($checkPort in @('8001', '8010', [string]$Port)) {
        if (Test-PortHealthy $checkPort) {
            throw "Align is still running on port $checkPort. Run .\align.ps1 stop, then update again."
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $LiveRoot '.git') -PathType Container)) {
        throw "The live folder has no Git history: $LiveRoot"
    }
    Write-Host "Updating $LiveRoot"
    $remoteHead = @(& git ls-remote --symref origin HEAD 2>$null)
if ($LASTEXITCODE -ne 0) { throw 'Could not query the origin remote.' }
$headLine = $remoteHead | Where-Object { "$_" -match '^ref: refs/heads/(.+)\s+HEAD$' } | Select-Object -First 1
if (-not $headLine) { throw 'Could not determine the origin default branch.' }
$defaultBranch = [regex]::Match("$headLine", '^ref: refs/heads/(.+)\s+HEAD$').Groups[1].Value
Write-Host "Updating from origin/$defaultBranch using fast-forward only."
& git pull --ff-only origin $defaultBranch
    if ($LASTEXITCODE -ne 0) { throw 'The live folder could not be updated. Local changes may need attention first.' }
    if ($python -and (Test-Path -LiteralPath $python -PathType Leaf)) {
        & $python -c "import app, owner_builder; app.initialise_database(); owner_builder.config(app.DATABASE); print('existing database updated')"
        if ($LASTEXITCODE -ne 0) { throw 'The existing database could not be updated.' }
    } else {
        Write-Host 'Database left unchanged: no virtual environment Python was found.'
    }
    Write-Host 'Live folder updated. Management Studio uses this same folder, so it does not need a second copy.'
}

# ----- Section: Start, stop, status -----
function Start-Live {
    if (-not $python) { throw 'Python 3.10 or later was not found. Run Install-Align.bat or install Python.' }
    if (Get-Health (Read-State)) { throw 'Align is already running. Use .\align.ps1 status or stop first.' }
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    Remove-Item -LiteralPath $outPath, $errPath -Force -ErrorAction SilentlyContinue
    $oldBetaMode = $env:ALIGN_BETA_MODE
    $oldPort = $env:ALIGN_PORT
    $oldTransportEnabled = $env:ALIGN_TRANSPORT_ENABLED
    try {
        $env:ALIGN_BETA_MODE = '0'
        $env:ALIGN_PORT = [string]$Port
        if ($null -eq $oldTransportEnabled -and $env:ALIGN_OTP_URL) {
            $env:ALIGN_TRANSPORT_ENABLED = '1'
        }
        $process = Start-Process -FilePath $python -ArgumentList @('launch.py') -WorkingDirectory $LiveRoot `
            -RedirectStandardOutput $outPath -RedirectStandardError $errPath -PassThru -WindowStyle Hidden
        @{ pid = $process.Id; port = $Port; transport_enabled = ($env:ALIGN_TRANSPORT_ENABLED -eq '1'); started_at = [DateTime]::UtcNow.ToString('o') } |
            ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    } finally {
        if ($null -eq $oldBetaMode) { Remove-Item Env:ALIGN_BETA_MODE -ErrorAction SilentlyContinue } else { $env:ALIGN_BETA_MODE = $oldBetaMode }
        if ($null -eq $oldPort) { Remove-Item Env:ALIGN_PORT -ErrorAction SilentlyContinue } else { $env:ALIGN_PORT = $oldPort }
        if ($null -eq $oldTransportEnabled) { Remove-Item Env:ALIGN_TRANSPORT_ENABLED -ErrorAction SilentlyContinue } else { $env:ALIGN_TRANSPORT_ENABLED = $oldTransportEnabled }
    }

    $state = Read-State
    $health = $null
    for ($i = 0; $i -lt 20 -and -not $health; $i++) {
        Start-Sleep -Seconds 1
        $health = Get-Health $state
        if ($process.HasExited) { break }
    }
    if (-not $health) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
        throw 'Align did not become healthy. See .align\server-out.log and .align\server-err.log.'
    }
    Write-Status $state $health
}

function Stop-Live {
    $state = Read-State
    if (-not $state) { Write-Host 'Align is not running.'; return }
    $process = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
    if ($process -and (Test-AlignProcess ([int]$state.pid))) {
        Stop-Process -Id $process.Id -Force
        Write-Host ("Stopped Align (PID {0})." -f $process.Id)
    } elseif ($process) {
        Write-Host ("State file PID {0} does not belong to Align; leaving it running." -f $state.pid) -ForegroundColor Yellow
    } else {
        Write-Host ("Align process {0} is already stopped." -f $state.pid)
    }
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
}

function Start-Wifi {
    if (-not $python -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Python was not found in the live folder virtual environment.'
    }
    $env:ALIGN_BETA_MODE = '0'
    & $python (Join-Path $LiveRoot 'launch.py') --network
}

# ----- Section: Management Studio -----
# The installed EXE starts this live folder. Replacing files here updates what it runs.
function Show-Studio {
    $exe = 'C:\Align\Align_Management_Studio\Align-Management-Studio.exe'
    Write-Host "Live folder: $LiveRoot"
    if (Test-Path -LiteralPath $exe -PathType Leaf) {
        Write-Host "Management Studio: $exe"
        Write-Host 'Open that program. It uses the live folder, so there is no separate copy to update.'
    } else {
        Write-Host "Management Studio EXE was not found at $exe"
    }
}

switch ($Section) {
    'update' { Update-Live }
    'start'  { Start-Live }
    'stop'   { Stop-Live }
    'status' { Write-Status (Read-State) (Get-Health (Read-State)) }
    'wifi'   { Start-Wifi }
    'studio' { Show-Studio }
}

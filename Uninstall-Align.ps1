#requires -Version 5.1
<#
Build 156 conservative uninstaller.

Default behaviour:
  - stops/removes .venv
  - removes installer/launcher files
  - preserves align.sqlite3
  - preserves user data and the rest of the source tree

Use -DeleteDatabase only when the Align database should also be removed.
#>
param(
    [switch]$DeleteDatabase
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
$LogDir = Join-Path $Root 'install-logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("uninstall-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

function Write-Log {
    param([string]$Message,[string]$Level='INFO')
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$Level,$Message
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Stop-Uninstall {
    param([string]$Message)
    Write-Log $Message 'ERROR'
    Write-Host ''
    Write-Host 'ALIGN UNINSTALL FAILED' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    Write-Host "Log: $LogFile" -ForegroundColor Yellow
    exit 1
}

function Remove-Safely {
    param([string]$Path,[switch]$Recurse)
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Log "Already absent: $Path"
        return
    }
    try {
        if ($Recurse) { Remove-Item -LiteralPath $Path -Recurse -Force }
        else { Remove-Item -LiteralPath $Path -Force }
        Write-Log "Removed: $Path"
    } catch {
        throw "Could not remove '$Path'. Close Align and any terminals/editors using the file, then retry. $($_.Exception.Message)"
    }
}

Write-Log 'Starting Align V3.0 Build 156 uninstall.'
Write-Log "Root: $Root"
Write-Log "DeleteDatabase switch: $DeleteDatabase"

try {
    if ($env:OS -ne 'Windows_NT') { throw 'This uninstaller is intended for Windows.' }

    $database = Join-Path $Root 'align.sqlite3'
    $venv = Join-Path $Root '.venv'

    $databaseDeleteConfirmed = $false
    if ($DeleteDatabase) {
        Write-Host ''
        Write-Host 'WARNING: You explicitly requested database deletion.' -ForegroundColor Yellow
        Write-Host 'This permanently removes local Align planner data stored in align.sqlite3.' -ForegroundColor Yellow
        $confirmation = Read-Host 'Type DELETE ALIGN DATABASE to continue'
        if ($confirmation -cne 'DELETE ALIGN DATABASE') {
            throw 'Database deletion was requested but the confirmation text did not match. No database was deleted.'
        }
        $databaseDeleteConfirmed = $true
        Write-Log 'Explicit database deletion confirmed.' 'WARN'
    } else {
        Write-Log 'Database protection enabled. align.sqlite3 will be preserved.'
    }

    Write-Log 'Checking whether Align is running...'
    $portOwners = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
        $portOwners = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        Write-Log 'Could not inspect port 8001; continuing.' 'WARN'
    }
    foreach ($pidValue in $portOwners) {
        if ($pidValue -and $pidValue -ne $PID) {
            $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
            if ($process) {
                Write-Log "Port 8001 is currently owned by PID $pidValue ($($process.ProcessName))." 'WARN'
                Write-Host "Align may still be running. Close it before continuing." -ForegroundColor Yellow
                $answer = Read-Host 'Type STOP ALIGN to attempt to stop that process, or press Enter to cancel'
                if ($answer -cne 'STOP ALIGN') {
                    throw 'Uninstall cancelled because an application is still listening on port 8001.'
                }
                Stop-Process -Id $pidValue -Force -ErrorAction Stop
                Write-Log "Stopped process $pidValue."
            }
        }
    }

    # Resolve every prerequisite before removing the environment or launchers.
    # A missed typed confirmation must leave the installation fully usable.
    if ($DeleteDatabase -and -not $databaseDeleteConfirmed) {
        throw 'Database deletion was not confirmed. No installation files were removed.'
    }
    if ($DeleteDatabase -and (Test-Path -LiteralPath $database) -and (Get-Item -LiteralPath $database -Force).PSIsContainer) {
        throw 'The database path is not a file. No installation files were removed.'
    }

    $launcherFiles = @(
        'Install-Align.ps1',
        'Install-Align.bat',
        'Start-Align.bat',
        'Start Align.bat',
        'Start Align on Wi-Fi.bat',
        'Start Align Remote Access.bat',
        'Start Align Transport.bat',
        'Install Align Add-ons.bat',
        'Install-Align-AddOns.ps1',
        'Uninstall-Align.ps1',
        'Uninstall-Align.bat',
        'README-INSTALL.md'
    )

    Write-Log 'Removing Build 156 virtual environment...'
    if (Test-Path -LiteralPath $venv) {
        Remove-Safely $venv -Recurse
    } else {
        Write-Log '.venv is already absent.'
    }

    if ($DeleteDatabase) {
        if (Test-Path -LiteralPath $database) {
            Remove-Safely $database
            Write-Log 'align.sqlite3 deleted.' 'WARN'
        } else {
            Write-Log 'align.sqlite3 was already absent.'
        }
        $backupFiles = Get-ChildItem -LiteralPath $Root -Filter 'align.sqlite3.backup_*' -File -ErrorAction SilentlyContinue
        foreach ($backup in $backupFiles) {
            Remove-Safely $backup.FullName
            Write-Log "Deleted database backup: $($backup.Name)" 'WARN'
        }
    } else {
        if (Test-Path -LiteralPath $database) {
            Write-Log 'PRESERVED: align.sqlite3'
        } else {
            Write-Log 'align.sqlite3 was not present.' 'WARN'
        }
    }

    Write-Log 'Removing installer and launcher files...'
    foreach ($file in $launcherFiles) {
        $path = Join-Path $Root $file
        if (Test-Path -LiteralPath $path) {
            Remove-Safely $path
        }
    }

    Write-Log 'Uninstall completed successfully.'
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ' ALIGN UNINSTALL COMPLETE' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ''
    if ($DeleteDatabase) {
        Write-Host 'Virtual environment: removed'
        Write-Host 'Database:            deleted (explicitly requested)'
    } else {
        Write-Host 'Virtual environment: removed'
        Write-Host 'Database:            PRESERVED' -ForegroundColor Cyan
        Write-Host "Database path:       $database"
    }
    Write-Host ''
    Write-Host 'The remaining Align source files were intentionally left in place.'
    Write-Host "Log: $LogFile" -ForegroundColor DarkGray
    exit 0
} catch {
    Stop-Uninstall $_.Exception.Message
}

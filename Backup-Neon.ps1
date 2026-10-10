<#
.SYNOPSIS  Backs up the hosted Neon database to Master\Backups, and can schedule a daily run.
.DESCRIPTION
  -SetCredential  Prompts (hidden) for the Neon connection string and stores it encrypted for
                  THIS Windows user only (DPAPI). It is never printed or written in plain text.
  (no switch)     Runs backup_neon.py using the stored credential.
  -Schedule       Registers a daily Windows scheduled task (default 02:30) for the current user.
  -Unschedule     Removes that task.
  -CopyTo <dir>   Also copies each new backup to another folder (OneDrive or an external drive); combine with -Schedule.
#>
param(
    [switch]$SetCredential,
    [switch]$Schedule,
    [switch]$Unschedule,
    [string]$At = '02:30',
    [int]$Keep = 14,
    [string]$CopyTo,
    [string]$MasterDir = (Join-Path (Split-Path -Parent $PSScriptRoot) 'Master'),
    [string]$CredentialPath
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $MasterDir)) {
    $candidates = @((Join-Path $PSScriptRoot 'Master'), (Join-Path (Split-Path -Parent $PSScriptRoot) 'App\Align App\Master'), 'C:\Align\App\Align App\Master')
    $MasterDir = ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
    if (-not $MasterDir) { throw 'Could not find the Master folder. Pass -MasterDir <path>.' }
}
if (-not $CredentialPath) { $CredentialPath = Join-Path $MasterDir '.neon_dsn.xml' }
$taskName = 'Align Neon Backup'

if ($SetCredential) {
    $secure = Read-Host 'Paste the Neon connection string (input hidden)' -AsSecureString
    if ($secure.Length -eq 0) { throw 'Nothing entered; nothing saved.' }
    $secure | Export-Clixml -LiteralPath $CredentialPath
    Write-Host "Saved encrypted credential for $env:USERNAME."
    return
}
if ($Unschedule) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$taskName'."
    return
}
if ($Schedule) {
    if (-not (Test-Path -LiteralPath $CredentialPath)) { throw 'Run .\Backup-Neon.ps1 -SetCredential first.' }
    $ps = (Get-Command powershell.exe).Source
    $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Keep ' + $Keep + $(if ($CopyTo) { ' -CopyTo "' + $CopyTo + '"' } else { '' })
    $action = New-ScheduledTaskAction -Execute $ps -Argument $args -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Scheduled '$taskName' daily at $At (runs as $env:USERNAME, catches up if the PC was off)."
    return
}

if (-not (Test-Path -LiteralPath $CredentialPath)) { throw 'No stored credential. Run .\Backup-Neon.ps1 -SetCredential first.' }
$secure = Import-Clixml -LiteralPath $CredentialPath
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
$python = Join-Path $MasterDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python.exe).Source }
$out = Join-Path $MasterDir 'Backups\Neon'
& $python (Join-Path $PSScriptRoot 'backup_neon.py') --out $out --keep $Keep
$code = $LASTEXITCODE
if ($code -eq 0 -and $CopyTo) {
    New-Item -ItemType Directory -Force -Path $CopyTo | Out-Null
    $latest = Get-ChildItem -LiteralPath $out -Filter 'align-neon-*.json.gz' | Sort-Object Name | Select-Object -Last 1
    Copy-Item -LiteralPath $latest.FullName -Destination $CopyTo -Force
    Get-ChildItem -LiteralPath $CopyTo -Filter 'align-neon-*.json.gz' | Sort-Object Name | Select-Object -SkipLast $Keep | Remove-Item -Force
    Write-Host "Copied $($latest.Name) to $CopyTo"
}
Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
exit $code

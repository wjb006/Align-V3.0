<#
.SYNOPSIS  Shows the latest Render deploys for Align and exits non-zero if the newest one failed.
Usage: .\Check-Deploy.ps1 [-ServiceId srv-...]
#>
param([string]$ServiceId = 'srv-dagshc6k1f9s73dout5g')
if (-not (Get-Command render -ErrorAction SilentlyContinue)) { Write-Error 'The Render CLI is not installed.'; exit 2 }
$lines = render deploys list $ServiceId -o text --confirm 2>&1
$lines | Select-Object -First 4
$first = $lines | Select-Object -Skip 1 -First 1
if ($first -match '^\s*(Live|Deploying|Building|Update in progress)') { exit 0 }
if ($first -match 'fail|cancel') { Write-Host 'Newest deploy did not succeed.' -ForegroundColor Red; exit 1 }
exit 0

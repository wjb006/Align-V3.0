<#
.SYNOPSIS  Starts Align for other devices on your home Wi-Fi.
#>
& (Join-Path $PSScriptRoot 'align.ps1') -Section wifi
exit $LASTEXITCODE

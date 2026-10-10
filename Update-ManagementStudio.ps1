#requires -Version 5.1
<#
.SYNOPSIS
  Updates the live Align folder. Management Studio launches that folder,
  so the program does not keep a second copy of the app.
#>
& (Join-Path $PSScriptRoot 'align.ps1') -Section update
exit $LASTEXITCODE

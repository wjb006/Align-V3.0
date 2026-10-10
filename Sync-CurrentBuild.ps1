# The live folder is updated in place. This name remains so older shortcuts keep working.
& (Join-Path $PSScriptRoot 'align.ps1') -Section update
exit $LASTEXITCODE

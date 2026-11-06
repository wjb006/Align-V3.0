# Build the isolated Align V3.0 test executable.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Previous = $env:ALIGN_TEST_BUILD
try {
    $env:ALIGN_TEST_BUILD = "1"
    & (Join-Path $PSScriptRoot "build_windows.ps1")
    if ($LASTEXITCODE -ne 0) { throw "The Align V3.0 test build failed." }
    $Built = Join-Path $Root "dist\Align V3.0 Test\Align V3.0 Test.exe"
    if (-not (Test-Path $Built)) { throw "The isolated test executable was not created: $Built" }
    Write-Host "Isolated test build ready: $Built" -ForegroundColor Green
} finally {
    if ($null -eq $Previous) {
        Remove-Item Env:ALIGN_TEST_BUILD -ErrorAction SilentlyContinue
    } else {
        $env:ALIGN_TEST_BUILD = $Previous
    }
}

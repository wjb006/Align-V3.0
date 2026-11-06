[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TesseractHome = $env:TESSERACT_INSTALL_DIR,
    [switch]$KeepBuildFiles = $true
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Stop-Build([string]$Message) {
    Write-Host ""
    Write-Host "BUILD STOPPED: $Message" -ForegroundColor Red
    throw $Message
}
function Run-Checked([string]$File, [string[]]$Args, [string]$Failure) {
    & $File @Args
    if ($LASTEXITCODE -ne 0) { Stop-Build "$Failure (exit code $LASTEXITCODE)" }
}

Write-Host ""
Write-Host "ALIGN V3.0 — ISOLATED WINDOWS TEST BUILDER" -ForegroundColor Cyan
Write-Host "Creates a separate test build. Your normal Align installation and database are not changed."

try {
    $RepositoryRoot = (& git -C $RepositoryRoot rev-parse --show-toplevel 2>$null).Trim()
} catch { Stop-Build "Git repository not found. Run this from your Align checkout or pass -RepositoryRoot." }
if (-not $RepositoryRoot -or -not (Test-Path (Join-Path $RepositoryRoot ".git"))) {
    Stop-Build "Could not resolve the Align Git repository."
}
$Repo = (Resolve-Path $RepositoryRoot).Path
$Branch = "test/align-v3-ready-20261106"
$BuildParent = Join-Path $env:LOCALAPPDATA "Align-Builds"
$BuildRoot = Join-Path $BuildParent ("Align-V3-Test-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

foreach ($Tool in @("git", "py", "node", "go")) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) { Stop-Build "$Tool is required but was not found on PATH." }
}
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { Stop-Build "Python 3.12 is required." }

if (-not $TesseractHome) {
    $TessCommand = Get-Command tesseract.exe -ErrorAction SilentlyContinue
    if ($TessCommand) { $TesseractHome = Split-Path -Parent $TessCommand.Source }
}
if (-not $TesseractHome) {
    $Candidates = @(
        (Join-Path $env:ProgramFiles "Tesseract-OCR"),
        (Join-Path ([Environment]::GetEnvironmentVariable("ProgramFiles(x86)")) "Tesseract-OCR")
    )
    $TesseractHome = $Candidates | Where-Object {
        $_ -and (Test-Path (Join-Path $_ "tesseract.exe"))
    } | Select-Object -First 1
}
if (-not $TesseractHome -or
    -not (Test-Path (Join-Path $TesseractHome "tesseract.exe")) -or
    -not (Test-Path (Join-Path $TesseractHome "tessdata\eng.traineddata"))) {
    Stop-Build "Tesseract OCR plus English data is required. Install it, then rerun with -TesseractHome 'C:\Program Files\Tesseract-OCR'."
}
$env:TESSERACT_INSTALL_DIR = (Resolve-Path $TesseractHome).Path
Write-Host "Tesseract: $env:TESSERACT_INSTALL_DIR" -ForegroundColor Green

New-Item -ItemType Directory -Force -Path $BuildParent | Out-Null
if (Test-Path $BuildRoot) { Stop-Build "Build folder already exists: $BuildRoot" }
$WorktreeCreated = $false
try {
    Write-Host ""
    Write-Host "Fetching $Branch from GitHub..." -ForegroundColor Cyan
    Run-Checked "git" @("-C", $Repo, "fetch", "origin", $Branch) "Git fetch failed"
    Run-Checked "git" @("-C", $Repo, "worktree", "add", "--detach", $BuildRoot, "origin/$Branch") "Could not create isolated worktree"
    $WorktreeCreated = $true
    Set-Location $BuildRoot

    Write-Host ""
    Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
    Run-Checked "py" @("-3.12", "-m", "pip", "install", "--upgrade", "pip", "pyinstaller") "Could not install build tools"
    Run-Checked "py" @("-3.12", "-m", "pip", "install", "-r", "requirements.txt") "Could not install Align dependencies"

    Write-Host ""
    Write-Host "Running Align regression tests..." -ForegroundColor Cyan
    $Tests = @(
        "test_test_build_isolation.py","test_rota_ocr_provider.py","test_work_setup.py",
        "test_work_rota_import.py","test_desktop_auth.py","test_desktop_auth_http.py",
        "test_desktop_programme.py","test_desktop_update.py","test_owner_builder.py",
        "test_admin_owner_status.py","test_studio150.py","test_asset_studio_migration.py",
        "test_studio_update.py","test_studio_deploy.py","test_studio_render_deploy.py",
        "test_personal_planner.py","test_post_event_travel.py","test_personal_otp.py",
        "test_transport_build149.py","test_here_transit.py","test_here_quota.py",
        "test_hosted_travel.py","test_hosted_persistence.py","test_month_calendar.py",
        "test_event_calendar_feed.py","test_week_reminders151.py","test_builder_finance.py",
        "test_builder_formatting.py","test_local_backup.py","test_ui_polish.py",
        "test_calendar_appearance.py","test_phone_push.py","test_credential_recovery.py"
    )
    Run-Checked "py" (@("-3.12", "-m", "unittest") + $Tests) "Align regression tests did not pass"

    Write-Host ""
    Write-Host "Checking JavaScript..." -ForegroundColor Cyan
    Run-Checked "node" @("--check", "static/work-rota.js") "Work rota JavaScript check failed"
    Run-Checked "node" @("--check", "static/desktop.js") "Desktop JavaScript check failed"

    Write-Host ""
    Write-Host "Testing Go launcher..." -ForegroundColor Cyan
    Push-Location (Join-Path $BuildRoot "studio-launcher")
    try { Run-Checked "go" @("test", "./...") "Go launcher tests failed" }
    finally { Pop-Location }

    Write-Host ""
    Write-Host "Building the isolated Windows executable..." -ForegroundColor Cyan
    Run-Checked "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $BuildRoot "desktop\build_test_windows.ps1")) "Windows executable build failed"

    $AppRoot = Join-Path $BuildRoot "dist\Align V3.0 Test"
    $RequiredFiles = @(
        (Join-Path $AppRoot "Align V3.0 Test.exe"),
        (Join-Path $AppRoot "ocr\tesseract.exe"),
        (Join-Path $AppRoot "ocr\tessdata\eng.traineddata"),
        (Join-Path $BuildRoot "installer\windows\Install-Align-Test.ps1"),
        (Join-Path $BuildRoot "installer\windows\README-Test.md")
    )
    foreach ($File in $RequiredFiles) {
        if (-not (Test-Path $File)) { Stop-Build "Required build file missing: $File" }
    }

    Write-Host ""
    Write-Host "Packaging the test ZIP..." -ForegroundColor Cyan
    $PackageRoot = Join-Path $BuildRoot "dist\Align-V3.0-Test"
    $PackageApp = Join-Path $PackageRoot "Align V3.0 Test"
    New-Item -ItemType Directory -Force -Path $PackageApp | Out-Null
    Copy-Item (Join-Path $AppRoot "*") $PackageApp -Recurse -Force
    Copy-Item (Join-Path $BuildRoot "installer\windows\Install-Align-Test.ps1") $PackageRoot
    Copy-Item (Join-Path $BuildRoot "installer\windows\README-Test.md") (Join-Path $PackageRoot "README.md")
    Copy-Item (Join-Path $BuildRoot "desktop\README.md") (Join-Path $PackageRoot "BUILD.md")
    $Commit = (& git -C $BuildRoot rev-parse --short HEAD).Trim()
    $Marker = @("ALIGN V3.0 TEST BUILD", "Branch: $Branch", "Commit: $Commit", "NOT A PRODUCTION RELEASE")
    $Marker | Set-Content (Join-Path $PackageRoot "TEST-BUILD.txt") -Encoding UTF8

    $Zip = Join-Path $BuildRoot "dist\Align-V3.0-Test-Windows.zip"
    if (Test-Path $Zip) { Remove-Item $Zip -Force }
    Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $Zip -CompressionLevel Optimal
    if (-not (Test-Path $Zip)) { Stop-Build "ZIP package was not created." }

    Write-Host ""
    Write-Host "BUILD COMPLETE" -ForegroundColor Green
    Write-Host "Package: $Zip" -ForegroundColor Green
    Write-Host "Installer inside ZIP: Install-Align-Test.ps1" -ForegroundColor Green
    Write-Host "Test data: $env:LOCALAPPDATA\Align-Test" -ForegroundColor Green
    Write-Host "Test address: http://127.0.0.1:8011/desktop" -ForegroundColor Green
    Write-Host "Normal Align data was not opened or changed." -ForegroundColor Green
    Start-Process explorer.exe -ArgumentList @("/select,", $Zip)
} finally {
    Set-Location $Repo
    if ($WorktreeCreated) {
        if ($KeepBuildFiles) {
            Write-Host "Build source retained at: $BuildRoot" -ForegroundColor DarkGray
        } else {
            & git -C $Repo worktree remove --force $BuildRoot
        }
    }
}

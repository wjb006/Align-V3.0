[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TesseractHome = $env:TESSERACT_INSTALL_DIR
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host ""
Write-Host "ALIGN V3.0 - ISOLATED WINDOWS TEST BUILDER" -ForegroundColor Cyan
Write-Host "This build uses separate test files and data. Your normal Align database is not changed."

# Resolve the repository root even when this script is launched from another folder.
$Repo = (& git -C $RepositoryRoot rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $Repo) { throw "Align Git repository not found. Pass -RepositoryRoot with your local repository path." }
$Repo = $Repo.Trim()
$Branch = "test/align-v3-build-158"
$BuildParent = Join-Path $env:LOCALAPPDATA "Align-Builds"
$BuildRoot = Join-Path $BuildParent ("Align-V3-Test-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

foreach ($ToolName in @("git", "py", "node", "go")) {
    if (-not (Get-Command $ToolName -ErrorAction SilentlyContinue)) { throw "$ToolName is required but was not found on PATH." }
}
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required." }

# Find Tesseract and its English language model.
if (-not $TesseractHome) {
    $TesseractCommand = Get-Command tesseract.exe -ErrorAction SilentlyContinue
    if ($TesseractCommand) { $TesseractHome = Split-Path -Parent $TesseractCommand.Source }
}
if (-not $TesseractHome) {
    $ProgramFiles32 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $Candidates = @((Join-Path $env:ProgramFiles "Tesseract-OCR"))
    if ($ProgramFiles32) { $Candidates += (Join-Path $ProgramFiles32 "Tesseract-OCR") }
    foreach ($Candidate in $Candidates) {
        if (Test-Path (Join-Path $Candidate "tesseract.exe")) { $TesseractHome = $Candidate; break }
    }
}
if (-not $TesseractHome) { throw "Tesseract OCR is missing. Install it, then rerun with -TesseractHome pointing to its folder." }
if (-not (Test-Path (Join-Path $TesseractHome "tesseract.exe"))) { throw "tesseract.exe was not found in $TesseractHome" }
if (-not (Test-Path (Join-Path $TesseractHome "tessdata\eng.traineddata"))) { throw "Tesseract English language data is missing from $TesseractHome" }
$env:TESSERACT_INSTALL_DIR = (Resolve-Path $TesseractHome).Path
$env:TESSERACT_CMD = Join-Path $env:TESSERACT_INSTALL_DIR "tesseract.exe"
$env:TESSDATA_DIR = Join-Path $env:TESSERACT_INSTALL_DIR "tessdata"
# Point Tesseract directly at the verified English language-data directory.
$env:TESSDATA_PREFIX = $env:TESSDATA_DIR
Write-Host "Tesseract: $env:TESSERACT_INSTALL_DIR" -ForegroundColor Green
Write-Host "Language data: $env:TESSDATA_DIR" -ForegroundColor DarkGray
Write-Host "Verifying Tesseract can load English..." -ForegroundColor Cyan
$LanguageOutput = & $env:TESSERACT_CMD --list-langs 2>&1
$LanguageExitCode = $LASTEXITCODE
$LanguageOutput | ForEach-Object { Write-Host $_ }
if ($LanguageExitCode -ne 0 -or (($LanguageOutput -join "`n") -notmatch "(?m)^eng\s*$")) {
    throw "Tesseract could not load eng.traineddata from $env:TESSDATA_DIR. Check the Tesseract installation before building."
}

New-Item -ItemType Directory -Force -Path $BuildParent | Out-Null
if (Test-Path $BuildRoot) { throw "Build folder already exists: $BuildRoot" }

Write-Host ""
Write-Host "Fetching the isolated test branch..." -ForegroundColor Cyan
& git -C $Repo fetch origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Git fetch failed." }
& git -C $Repo worktree add --detach $BuildRoot ("origin/" + $Branch)
if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated Git worktree." }

Push-Location $BuildRoot
try {
    Write-Host ""
    Write-Host "Installing Python build tools and Align dependencies..." -ForegroundColor Cyan
    & py -3.12 -m pip install --upgrade pip pyinstaller pytest
    if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }
    & py -3.12 -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Could not install Align dependencies." }

    Write-Host ""
    Write-Host "Running Align, Work, rota OCR and authentication regression tests..." -ForegroundColor Cyan
    $TestFiles = @(
        "test_test_build_isolation.py", "test_rota_ocr_provider.py", "test_work_setup.py",
        "test_work_rota_import.py", "test_desktop_auth.py", "test_desktop_auth_http.py",
        "test_desktop_programme.py", "test_desktop_update.py", "test_owner_builder.py",
        "test_admin_owner_status.py", "test_studio150.py", "test_asset_studio_migration.py",
        "test_studio_update.py", "test_studio_deploy.py", "test_studio_render_deploy.py",
        "test_personal_planner.py", "test_post_event_travel.py", "test_retired_shift_api.py", "test_personal_otp.py",
        "test_transport_build149.py", "test_here_transit.py", "test_here_quota.py",
        "test_hosted_travel.py", "test_hosted_persistence.py", "test_month_calendar.py",
        "test_event_calendar_feed.py", "test_week_reminders151.py", "test_builder_finance.py",
        "test_builder_formatting.py", "test_local_backup.py", "test_ui_polish.py",
        "test_calendar_appearance.py", "test_phone_push.py", "test_credential_recovery.py"
    )
    & py -3.12 -m unittest @TestFiles
    if ($LASTEXITCODE -ne 0) { throw "Align regression tests failed. The Windows package was not created." }

    Write-Host "Verifying Build 158 release markers..." -ForegroundColor Cyan
    $ClientBuild = Select-String -Path "static\app.js" -Pattern '^const BUILD_VERSION = ([0-9]+);$'
    $ServerBuild = Select-String -Path "app.py" -Pattern '^BUILD_VERSION = ([0-9]+)$'
    $WorkerBuild = Select-String -Path "static\service-worker.js" -Pattern '^const BUILD = ([0-9]+);$'
    if (-not $ClientBuild -or $ClientBuild.Matches[0].Groups[1].Value -ne "158") { throw "Client application is not Build 158." }
    if (-not $ServerBuild -or $ServerBuild.Matches[0].Groups[1].Value -ne "158") { throw "Server application is not Build 158." }
    if (-not $WorkerBuild -or $WorkerBuild.Matches[0].Groups[1].Value -ne "158") { throw "Offline worker is not Build 158." }
    if (-not (Select-String -Path "static\index.html" -Pattern '158-v72' -Quiet)) { throw "HTML shell is not using the Build 158 asset cache." }
    if (-not (Test-Path "static\section-guide.js")) { throw "Guided section setup is missing." }
    if (-not (Test-Path "migrations\158_section_guides.sql")) { throw "Migration 158 is missing." }

    Write-Host "Checking JavaScript..." -ForegroundColor Cyan
    & node --check static/work-rota.js
    if ($LASTEXITCODE -ne 0) { throw "Work rota JavaScript syntax check failed." }
    & node --check static/shift-planner.js
    if ($LASTEXITCODE -ne 0) { throw "Shift planner JavaScript syntax check failed." }
    & node --check static/post-event-travel.js
    if ($LASTEXITCODE -ne 0) { throw "Post-event travel JavaScript syntax check failed." }
    & node test_work_calendar_entry.js
    if ($LASTEXITCODE -ne 0) { throw "Work calendar UI regression tests failed." }
    & node --check static/desktop.js
    if ($LASTEXITCODE -ne 0) { throw "Desktop JavaScript syntax check failed." }
    & node --check static/app.js
    if ($LASTEXITCODE -ne 0) { throw "Build 158 app JavaScript syntax check failed." }
    & node --check static/beta-admin.js
    if ($LASTEXITCODE -ne 0) { throw "Owner administration JavaScript syntax check failed." }
    & node --check static/section-guide.js
    if ($LASTEXITCODE -ne 0) { throw "Section guide JavaScript syntax check failed." }
    & node --check static/service-worker.js
    if ($LASTEXITCODE -ne 0) { throw "Build 158 service worker syntax check failed." }

    Write-Host "Testing the Go launcher..." -ForegroundColor Cyan
    Push-Location (Join-Path $BuildRoot "studio-launcher")
    try {
        & go test ./...
        if ($LASTEXITCODE -ne 0) { throw "Go launcher tests failed." }
    } finally { Pop-Location }

    Write-Host "Building the isolated Windows test application..." -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $BuildRoot "desktop\build_test_windows.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Windows executable build failed." }

    $AppRoot = Join-Path $BuildRoot "dist\Align V3.0 Test"
    $MustExist = @(
        (Join-Path $AppRoot "Align V3.0 Test.exe"),
        (Join-Path $AppRoot "ocr\tesseract.exe"),
        (Join-Path $AppRoot "ocr\tessdata\eng.traineddata"),
        (Join-Path $AppRoot "_internal\static\app.js"),
        (Join-Path $AppRoot "_internal\static\beta-admin.js"),
        (Join-Path $AppRoot "_internal\static\section-guide.js"),
        (Join-Path $AppRoot "_internal\migrations\158_section_guides.sql"),
        (Join-Path $BuildRoot "installer\windows\Install-Align-Test.ps1"),
        (Join-Path $BuildRoot "installer\windows\README-Test.md")
    )
    foreach ($RequiredFile in $MustExist) {
        if (-not (Test-Path $RequiredFile)) { throw "Required build file is missing: $RequiredFile" }
    }
    $PackagedAppJs = Get-Content -Raw (Join-Path $AppRoot "_internal\static\app.js")
    $PackagedIndex = Get-Content -Raw (Join-Path $AppRoot "_internal\static\index.html")
    $PackagedStudio = Get-Content -Raw (Join-Path $AppRoot "_internal\static\management-studio.html")
    $PackagedOwnerAdmin = Get-Content -Raw (Join-Path $AppRoot "_internal\static\beta-admin.js")
    if ($PackagedAppJs -notmatch 'const BUILD_VERSION = 158;') { throw "Packaged frontend is not Build 158." }
    if ($PackagedIndex -notmatch '158-v72') { throw "Packaged HTML shell is not using the Build 158 asset cache." }
    if ($PackagedStudio -notmatch 'beta-admin.js\?v=158-v72') { throw "Packaged Management Studio is not using the refreshed Owner admin script." }
    if ($PackagedOwnerAdmin -notmatch 'Not available in this local test installation') { throw "Packaged Owner admin screen is missing the local hosted-feature explanation." }

    Write-Host "Assembling the Windows test ZIP..." -ForegroundColor Cyan
    $PackageRoot = Join-Path $BuildRoot "dist\Align-V3.0-Test"
    $PackageApp = Join-Path $PackageRoot "Align V3.0 Test"
    New-Item -ItemType Directory -Force -Path $PackageApp | Out-Null
    Copy-Item (Join-Path $AppRoot "*") $PackageApp -Recurse -Force
    Copy-Item (Join-Path $BuildRoot "installer\windows\Install-Align-Test.ps1") $PackageRoot
    Copy-Item (Join-Path $BuildRoot "installer\windows\README-Test.md") (Join-Path $PackageRoot "README.md")
    Copy-Item (Join-Path $BuildRoot "desktop\README.md") (Join-Path $PackageRoot "BUILD.md")
    Copy-Item (Join-Path $BuildRoot "BUILD-158.md") (Join-Path $PackageRoot "BUILD-158.md")
    $Commit = (& git -C $BuildRoot rev-parse --short HEAD).Trim()
    @("ALIGN V3.0 TEST BUILD", "Build: 158", "Branch: $Branch", "Commit: $Commit", "NOT A PRODUCTION RELEASE") | Set-Content (Join-Path $PackageRoot "TEST-BUILD.txt") -Encoding UTF8
    $ZipFile = Join-Path $BuildRoot "dist\Align-V3.0-Test-Windows.zip"
    Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $ZipFile -CompressionLevel Optimal -Force
    if (-not (Test-Path $ZipFile)) { throw "The ZIP package was not created." }

    Write-Host ""
    Write-Host "BUILD COMPLETE" -ForegroundColor Green
    Write-Host "Package: $ZipFile" -ForegroundColor Green
    Write-Host "Installer in ZIP: Install-Align-Test.ps1" -ForegroundColor Green
    Write-Host "Test data: $env:LOCALAPPDATA\Align-Test" -ForegroundColor Green
    Write-Host "Test address: http://127.0.0.1:8011/desktop" -ForegroundColor Green
    Write-Host "Normal Align data was not opened or changed." -ForegroundColor Green
    if ($env:GITHUB_ACTIONS -ne "true") { Start-Process explorer.exe -ArgumentList ("/select," + $ZipFile) }
} finally {
    Pop-Location
    Write-Host "Isolated build source retained at: $BuildRoot" -ForegroundColor DarkGray
}

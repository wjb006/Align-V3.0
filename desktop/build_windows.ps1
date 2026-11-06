# Build the Windows Align programme
# Run from any directory:  powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = $null
try { & py -3.12 --version *> $null; if ($LASTEXITCODE -eq 0) { $Python = "py -3.12" } } catch {}
if (-not $Python) { $Python = "python" }
Write-Host "Installing the build tools..."
Invoke-Expression "$Python -m pip install --upgrade pip pyinstaller"
if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }
Invoke-Expression "$Python -m pip install -r requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "Could not install Align's Python dependencies." }
$InfoPath = Join-Path $Root "desktop\build_info.py"
$InfoOriginal = [System.IO.File]::ReadAllText($InfoPath)
$Commit = ""
try { $Commit = (& git -C $Root rev-parse HEAD).Trim() } catch { $Commit = "" }
if ($Commit -match '^[0-9a-f]{40}$') {
    $Stamped = @"
"""Commit recorded by the Windows build. Empty in a source checkout."""
COMMIT = "$Commit"
"@
    [System.IO.File]::WriteAllText($InfoPath, $Stamped.Replace("`r`n", "`n") + "`n")
}
try {
    Invoke-Expression "$Python -m PyInstaller --noconfirm --clean desktop/align.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller did not produce Align." }
} finally {
    [System.IO.File]::WriteAllText($InfoPath, $InfoOriginal)
}
$Built = Join-Path $Root "dist\Align\Align.exe"
if (-not (Test-Path $Built)) { throw "Expected $Built" }
Copy-Item (Join-Path $Root "static\icons\align.ico") (Join-Path $Root "dist\Align\align.ico") -Force
$TesseractHome = $env:ALIGN_TESSERACT_HOME
if (-not $TesseractHome) { $TesseractHome = Join-Path $env:ProgramFiles "Tesseract-OCR" }
$TesseractExe = Join-Path $TesseractHome "tesseract.exe"
if (Test-Path $TesseractExe) {
    $TesseractDestination = Join-Path $Root "dist\Align\tesseract"
    New-Item -ItemType Directory -Force -Path $TesseractDestination | Out-Null
    Copy-Item (Join-Path $TesseractHome "*") $TesseractDestination -Recurse -Force
    Write-Host "Bundled local OCR runtime from $TesseractHome"
} else {
    Write-Warning "Tesseract was not found. This build will report photo/scanned-PDF OCR as unavailable."
}
Write-Host "Built $Built"
Write-Host "Installer input is dist\Align plus installer\windows\Install-Align-Studio.ps1"

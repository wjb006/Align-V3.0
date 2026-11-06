# Build the Windows Align programme
# Run from any directory:  powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = $null
try { & py -3.12 --version *> $null; if ($LASTEXITCODE -eq 0) { $Python = "py -3.12" } } catch {}
if (-not $Python) { $Python = "python" }
$TesseractCandidates = @(
    $env:TESSERACT_INSTALL_DIR,
    (Join-Path $env:ProgramFiles "Tesseract-OCR"),
    (Join-Path ${env:ProgramFiles(x86)} "Tesseract-OCR")
) | Where-Object { $_ -and (Test-Path (Join-Path $_ "tesseract.exe")) }
if (-not $TesseractCandidates) {
    throw "Tesseract OCR is required for the photo/scanned-PDF test build. Install Tesseract OCR or set TESSERACT_INSTALL_DIR."
}
$env:TESSERACT_INSTALL_DIR = (Resolve-Path ($TesseractCandidates | Select-Object -First 1)).Path
if (-not (Test-Path (Join-Path $env:TESSERACT_INSTALL_DIR "tessdata\eng.traineddata"))) {
    throw "Tesseract English language data was not found in $env:TESSERACT_INSTALL_DIR\tessdata."
}
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
$BundledTesseract = Join-Path $Root "dist\Align\ocr\tesseract.exe"
if (-not (Test-Path $BundledTesseract)) { throw "The Windows package is missing its bundled Tesseract OCR engine." }
if (-not (Test-Path (Join-Path $Root "dist\Align\ocr\tessdata\eng.traineddata"))) { throw "The Windows package is missing the English OCR model." }
Copy-Item (Join-Path $Root "static\icons\align.ico") (Join-Path $Root "dist\Align\align.ico") -Force
Write-Host "Built $Built"
Write-Host "Installer input is dist\Align plus installer\windows\Install-Align-Studio.ps1"

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
Invoke-Expression "$Python -m PyInstaller --noconfirm --clean desktop/align.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller did not produce Align." }
$Built = Join-Path $Root "dist\Align\Align.exe"
if (-not (Test-Path $Built)) { throw "Expected $Built" }
Write-Host "Built $Built"
Write-Host "Installer input is dist\Align plus installer\windows\Install-Align-Studio.ps1"

$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Align V3.0 Test"
$DataRoot = Join-Path $env:LOCALAPPDATA "Align-Test"
$PackagedRoot = Join-Path $PSScriptRoot "Align V3.0 Test"
$PackagedApp = Join-Path $PackagedRoot "Align V3.0 Test.exe"

if (-not (Test-Path $PackagedApp)) {
    throw "The isolated Align V3.0 Test executable is missing from the package."
}

Write-Host ""
Write-Host "ALIGN V3.0 TEST" -ForegroundColor Cyan
Write-Host "Installing separately from your normal Align programme..." -ForegroundColor Gray
New-Item -ItemType Directory -Force -Path $InstallRoot, $DataRoot | Out-Null

# This installer deliberately uses a separate programme folder and a separate
# data folder. It never copies, migrates, opens or deletes %LOCALAPPDATA%\Align.
Copy-Item -Path (Join-Path $PackagedRoot "*") -Destination $InstallRoot -Recurse -Force

$Target = Join-Path $InstallRoot "Align V3.0 Test.exe"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell
$ShortcutPath = Join-Path $Desktop "Align V3.0 Test.lnk"
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.Arguments = ""
$Shortcut.WorkingDirectory = $InstallRoot
$Shortcut.Description = "Open the isolated Align V3.0 test build"
$IconFile = Join-Path $InstallRoot "align.ico"
if (Test-Path $IconFile) { $Shortcut.IconLocation = $IconFile }
$Shortcut.Save()

Write-Host "Test app: $InstallRoot" -ForegroundColor Green
Write-Host "Test data: $DataRoot" -ForegroundColor Green
Write-Host "Your normal Align app and %LOCALAPPDATA%\Align data have not been touched." -ForegroundColor Green
Start-Process -FilePath $Target -WorkingDirectory $InstallRoot

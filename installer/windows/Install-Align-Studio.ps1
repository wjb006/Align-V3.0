$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Align Management Studio"
$DataRoot = Join-Path $env:LOCALAPPDATA "Align"
function Find-Python {
    try { & py -3.12 --version *> $null; if ($LASTEXITCODE -eq 0) { return "py" } } catch {}
    try { $v = & python --version 2>&1; if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.1[2-9]") { return "python" } } catch {}
    return $null
}
Write-Host ""; Write-Host "ALIGN MANAGEMENT STUDIO" -ForegroundColor Cyan
Write-Host "Preparing your local control hub..." -ForegroundColor Gray
$Python = Find-Python
if (-not $Python) {
    Write-Host "Python 3.12+ is required. Install it from https://www.python.org/downloads/windows/ and enable Add Python to PATH." -ForegroundColor Yellow
    Read-Host "Press Enter to close"; exit 1
}
$SourceRoot = Join-Path $PSScriptRoot "app"
if (-not (Test-Path (Join-Path $SourceRoot "app.py"))) { throw "Align application files were not found beside this installer." }
New-Item -ItemType Directory -Force -Path $InstallRoot,$DataRoot | Out-Null
$TargetApp = Join-Path $InstallRoot "app"
if (Test-Path $TargetApp) { Remove-Item $TargetApp -Recurse -Force }
Copy-Item $SourceRoot $TargetApp -Recurse -Force
Copy-Item (Join-Path $PSScriptRoot "Launch-Align-Studio.ps1") $InstallRoot -Force
$Venv = Join-Path $InstallRoot ".venv"
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    if ($Python -eq "py") { & py -3.12 -m venv $Venv } else { & python -m venv $Venv }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the private Python environment." }
}
$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not prepare Python package installer." }
& $VenvPython -m pip install -r (Join-Path $TargetApp "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check your internet connection and try again." }
$SettingsFile = Join-Path $DataRoot "studio-environment.ps1"
if (-not (Test-Path $SettingsFile)) {
    ('$env:ALIGN_DATA_DIR = "' + $DataRoot + '"' + [Environment]::NewLine + '$env:ALIGN_BETA_MODE = "0"') | Set-Content -Encoding UTF8 $SettingsFile
}
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "Align Management Studio.lnk"))
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallRoot "Launch-Align-Studio.ps1") + '"'
$Shortcut.WorkingDirectory = $InstallRoot
$Shortcut.Description = "Open your local Align V3.0 control hub"
$Shortcut.Save()
Write-Host "Installation prepared. Launching Align..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",(Join-Path $InstallRoot "Launch-Align-Studio.ps1"))

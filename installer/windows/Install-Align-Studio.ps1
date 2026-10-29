$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Align Management Studio"
$DataRoot = Join-Path $env:LOCALAPPDATA "Align"
$PackagedApp = Join-Path $PSScriptRoot "Align\Align.exe"
$SourceRoot = Join-Path $PSScriptRoot "app"

function Find-Python {
    try { & py -3.12 --version *> $null; if ($LASTEXITCODE -eq 0) { return "py" } } catch {}
    try { $v = & python --version 2>&1; if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.1[2-9]") { return "python" } } catch {}
    return $null
}

Write-Host ""
Write-Host "ALIGN" -ForegroundColor Cyan
Write-Host "Installing the planner and Management Studio on this computer..." -ForegroundColor Gray
New-Item -ItemType Directory -Force -Path $InstallRoot, $DataRoot | Out-Null

# Planner data lives in $DataRoot. This installer never deletes or overwrites
# align.sqlite3. The programme adopts an older copy itself when the data folder
# does not already have one.
if (Test-Path $PackagedApp) {
    Copy-Item -Path (Join-Path $PSScriptRoot "Align\*") -Destination $InstallRoot -Recurse -Force
    $Target = Join-Path $InstallRoot "Align.exe"
} elseif (Test-Path (Join-Path $SourceRoot "app.py")) {
    $Python = Find-Python
    if (-not $Python) {
        Write-Host "Python 3.12 or newer is required for a source install. Install it from https://www.python.org/downloads/windows/ and enable Add Python to PATH." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit 1
    }
    $TargetApp = Join-Path $InstallRoot "app"
    New-Item -ItemType Directory -Force -Path $TargetApp | Out-Null
    Copy-Item -Path (Join-Path $SourceRoot "*") -Destination $TargetApp -Recurse -Force
    $Venv = Join-Path $InstallRoot ".venv"
    if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
        if ($Python -eq "py") { & py -3.12 -m venv $Venv } else { & python -m venv $Venv }
        if ($LASTEXITCODE -ne 0) { throw "Could not create the private Python environment." }
    }
    $VenvPython = Join-Path $Venv "Scripts\python.exe"
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare the Python package installer." }
    & $VenvPython -m pip install -r (Join-Path $TargetApp "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check your internet connection and try again." }
    Copy-Item (Join-Path $PSScriptRoot "Launch-Align-Studio.ps1") $InstallRoot -Force
    $Target = "powershell.exe"
} else {
    throw "The Align programme was not found beside this installer. Use a package that contains Align\Align.exe."
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut((Join-Path $Desktop "Align.lnk"))
if ($Target -eq "powershell.exe") {
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $InstallRoot "Launch-Align-Studio.ps1") + '"'
} else {
    $Shortcut.TargetPath = $Target
    $Shortcut.Arguments = ""
}
$Shortcut.WorkingDirectory = $InstallRoot
$Shortcut.Description = "Open Align planner and Management Studio"
$Shortcut.Save()
$OldShortcut = Join-Path $Desktop "Align Management Studio.lnk"
if ((Test-Path -LiteralPath $OldShortcut) -and ($OldShortcut -ne $Shortcut.FullName)) {
    Remove-Item -LiteralPath $OldShortcut -Force
}
Write-Host "Align is installed. Your planner data stays in $DataRoot." -ForegroundColor Green
if ($Target -eq "powershell.exe") {
    Start-Process powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", (Join-Path $InstallRoot "Launch-Align-Studio.ps1"))
} else {
    Start-Process -FilePath $Target -WorkingDirectory $InstallRoot
}

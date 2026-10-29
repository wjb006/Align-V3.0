$ErrorActionPreference = "Stop"
$InstallRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonW = Join-Path $InstallRoot ".venv\Scripts\pythonw.exe"
$Python = Join-Path $InstallRoot ".venv\Scripts\python.exe"
$App = Join-Path $InstallRoot "app"
if (-not (Test-Path (Join-Path $App "app.py")) -or -not (Test-Path $Python)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Align needs to be installed again. Your saved planner data was not removed.","Align") | Out-Null
    exit 1
}
$Runtime = if (Test-Path $PythonW) { $PythonW } else { $Python }
$DataRoot = Join-Path $env:LOCALAPPDATA "Align"
$EnvironmentFile = Join-Path $DataRoot "studio-environment.ps1"
if (Test-Path $EnvironmentFile) { . $EnvironmentFile }
$env:ALIGN_DATA_DIR = $DataRoot
$env:ALIGN_STUDIO_LOCAL = "1"
$env:ALIGN_BETA_MODE = "0"
Start-Process -FilePath $Runtime -ArgumentList @("-m", "desktop") -WorkingDirectory $App -WindowStyle Hidden

$ErrorActionPreference = "Stop"
$InstallRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $InstallRoot ".venv\Scripts\python.exe"
$Launcher = Join-Path $InstallRoot "Align-Management-Studio.exe"
$DataRoot = Join-Path $env:LOCALAPPDATA "Align"
$EnvironmentFile = Join-Path $DataRoot "studio-environment.ps1"
if (-not (Test-Path $Python) -or -not (Test-Path $Launcher)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Align Management Studio needs installation or repair. Run the installer again.","Align Management Studio") | Out-Null
    exit 1
}
if (Test-Path $EnvironmentFile) { . $EnvironmentFile }
$env:ALIGN_DATA_DIR = $DataRoot
$env:ALIGN_STUDIO_LOCAL = "1"
Start-Process -FilePath $Launcher -WorkingDirectory $InstallRoot

$ErrorActionPreference = "Stop"
$InstallRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppRoot = Join-Path $InstallRoot "app"
$Python = Join-Path $InstallRoot ".venv\Scripts\python.exe"
$DataRoot = Join-Path $env:LOCALAPPDATA "Align"
$EnvironmentFile = Join-Path $DataRoot "studio-environment.ps1"
if (-not (Test-Path $Python)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Align needs installation. Run the installer again.","Align Management Studio") | Out-Null
    exit 1
}
if (Test-Path $EnvironmentFile) { . $EnvironmentFile }
$env:ALIGN_DATA_DIR = $DataRoot
$env:ALIGN_STUDIO_LOCAL = "1"
$port = 8001
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("127.0.0.1",$port); $client.Close()
    Start-Process "http://127.0.0.1:$port/studio"
    exit 0
} catch {}
$log = Join-Path $DataRoot "studio.log"
$err = Join-Path $DataRoot "studio-error.log"
$process = Start-Process -FilePath $Python -ArgumentList @((Join-Path $AppRoot "app.py")) -WorkingDirectory $AppRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err
$ready = $false
for ($i=0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ge 200) { $ready = $true; break }
    } catch { if ($process.HasExited) { break } }
}
if ($ready) { Start-Process "http://127.0.0.1:$port/studio" }
else {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Align could not start. Logs are saved in:" + [Environment]::NewLine + $DataRoot + [Environment]::NewLine + "Check studio-error.log for details.","Align Management Studio") | Out-Null
}

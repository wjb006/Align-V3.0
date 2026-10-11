@echo off
setlocal
cd /d "%~dp0"
title Stop Align OTP
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$stopped=$false; if(Get-Command docker -ErrorAction SilentlyContinue){$container=& docker ps -q --filter 'name=^/align-otp$' 2>$null; if($container){& docker stop align-otp | Out-Null; if($LASTEXITCODE -eq 0){$stopped=$true}}}; $jar=Join-Path (Get-Location) 'otp-runtime\otp-shaded-2.8.0.jar'; $full=[IO.Path]::GetFullPath($jar); $procs=Get-CimInstance Win32_Process -Filter 'Name = ''java.exe''' -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($full,[StringComparison]::OrdinalIgnoreCase) -ge 0 }; foreach($proc in $procs){Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop; $stopped=$true}; if($stopped){Write-Host 'Align OTP stopped.'}else{Write-Host 'Align OTP was not running.'}"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" echo Could not stop OTP. Close its terminal or inspect Docker, then retry.
pause
exit /b %EXITCODE%

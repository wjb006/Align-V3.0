@echo off
setlocal
cd /d "%~dp0"
title Align Merseyside
set "OTP_DATA=%~dp0otp-data"
set "ALIGN_PORT=8010"
if not defined ALIGN_TRANSPORT_ENABLED set "ALIGN_TRANSPORT_ENABLED=1"
set "ALIGN_OTP_URL=http://127.0.0.1:8080/otp/gtfs/v1"

if not exist "%OTP_DATA%\graph.obj" (
  echo The Merseyside graph is not ready.
  echo Double-click Build Align OTP Graph.bat once, then run this file again.
  pause
  exit /b 1
)

powershell -NoProfile -Command "$ok=Test-NetConnection -ComputerName 127.0.0.1 -Port 8080 -InformationLevel Quiet; if(-not $ok){ Start-Process -FilePath '%~dp0Start Align OTP.bat' -WindowStyle Hidden; $deadline=(Get-Date).AddSeconds(60); do { Start-Sleep -Seconds 1; $ok=Test-NetConnection -ComputerName 127.0.0.1 -Port 8080 -InformationLevel Quiet } while((-not $ok) -and ((Get-Date)-lt $deadline)) }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 (
  echo OTP did not become ready on port 8080.
  echo Run Start Align OTP.bat to see its diagnostic message.
  pause
  exit /b 1
)

echo Merseyside routing is ready.
echo Open http://127.0.0.1:%ALIGN_PORT%/ after Align starts.
call "%~dp0Start-Align.bat"
endlocal

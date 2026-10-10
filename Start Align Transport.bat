@echo off
setlocal
cd /d "%~dp0"
title Align Transport Build 149

set "ALIGN_PORT=8010"
if not defined ALIGN_TRANSPORT_ENABLED set "ALIGN_TRANSPORT_ENABLED=1"
if not defined ALIGN_OTP_URL set "ALIGN_OTP_URL=http://127.0.0.1:8080/otp/gtfs/v1"

echo.
echo Align Transport is enabled for this run.
echo Routing URL: %ALIGN_OTP_URL%
echo Open http://127.0.0.1:%ALIGN_PORT%/ after Align starts.
echo Press Ctrl+C in this window to stop Align.
echo.

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" launch.py
) else (
  py -3 launch.py
)

if errorlevel 1 (
  echo.
  echo Align stopped with an error.
  pause
)
endlocal

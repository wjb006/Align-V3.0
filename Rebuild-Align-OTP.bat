@echo off
setlocal
cd /d "%~dp0"
title Rebuild Align V3.0 OTP Graph
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Rebuild-Align-OTP.ps1"
if errorlevel 1 (
  echo.
  echo OTP rebuild failed. Check otp-rebuild.log in this folder.
  pause
  exit /b 1
)
echo.
echo OTP graph rebuilt successfully.
pause

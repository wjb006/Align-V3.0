@echo off
setlocal
cd /d "%~dp0"
title Rebuild Align V3.0 OTP Graph

echo Updating Align OTP rebuild scripts from GitHub...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $base='https://raw.githubusercontent.com/wjb006/Align-V3.0/codex/align-v3-rebuild/'; $root=(Get-Location).Path; Invoke-WebRequest -UseBasicParsing -Uri ($base+'Rebuild-Align-OTP.ps1') -OutFile (Join-Path $root 'Rebuild-Align-OTP.ps1'); Invoke-WebRequest -UseBasicParsing -Uri ($base+'Sanitize-Align-NationalRail.ps1') -OutFile (Join-Path $root 'Sanitize-Align-NationalRail.ps1')"
if errorlevel 1 (
  echo Could not update scripts from GitHub. Check your internet connection.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Rebuild-Align-OTP.ps1"
if errorlevel 1 (
  echo.
  echo OTP rebuild failed. Check otp-rebuild.log and otp-graph-build.log in this folder.
  pause
  exit /b 1
)
echo.
echo OTP graph rebuilt successfully.
pause

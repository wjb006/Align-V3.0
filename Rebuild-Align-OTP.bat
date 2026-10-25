@echo off
setlocal
cd /d "%~dp0"
title Rebuild Align V3.0 OTP Graph

REM Prefer authenticated refresh when GitHub CLI is available, so fixes are
REM pulled automatically. If gh is unavailable, existing local scripts still run.
where gh.exe >nul 2>&1
if not errorlevel 1 (
  gh auth status >nul 2>&1
  if not errorlevel 1 goto refresh_scripts
)

if exist "%~dp0Rebuild-Align-OTP.ps1" if exist "%~dp0Sanitize-Align-NationalRail.ps1" goto run_local

echo Required script files are missing from:
echo   %CD%
echo.
echo Expected files:
echo   Rebuild-Align-OTP.ps1
echo   Sanitize-Align-NationalRail.ps1
echo.
echo Download them from the signed-in GitHub repository and save them
echo directly into this same folder as this .bat file.
echo.
echo Repository: https://github.com/wjb006/Align-V3.0/tree/codex/align-v3-rebuild
pause
exit /b 1

:refresh_scripts
echo Updating Align OTP rebuild scripts from your authenticated GitHub account...
gh api "repos/wjb006/Align-V3.0/contents/Rebuild-Align-OTP.ps1?ref=codex/align-v3-rebuild" --jq .content > "%TEMP%\align-otp-script.b64"
if errorlevel 1 goto download_failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$b=[IO.File]::ReadAllText('%TEMP%\align-otp-script.b64').Trim(); [IO.File]::WriteAllBytes('%CD%\Rebuild-Align-OTP.ps1',[Convert]::FromBase64String($b))"
if errorlevel 1 goto download_failed
gh api "repos/wjb006/Align-V3.0/contents/Sanitize-Align-NationalRail.ps1?ref=codex/align-v3-rebuild" --jq .content > "%TEMP%\align-otp-sanitize.b64"
if errorlevel 1 goto download_failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$b=[IO.File]::ReadAllText('%TEMP%\align-otp-sanitize.b64').Trim(); [IO.File]::WriteAllBytes('%CD%\Sanitize-Align-NationalRail.ps1',[Convert]::FromBase64String($b))"
if errorlevel 1 goto download_failed
del "%TEMP%\align-otp-script.b64" "%TEMP%\align-otp-sanitize.b64" >nul 2>&1

:run_local
echo Running Align OTP graph rebuild...
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
exit /b 0

:download_failed
echo Could not fetch the latest scripts using GitHub CLI authentication.
echo Check that your account can access wjb006/Align-V3.0.
pause
exit /b 1

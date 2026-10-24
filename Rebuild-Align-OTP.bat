@echo off
setlocal
cd /d "%~dp0"
title Rebuild Align V3.0 OTP Graph

where gh.exe >nul 2>&1
if errorlevel 1 (
  echo This is a private GitHub repository, so raw.githubusercontent.com returns 404 when not authenticated.
  echo Please open the repository in your signed-in browser and download these two files:
  echo   Rebuild-Align-OTP.ps1
  echo   Sanitize-Align-NationalRail.ps1
  echo Save both into: %CD%
  echo Then run this launcher again.
  echo.
  echo Repository: https://github.com/wjb006/Align-V3.0/tree/codex/align-v3-rebuild
  pause
  exit /b 1
)

echo Updating Align OTP rebuild scripts using your authenticated GitHub CLI...
gh auth status >nul 2>&1
if errorlevel 1 (
  echo GitHub CLI is installed but not signed in. Run: gh auth login
  pause
  exit /b 1
)
gh api "repos/wjb006/Align-V3.0/contents/Rebuild-Align-OTP.ps1?ref=codex/align-v3-rebuild" --jq .content > "%TEMP%\align-otp-script.b64"
if errorlevel 1 goto download_failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$b=[IO.File]::ReadAllText('%TEMP%\align-otp-script.b64').Trim(); [IO.File]::WriteAllBytes('%CD%\Rebuild-Align-OTP.ps1',[Convert]::FromBase64String($b))"
if errorlevel 1 goto download_failed
gh api "repos/wjb006/Align-V3.0/contents/Sanitize-Align-NationalRail.ps1?ref=codex/align-v3-rebuild" --jq .content > "%TEMP%\align-otp-sanitize.b64"
if errorlevel 1 goto download_failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$b=[IO.File]::ReadAllText('%TEMP%\align-otp-sanitize.b64').Trim(); [IO.File]::WriteAllBytes('%CD%\Sanitize-Align-NationalRail.ps1',[Convert]::FromBase64String($b))"
if errorlevel 1 goto download_failed
del "%TEMP%\align-otp-script.b64" "%TEMP%\align-otp-sanitize.b64" >nul 2>&1

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
echo Could not fetch scripts using GitHub CLI authentication.
echo Check that your account can access wjb006/Align-V3.0.
pause
exit /b 1

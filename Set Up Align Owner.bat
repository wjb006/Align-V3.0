@echo off
setlocal
title Align V3 - Set Up Live Owner
set "V3_ROOT=%~dp0"
if not exist "%V3_ROOT%setup_live_owner.py" (
  echo Align V3 live Owner setup was not found at:
  echo %V3_ROOT%setup_live_owner.py
  pause
  exit /b 2
)
if exist "%V3_ROOT%.venv\Scripts\python.exe" (
  "%V3_ROOT%.venv\Scripts\python.exe" "%V3_ROOT%setup_live_owner.py"
) else (
  py "%V3_ROOT%setup_live_owner.py"
)
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Live Owner setup stopped. No success was reported.
pause
exit /b %RESULT%

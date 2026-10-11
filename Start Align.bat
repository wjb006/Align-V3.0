@echo off
setlocal
cd /d "%~dp0"
title Align V3.0

if /I "%~1"=="local" goto local
if /I "%~1"=="wifi" goto wifi
if /I "%~1"=="remote" goto remote
if /I "%~1"=="transport" goto transport
if /I "%~1"=="merseyside" goto merseyside

echo.
echo  ALIGN V3.0
echo  ==========
echo  L  Start on this PC
echo  W  Start on Wi-Fi
echo  R  Start remote access
echo  T  Start with transport routing already running
echo  M  Start Merseyside transport and Align
echo  Q  Quit
echo.
choice /C LWRMTQ /N /M "Choose how to start Align: "
if errorlevel 6 exit /b 0
if errorlevel 5 goto merseyside
if errorlevel 4 goto transport
if errorlevel 3 goto remote
if errorlevel 2 goto wifi
if errorlevel 1 goto local
exit /b 0

:local
call "%~dp0Start-Align.bat"
goto finished

:wifi
call "%~dp0Start-Align.bat" --network
goto finished

:remote
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start Align Remote Access.ps1"
pause
goto finished

:transport
set "ALIGN_PORT=8010"
set "ALIGN_TRANSPORT_ENABLED=1"
if not defined ALIGN_OTP_URL set "ALIGN_OTP_URL=http://127.0.0.1:8080/otp/gtfs/v1"
call "%~dp0Start-Align.bat"
goto finished

:merseyside
call "%~dp0Start Align Merseyside.bat"
goto finished

:finished
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%

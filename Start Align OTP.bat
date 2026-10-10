@echo off
setlocal
set "OTP_DATA=%~dp0otp-data"
set "OTP_JAVA=%~dp0otp-runtime\jdk-25.0.4.1+1\bin\java.exe"
set "OTP_JAR=%~dp0otp-runtime\otp-shaded-2.8.0.jar"
title Align Merseyside OTP server

if not exist "%OTP_DATA%\graph.obj" (
  echo No graph.obj found. Double-click Build Align OTP Graph.bat first.
  pause
  exit /b 1
)
if exist "%OTP_JAVA%" if exist "%OTP_JAR%" goto portable
where docker >nul 2>&1
if errorlevel 1 (
  echo Portable Java OTP runtime is missing and Docker is not available.
  pause
  exit /b 1
)
docker rm -f align-otp >nul 2>&1
echo OTP will be available at http://127.0.0.1:8080/otp/gtfs/v1
echo Leave this window open while Align is running.
docker run --name align-otp -p 127.0.0.1:8080:8080 -v "%OTP_DATA%:/var/opentripplanner" docker.io/opentripplanner/opentripplanner:2.8.0 --load --serve
endlocal
exit /b

:portable
echo OTP will be available at http://127.0.0.1:8080/otp/gtfs/v1
echo Leave this window open while Align is running.
echo Press Ctrl+C to stop OTP.
"%OTP_JAVA%" -Xmx4G -jar "%OTP_JAR%" --load --serve --bindAddress 127.0.0.1 "%OTP_DATA%"
endlocal

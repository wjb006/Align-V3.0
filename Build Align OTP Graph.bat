@echo off
setlocal
set "OTP_DATA=%~dp0otp-data"
set "OTP_JAVA=%~dp0otp-runtime\jdk-25.0.4.1+1\bin\java.exe"
set "OTP_JAR=%~dp0otp-runtime\otp-shaded-2.8.0.jar"
title Build Align Merseyside OTP graph

if not exist "%OTP_DATA%" mkdir "%OTP_DATA%"
if not exist "%OTP_DATA%\merseyside-latest.osm.pbf" (
  echo Missing Merseyside OSM extract: %OTP_DATA%\merseyside-latest.osm.pbf
  pause
  exit /b 1
)
if not exist "%OTP_DATA%\uk-busmetro-NW.gtfs.zip" (
  echo Missing North West bus/metro feed: %OTP_DATA%\uk-busmetro-NW.gtfs.zip
  pause
  exit /b 1
)
if not exist "%OTP_DATA%\gb-nationalrail.gtfs.zip" (
  echo Missing National Rail feed: %OTP_DATA%\gb-nationalrail.gtfs.zip
  pause
  exit /b 1
)

if exist "%~dp0otp-runtime\sanitize_nationalrail.py" (
  echo Checking the rail feed for duplicate calendar records...
  python "%~dp0otp-runtime\sanitize_nationalrail.py"
)

if exist "%OTP_JAVA%" if exist "%OTP_JAR%" goto portable
where docker >nul 2>&1
if errorlevel 1 (
  echo Portable Java OTP runtime is missing and Docker is not available.
  echo Run the Align setup package again, or contact support.
  pause
  exit /b 1
)
echo Building with Docker because the portable runtime was not found.
docker run --rm -v "%OTP_DATA%:/var/opentripplanner" docker.io/opentripplanner/opentripplanner:2.8.0 --build --save
if errorlevel 1 echo OTP graph build failed.
pause
endlocal
exit /b

:portable
echo Building the Merseyside graph. This may take several minutes.
"%OTP_JAVA%" -Xmx4G -jar "%OTP_JAR%" --build --save "%OTP_DATA%"
if errorlevel 1 (
  echo OTP graph build failed.
  pause
  exit /b 1
)
echo Graph built successfully: %OTP_DATA%\graph.obj
pause
endlocal

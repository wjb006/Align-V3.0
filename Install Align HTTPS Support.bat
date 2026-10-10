@echo off
setlocal
cd /d "%~dp0"
title Align HTTPS Setup

echo Align HTTPS Support
echo ===================
echo This installs the Python certificate helper, then opens a temporary local page
echo so your iPhone can install the Align Local Root CA profile.
echo.

if exist ".venv\Scripts\python.exe" goto use_venv
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 goto use_python

echo Python 3.10 or later is required.
pause
exit /b 1

:use_py
py -3 -m pip install "cryptography>=45" || goto failed
py -3 https_setup.py --serve-ca
goto finished

:use_python
python -m pip install "cryptography>=45" || goto failed
python https_setup.py --serve-ca
goto finished

:use_venv
".venv\Scripts\python.exe" -m pip install "cryptography>=45" || goto failed
".venv\Scripts\python.exe" https_setup.py --serve-ca
goto finished

:failed
echo.
echo HTTPS support could not be installed. Check your internet connection and try again.
:finished
echo.
pause

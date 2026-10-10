@echo off
setlocal
cd /d "%~dp0"
title Align v1.2
if exist ".venv\Scripts\python.exe" goto use_venv
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 goto use_python
echo Python 3.10 or later is required. Install it from:
echo https://www.python.org/downloads/windows/
pause
exit /b 1
:use_py
py -3 launch.py %*
goto finished
:use_python
python launch.py %*
goto finished
:use_venv
".venv\Scripts\python.exe" launch.py %*
:finished
pause

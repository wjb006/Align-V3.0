@echo off
cd /d "%~dp0"
title Align - Set Up Beta Owner
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" beta_setup.py
) else (
  py beta_setup.py
)
pause

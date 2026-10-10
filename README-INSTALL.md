# Align v1.3 — Build 156 Installation Guide

## Purpose
This package installs the local Windows version of Align v1.3 Build 156.

## Included
- `Install-Align.bat` — double-click installer.
- `Install-Align.ps1` — prerequisite, virtual-environment, dependency, database and verification engine.
- `Start-Align.bat` — starts Align using `.venv`.
- `README-INSTALL.md` — this guide.

## Prerequisites
- Windows 10 or Windows 11.
- Python 3.10 or newer; Python 3.12 is recommended.
- Internet access during dependency installation.
- A writable installation folder. `C:\Align\Build-156\` is a suitable example.

Python is not bundled with the ZIP. Install it first if the installer reports that Python is missing.

## Install
1. Extract the complete ZIP. Do not run Align from inside the ZIP.
2. Double-click `Install-Align.bat`.
3. The installer verifies Build 156 before changing the environment.
4. It creates or reuses `.venv`.
5. It upgrades pip and installs the repository's `requirements.txt` dependency chain.
6. It imports Align and runs the application's own database initialisation/migration routine.
7. It checks SQLite integrity and required tables.
8. It compiles Python sources and performs a final Build 156 health check.

Installation logs are written to `install-logs\`.

## Database
Local Align uses SQLite by default. The database is:

`align.sqlite3`

The installer does not delete an existing database. Re-running the installer is intended to preserve existing local data while allowing Align's migration code to upgrade it.

Stop Align before manually copying or replacing the database.

## Start Align
After a successful installation, double-click:

`Start-Align.bat`

The local application normally runs at:

`http://127.0.0.1:8001/`

The launcher starts `launch.py` with `.venv\Scripts\python.exe`. Keep the command window open while using the local server. Press Ctrl+C in that window to stop Align.

## What is verified
The installer checks:
- Windows environment.
- Required Build 156 files and folders.
- Server Build 156 in `app.py`.
- Client Build 156 in `static/app.js`.
- Service-worker Build 156 in `static/service-worker.js`.
- Python 3.10+.
- Virtual environment creation/reuse.
- Dependency installation.
- Python source compilation.
- Align database initialisation/migrations.
- SQLite integrity.
- Required core tables.
- Application import and health status.

## Common errors
### Python not found
Install Python 3.12 and run the installer again. If Python was just installed, open a new Command Prompt/Explorer window first.

### Python is too old
Build 156 requires Python 3.10 or newer. Python 3.12 is recommended.

### Virtual environment cannot be created
Move the extracted folder to a writable location such as `C:\Align\Build-156\`. Avoid protected folders such as `C:\Program Files\`.

### Dependency installation failed
Check Internet access and the latest file in `install-logs\`. The installer records the pip output.

### Database setup failed
Do not delete `align.sqlite3` as a first response. Read the installer log and keep a backup of existing data. If this is an existing installation, stop Align and retry the installer.

### Port 8001 is unavailable
Another application or Align instance is using the port. Close the other instance and start Align again.

### Browser does not open
Open `http://127.0.0.1:8001/` manually while the Align command window is running.

## Reinstalling
It is safe to run `Install-Align.bat` again. It reuses `.venv`, checks dependencies, runs Align's database initialisation/migration logic and repeats verification. It does not intentionally erase user data.

## Local versus hosted Align
This package is for the local Windows application. It does not configure Render, Neon/Postgres, Microsoft Graph, Apple/iCloud credentials, transport services or other external integrations.

## Successful result
A successful install ends with `ALIGN INSTALLATION COMPLETE` and reports Build 156, the Python version, virtual-environment path, database path and log path.

Then run `Start-Align.bat` and open `http://127.0.0.1:8001/`.

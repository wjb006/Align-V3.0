# Align desktop programme

This is the Windows programme for the Align planner and Management Studio. It is the same Python application as the local server. The programme starts that server on this computer, keeps the database outside the programme files, and opens a home screen with both parts.

## Run it from source

Python 3.12 or newer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m desktop
```

On macOS or Linux the same entry point is `python3 -m desktop`.

- Home: `http://127.0.0.1:8001/desktop`
- Planner: `http://127.0.0.1:8001/`
- Management Studio: `http://127.0.0.1:8001/management-studio`
- Data on Windows: `%LOCALAPPDATA%\Align\align.sqlite3`
- Data elsewhere: `$XDG_DATA_HOME/align` or `~/.local/share/align`
- Logs: `studio.log` and `studio-error.log` in that same folder

`ALIGN_DATA_DIR` chooses a different data folder. `ALIGN_PORT` chooses a different port (8001 if unset).

`python app.py` is the existing server entry point. It still stores `align.sqlite3` beside the source unless `ALIGN_DATA_DIR` is set. The desktop programme does not change that.

Useful checks without opening a window:

```powershell
py -3.12 -m desktop --dry-run
py -3.12 -m desktop --no-browser
```

`--serve` runs the server in the foreground until you stop it.

## Build a Windows executable

From the repository root, on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
```

That installs PyInstaller into the Python you use to build, then writes:

```text
dist\Align\Align.exe
```

The folder next to `Align.exe` is part of the programme. Copy the whole `dist\Align` folder. A one-file executable is not used, because the planner's pages and migrations have to stay beside the programme.

You can run the same command yourself:

```powershell
py -3.12 -m pip install --upgrade pip pyinstaller
py -3.12 -m pip install -r requirements.txt
py -3.12 -m PyInstaller --noconfirm --clean desktop/align.spec
```

GitHub Actions workflow `Align Management Studio Windows package` runs this build and uploads `Align-Management-Studio-Windows.zip`.

## Install on Windows

1. Unzip the package.
2. Run `Install-Align-Studio.ps1`.
3. Open the **Align** shortcut on the desktop.

The programme is copied to `%LOCALAPPDATA%\Programs\Align Management Studio`. Planner data stays in `%LOCALAPPDATA%\Align`. Installing again does not delete that database.

A package that contains the application source but not `Align.exe` still needs Python 3.12 or newer. The installer creates a private virtual environment and starts `python -m desktop`.

Uninstall by deleting the programme folder. Leave `%LOCALAPPDATA%\Align` in place if you want to keep the planner. Deleting that folder deletes the local database.

## What the first launch does with an older database

If `%LOCALAPPDATA%\Align\align.sqlite3` already has planner content, it is opened and left as it is.

If that file is missing, or it is blank, and an older `align.sqlite3` is sitting beside the programme or in an `app` folder, the programme copies the older file into the data folder. The older file is not deleted. A blank file that was replaced is renamed beside the data folder with a `.blank-` or `.unreadable-` suffix.

`ALIGN_LEGACY_DATABASES` can list older database files, separated by the system path separator. Set it to an empty value to skip that search.

## Tests

```powershell
py -3.12 -m unittest test_desktop_programme.py
node --check static/desktop.js
node --check static/management-studio-calendar.js
node test_desktop_shell.js
```

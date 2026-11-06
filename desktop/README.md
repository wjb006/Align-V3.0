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

## Updates

Check for updates on the desktop home screen or in Settings. Align compares the running commit with the latest commit on `codex/align-v3-rebuild` and, when you ask, downloads that commit as a zip over HTTPS. It does not use git and it does not replace the programme file.

Downloaded code is staged in `%LOCALAPPDATA%\Align\app-code`. The next launch uses that folder when it contains the Align pages, server modules, and migrations and names the commit it came from. Otherwise the programme uses the code bundled in `Align.exe`. A download that does not then become healthy is set aside on the following launch, and the bundled code is used. Planner data is not part of the download.

A GitHub token is optional. On Windows it is stored in Credential Manager, or as a DPAPI blob if Credential Manager cannot store it. It is not written into the planner database. Check when Align opens is off until you turn it on, and that check does not download code.

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

## Local sign-in

The installed desktop programme requires a local Owner sign-in. On first launch, create the local Owner account with an email address, display name, and password of at least 12 characters. Later launches restore the session automatically when **Keep me signed in** is selected (30 days). If it is not selected, the browser session ends when its profile closes and the server-side session expires after 12 hours. Use **Sign out** on the desktop home screen to revoke the current session.

Local authentication is separate from hosted beta accounts and from the planner database. The account and hashed session records are stored in `desktop-auth.sqlite3` in the desktop data folder (normally `%LOCALAPPDATA%\\Align`). Passwords are salted PBKDF2-HMAC-SHA256 hashes; the browser receives only an HttpOnly, SameSite=Strict session cookie. Sign-in does not migrate, overwrite, or delete `align.sqlite3`.

## Rota photo and scanned-PDF reading

Align's rota reader uses **local Tesseract OCR**. Photo pixels and scanned PDF pages are processed on the computer running Align; the OCR code does not send rota files to a third-party OCR or AI service. CSV, XLSX and text-based PDFs continue to use their existing direct readers.

For a Windows source run:

1. Install the Tesseract OCR Windows runtime (English language data must be included).
2. Open PowerShell and confirm `tesseract --version` works.
3. If Tesseract is not on PATH, set `ALIGN_TESSERACT_CMD` to the full path of `tesseract.exe`, for example `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`.
4. Reopen Align. Work > Upload my rota checks the installed runtime and shows which formats are available.

The Python dependencies for image decoding and scanned-PDF rendering are installed with `requirements.txt`. HEIC reading is reported separately and is enabled only when the HEIC decoder is present. The GitHub Windows test-package workflow installs a pinned Tesseract 5.5.3 runtime and bundles its executable, DLLs and language data alongside Align. The local `desktop\\build_windows.ps1` build also bundles Tesseract when it is installed in the standard Program Files location or `ALIGN_TESSERACT_HOME`. Source runs still need Tesseract installed separately. Every build must be checked through Work > Upload my rota; the capability response is the source of truth for photo, HEIC and scanned-PDF support.

OCR is best-effort: glare, skew, low resolution, handwriting and dense multi-person tables can reduce accuracy. Every extracted row remains in the review screen; nothing enters the planner until it is explicitly approved. Shared rotas are rejected, and the source upload is deleted after processing.

# Align programme

This folder is the programme to keep. It is the planner, Management Studio, and Windows installer from `codex/align-v3-rebuild` at `9a45a37`. Tests, old checklists, and one-off scripts stayed in the rest of the repository.

```
programme/
  Install-Align-Studio.ps1    Windows installer
  Launch-Align-Studio.ps1     Starts an installed source copy
  app/                        Planner, Management Studio, and desktop programme
  studio-launcher/            Optional Go starter for a source install
```

On Windows, run `Install-Align-Studio.ps1` from this folder. It copies `app\` into `%LOCALAPPDATA%\Programs\Align Management Studio` and adds an Align shortcut on the desktop. Planner data stays in `%LOCALAPPDATA%\Align`. A built package uses `Align\Align.exe` beside the installer instead of `app\`. Build that on Windows with `app\desktop\build_windows.ps1`.

From source, with Python 3.12 or newer:

```powershell
cd app
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m desktop
```

Home is `http://127.0.0.1:8001/desktop`. `python app.py` is the same server and stores `align.sqlite3` in the folder where you start it.

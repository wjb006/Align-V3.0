# Align V3.0 desktop rebuild

27 October 2026. Branch `cursor/windows-desktop-rebuild-d937`. There is no `main` branch on `wjb006/Align-V3.0`. `origin/HEAD` is `codex/align-v3-rebuild`, and that is the tree this work started from.

## What was there

Align is a Python `ThreadingHTTPServer` plus a browser app. The planner is `/`. Management Studio is `/management-studio`. Local data is SQLite (`align.sqlite3`). Hosted data is Postgres and is a separate service.

The Windows “programme” was three pieces:

- `studio-launcher/`, a Go executable that started `launch.py` and opened a browser window on `/management-studio`.
- `installer/windows/Install-Align-Studio.ps1`, which required Python 3.12 on the PC, created a virtual environment, and copied the source tree.
- The Python server itself, started by `launch.py` / `app.py`.

`docs/management-studio-host-platform.md` described an App / Studio / Host shell and said it had not been implemented. The Studio page already had those sections. The app pane was an iframe that the server refused to display (`X-Frame-Options: DENY` and `frame-ancestors 'none'` on every response, including `/`). The host pane said live checks were not connected, which was accurate and also meant the screen could not show the local health check that `/api/health` already returns.

The installer copied a database out of the programme folder onto `%LOCALAPPDATA%\Align\align.sqlite3` and then deleted the programme-folder copy. If both existed, the programme-folder file replaced the data-folder file. The Go launcher did not set `ALIGN_DATA_DIR` itself. Only the PowerShell wrapper did. Starting the `.exe` directly stored data beside the programme, where the next install could remove it.

A brand-new database created by the desktop programme has no legacy `alerts` table. Opening the planner called `/api/bootstrap`, and `dashboard()` still queried `alerts`, so the screen stopped on “Unable to load Align: no such table: alerts”. Older databases that still have that table keep the same reminder rows.

The working calendar listed events by the day they started, so an event crossing midnight disappeared from the second day. The day/hour view grouped an event only by its start hour, so a 09:30–11:00 event did not occupy 10:00. Event buttons did not open details. Add existed. Edit did not, even though `PUT /api/organiser-events/{id}` already saved changes.

There is no separate native planner. The features live in the Python server and the pages under `static/`.

## What changed

- `python -m desktop` is the programme. It chooses the data folder, adopts an older database without deleting it, starts the existing server if Align is not already on the port, and opens `/desktop`.
- `/desktop` is a home screen with Planner, Management Studio, and a local status card. Status comes from `/api/health` and `/api/desktop/status`. The public site is named and is not checked.
- PyInstaller spec `desktop/align.spec` builds `dist/Align/Align.exe` (a folder build, not one file). `desktop/build_windows.ps1` is the Windows build. The GitHub workflow builds that package. The installer uses `Align.exe` when it is present and does not delete a database.
- The Go launcher now runs `python -m desktop` and passes the same data-folder environment. It remains a thin starter for a source install. The packaged programme is the PyInstaller executable.
- Studio’s app pane can embed `/` because that document is now `SAMEORIGIN`. API responses stay `DENY`.
- Host overview shows the local health check and says the public site was not checked. Release dispatch is unchanged.
- The working calendar positions timed events by start and end, includes events that overlap a day, and can open, add, and edit saved Align events. Imported events stay read-only.
- A frozen programme tells the Updates button to install a new package instead of running `git pull`. Saved data is not part of that update.
- A fresh database can open the planner. `dashboard()` and the calendar feed return an empty legacy `alerts` / `alert_rules` list when those tables are absent, and still read them when an older database has them.
- `python app.py` still uses the database beside the process unless `ALIGN_DATA_DIR` is set. Record formats and API paths are unchanged.

Cache-version checks in `test_ui_polish.py`, `test_ui_polish.js`, `test_display_dates.js`, and `verify_align_build156.py` expected `156-v46` or `156-v47` while the pages already referenced `156-v56`. Those checks now expect `156-v56`. The shell cache itself was not bumped.

## What was verified here

- `python -m unittest test_desktop_programme.py test_studio_update.py test_extracted_routes.py test_ui_polish.py`: 28 tests passed. That includes a live server, `/api/bootstrap` on a fresh database, an empty legacy-alert list, and a database that still has `alerts` / `alert_rules`.
- `node test_desktop_shell.js`, `node test_ui_polish.js`, and `node test_display_dates.js` passed.
- `go test ./...` in `studio-launcher` passed.
- Screenshots from that local server: desktop home, planner with a saved event, Management Studio, working calendar month and day/hour views, an open event, and Host overview. The planner no longer stops on “no such table: alerts”.

This environment cannot produce a Windows `.exe`. The spec and the Windows workflow are the build. They have not been executed on Windows in this session.

## Follow-up on this branch

- The day/hour grid scrolls to the current hour when that day is today, and marks the hour. Opening an event keeps the scroll position.
- `/api/alerts` and `/api/alert-rules` return an empty list when those tables are missing. A fresh database now creates the tables, so a reminder can be saved. A write against a database that still lacks them says the reminders are not stored, instead of reporting a missing table.
- The Go launcher again waits until Align is healthy, refuses another programme on the port, and opens one window. It starts Python with `--no-browser` so the window is not opened twice.
- A source install still reads `%LOCALAPPDATA%\Align\studio-environment.ps1` when that file exists, then sets the data folder. Reinstalling removes the old “Align Management Studio” shortcut.

## Left open

- The Windows executable has not been launched on Windows, and the installer has not been clicked through on a PC.
- The executable is not code-signed.
- Programme updates for an installed `Align.exe` are “install the new package”. Studio’s git update still works for a source checkout.
- Host overview does not probe https://getalign.co.uk and does not perform backup, restore, or deploy. Those actions stay on their existing Studio controls.
- `python app.py` and `python -m desktop` can point at different database files. See the decision below.

## Decisions for Will

1. **Two local databases, on purpose.** The desktop shortcut and `python -m desktop` use `%LOCALAPPDATA%\Align\align.sqlite3`. `python app.py` and `Start Align.bat` keep using `align.sqlite3` in the folder where the server is started. The first desktop launch copies an older programme-folder database only when the Align data folder does not already contain planner content. If both already have different records, the data-folder copy wins and the other file is left untouched. Say if you would rather the shortcut keep opening the copy next to the source.

2. **Folder build, not a single `.exe`.** `dist\Align\` has to stay together. A single-file executable would unpack on every start and makes the migrations and pages harder to find. Say if you want a one-file build anyway.

3. **Public site health.** This screen does not call getalign.co.uk, so it cannot show a false “healthy”. A real check would be a loopback-only server request with a short timeout, still without secrets. Say if you want that added.

4. **Signing and auto-update.** The package is unsigned. Windows will warn on first launch. An installed programme does not update itself. Say if you want a signed certificate and an updater, or if replacing the folder and keeping `%LOCALAPPDATA%\Align` is enough.

5. **Go launcher.** It is still tested and still starts the Python programme for a source install. The zip from GitHub Actions now contains `Align.exe`, not the Go executable. Say if the Go launcher should stay in the zip as a second way to start a source tree.

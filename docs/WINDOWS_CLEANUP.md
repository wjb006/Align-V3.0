# Old Align copies on a Windows PC

This is a checklist only. It does not connect to a PC, and it does not delete anything by itself.

The hosted app at https://www.getalign.co.uk is separate from copies installed on a Windows computer. Cleaning up a PC does not change the hosted database.

Before deleting anything, decide whether the local planner should be kept. Local data is not the same file as the hosted account.

## Find the copies

1. Look for a Start menu or desktop shortcut named Align or Align Management Studio.
2. The installed programme, when present, is under `%LOCALAPPDATA%\Programs\Align Management Studio`.
3. The desktop programme's planner database is `%LOCALAPPDATA%\Align\align.sqlite3`. Logs in that same folder are `studio.log` and `studio-error.log`.
4. A downloaded code update, when present, is `%LOCALAPPDATA%\Align\app-code`.
5. A test build, when present, uses `%LOCALAPPDATA%\Align-Test` and port `8011`. It is separate from the normal database.
6. A copy started with `Start Align.bat` or `python app.py` keeps `align.sqlite3` in the folder where that server was started. That file is not the same as `%LOCALAPPDATA%\Align\align.sqlite3`.
7. Optional local transport files, when present, are an OTP runtime folder and a local NaPTAN file next to that server. They are not needed for the hosted site.

## If the local planner should be kept

1. Copy `%LOCALAPPDATA%\Align` to a USB drive or another folder you control.
2. If a second `align.sqlite3` sits next to `Start Align.bat`, copy that file too and label which one it is.
3. Do not upload those files to the hosted site as part of this cleanup. They contain the local account.

## Remove the programme, not the data

1. Close Align, including any window left open at `http://127.0.0.1:8001`.
2. Delete the programme folder `%LOCALAPPDATA%\Programs\Align Management Studio` if you no longer want the desktop app.
3. Delete the Start menu and desktop shortcuts that point at that folder or at `Start Align.bat`.
4. Leave `%LOCALAPPDATA%\Align` in place until you have confirmed the copy from the step above.
5. Leave `%LOCALAPPDATA%\Align-Test` only if you still use the test build. Otherwise it can be deleted on its own. It does not hold the normal planner.

## After that

1. Use https://www.getalign.co.uk in the browser, or the Home Screen icon, for the hosted account.
2. Sign in there with the hosted email and password. The Windows programme password is a different store (`desktop-auth.sqlite3` in the Align data folder).
3. When you are sure the hosted account has what you need, deleting `%LOCALAPPDATA%\Align` removes the local database. That cannot be undone from the hosted service.

# Align on Windows

This package installs the local Align programme: the planner and Management Studio.

- Programme: `%LOCALAPPDATA%\Programs\Align Management Studio`
- Planner data and logs: `%LOCALAPPDATA%\Align`
- Desktop shortcut: Align
- Home screen: `http://127.0.0.1:8001/desktop`

A packaged build includes `Align\Align.exe` and does not need a separate Python install. A source package still needs Python 3.12 or newer.

The installer does not delete or replace `align.sqlite3`. If this computer already has planner data in the Align data folder, that copy is the one that opens. An older database beside a previous install is copied only when the data folder does not already have planner content. The older file is left where it is.

Logs: `%LOCALAPPDATA%\Align\studio.log` and `studio-error.log`.

This programme does not change Render, DNS, the hosted database, or credentials. https://getalign.co.uk stays online when this PC is off.

Build instructions are in [`desktop/README.md`](../../desktop/README.md).

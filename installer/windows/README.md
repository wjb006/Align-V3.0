# Align Management Studio — Windows installer

This package installs a local Windows control hub for Align V3.0.

- Program files: %LOCALAPPDATA%\Programs\Align Management Studio
- Local data/logs: %LOCALAPPDATA%\Align
- Desktop shortcut: Align Management Studio
- Local Studio: http://127.0.0.1:8001/studio

Python 3.12 and an internet connection are required for first-time dependency setup. Install Python from https://www.python.org/downloads/windows/ and enable PATH support, then run Install-Align-Studio.ps1 from the extracted package.

The local Studio and hosted Align site are separate. This installer does not change Render, DNS, production databases, or credentials. The hosted app remains online when this PC is off.

Logs are stored in %LOCALAPPDATA%\Align\studio.log and studio-error.log.

## Studio build ethos

The implementation principles and release gates are documented in [`docs/MANAGEMENT_STUDIO_BUILD_ETHOS.md`](../../../docs/MANAGEMENT_STUDIO_BUILD_ETHOS.md). The dedicated working calendar must support Month, Week, Day, and Day/Hour time-grid views using real Align events; it is separate from calendar appearance settings. The hosted app must remain independent of the local PC, and the installer must preserve local data and credentials.

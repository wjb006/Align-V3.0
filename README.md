# Align V3.0

Align is a personal organiser with a Python `ThreadingHTTPServer` backend and a vanilla JavaScript PWA. The Owner Management Studio publishes onboarding questions and database-backed sections. User records are stored in `builder_records` and validated against the published section fields.

## Current release status

The local V3.0 build includes configurable Sections, optional Work records, user-managed iCloud calendars, and Microsoft Graph account email delivery. The current build is not deployed and is not ready for external testers: legacy shift code remains, hosted PostgreSQL and a V3 Render service are not provisioned, and the Microsoft/Apple integrations still require account credentials and live checks. See [BUILD_CHECKLIST.md](BUILD_CHECKLIST.md) for the current evidence and handoff.

## Local development

Use Python 3.12. Create a virtual environment, install the listed requirements and run `python app.py`. The app opens at `http://127.0.0.1:8001`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
.\.venv\Scripts\python.exe app.py
```

Run the local regression suite with `.\.venv\Scripts\python.exe -m pytest -q`. Browser regressions use the pinned Playwright package under `browser-tests/`.

## Hosted deployment

The hosted service starts with `python render_start.py`. Configure a dedicated Neon database and set the environment names listed in [ENVIRONMENT.md](ENVIRONMENT.md). Apply the numbered PostgreSQL migrations to `align_owner` and every tester schema before enabling the service. Hosted Studio uploads require an S3-compatible persistent bucket: configure `AWS_ENDPOINT_URL_S3`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `ALIGN_ASSET_BUCKET`; the app blocks hosted uploads when this storage is missing. Never reuse the existing Align installation's database or credential key. The current deployment checklist remains incomplete; do not point the old Align Render service or existing domain records at this repository.

`dist/*.exe`, local SQLite databases, secrets and `otp-runtime/` are not source files. The OTP graph builder requires a separately installed Java 21 runtime; keep packaged executables as release artifacts.

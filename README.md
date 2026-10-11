# Align V3.0

Align is a personal organiser with a Python `ThreadingHTTPServer` backend and a vanilla JavaScript PWA. The Owner Management Studio publishes onboarding questions and database-backed sections. User records are stored in `builder_records` and validated against the published section fields.

## Live build signs

These badges follow the development branch and update automatically when GitHub Actions runs.

[![Browser regressions](https://github.com/wjb006/Align-V3.0/actions/workflows/build-browser.yml/badge.svg?branch=codex%2Falign-v3-rebuild)](https://github.com/wjb006/Align-V3.0/actions/workflows/build-browser.yml)
[![Hosted persistence](https://github.com/wjb006/Align-V3.0/actions/workflows/hosted-persistence.yml/badge.svg?branch=codex%2Falign-v3-rebuild)](https://github.com/wjb006/Align-V3.0/actions/workflows/hosted-persistence.yml)
[![Navigation checks](https://github.com/wjb006/Align-V3.0/actions/workflows/pr-navigation-checks.yml/badge.svg?branch=codex%2Falign-v3-rebuild)](https://github.com/wjb006/Align-V3.0/actions/workflows/pr-navigation-checks.yml)

**Latest verified CI baseline:** commit [594cd085](https://github.com/wjb006/Align-V3.0/commit/594cd085e52bd2a014426ab6ef61e65a76fd34f8) — browser regressions, hosted persistence integration tests, and navigation checks all passed on 11 October 2026.

> Green CI means the automated workflows passed. It does not mean production hosting is ready. The V3.0 release remains blocked on a shift-safe final schema/migration plan, hosted Neon/Render provisioning, durable object-storage credentials, and live authentication, sync, backup/restore, and device checks. The old Align app and its domain/DNS remain untouched until release gates pass. Track the work in [BUILD_CHECKLIST.md](BUILD_CHECKLIST.md).

## Local development

Use Python 3.12. Create a virtual environment, install the listed requirements and run `python app.py`. The app opens at `http://127.0.0.1:8001`.

```powershell
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt pytest
.\\.venv\\Scripts\\python.exe app.py
```

Run the local regression suite with `.\\.venv\\Scripts\\python.exe -m pytest -q`. Browser regressions use the pinned Playwright package under `browser-tests/`.

## Hosted deployment

The hosted service starts with `python render_start.py`. Configure a dedicated Neon database and set the environment names listed in [ENVIRONMENT.md](ENVIRONMENT.md). Apply the numbered PostgreSQL migrations to `align_owner` and every tester schema before enabling the service. Hosted Studio uploads require an S3-compatible persistent bucket: configure `AWS_ENDPOINT_URL_S3`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `ALIGN_ASSET_BUCKET`; the app blocks hosted uploads when this storage is missing. Never reuse the existing Align installation's database or credential key. Do not point the old Align Render service or existing domain records at this repository until the release gates are complete.

`dist/*.exe`, local SQLite databases, secrets and `otp-runtime/` are not source files. The OTP graph builder requires a separately installed Java 21 runtime; keep packaged executables as release artifacts.

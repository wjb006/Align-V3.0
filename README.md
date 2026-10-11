# Align V3.0

Align is a personal organiser with a Python `ThreadingHTTPServer` backend and a vanilla JavaScript PWA. The Owner Management Studio publishes onboarding questions and database-backed sections. User records are stored in `builder_records` and validated against the published section fields.

## Local development

Use Python 3.12. Create a virtual environment, install the listed requirements and run `python app.py`. The app opens at `http://127.0.0.1:8001`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
.\.venv\Scripts\python.exe app.py
```

Run the local regression suite with `.\.venv\Scripts\python.exe -m pytest -q`. Browser regressions use the pinned Playwright package under `browser-tests/`.

## Hosted deployment

The hosted service starts with `python render_start.py`. Configure a dedicated Neon database and set the environment names listed in [ENVIRONMENT.md](ENVIRONMENT.md). Apply the numbered PostgreSQL migrations to `align_owner` and every tester schema before enabling the service. Never reuse the existing Align installation's database or credential key.

`dist/*.exe`, local SQLite databases, secrets and `otp-runtime/` are not source files. The OTP graph builder requires a separately installed Java 21 runtime; keep packaged executables as release artifacts.

"""Verify Align V3.0 Build 156 source and offline asset version consistency."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    checks = {
        "server build": re.search(r"^BUILD_VERSION = (\d+)", (ROOT / "app.py").read_text(encoding="utf-8"), re.M),
        "client build": re.search(r"const BUILD_VERSION = (\d+)", (ROOT / "static/app.js").read_text(encoding="utf-8")),
        "worker build": re.search(r"const BUILD = (\d+)", (ROOT / "static/service-worker.js").read_text(encoding="utf-8")),
    }
    for name, match in checks.items():
        if not match or match.group(1) != "156":
            print(f"STOP: {name} is not Build 156.")
            raise SystemExit(1)
    asset_version = "156-v36"
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    if asset_version not in index or "Align V3.0" not in index:
        print("STOP: index.html does not reference the Align V3.0 Build 156 assets.")
        raise SystemExit(1)
    app_js = (ROOT / "static/app.js").read_text(encoding="utf-8")
    worker = (ROOT / "static/service-worker.js").read_text(encoding="utf-8")
    if f"`${{BUILD_VERSION}}-v36`" not in app_js or f"`${{BUILD}}-v36`" not in worker:
        print("STOP: app or service-worker asset cache version is stale.")
        raise SystemExit(1)
    print("PASS — Align V3.0 Build 156 version and offline asset consistency verified.")


if __name__ == "__main__":
    main()

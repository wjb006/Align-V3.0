"""PyInstaller runtime hook for the isolated Align V3.0 test build.

Runs before desktop.app_code is imported so test data, port and update branch
are fixed before any updater or database path is initialised.
"""
import os
from pathlib import Path

_local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
os.environ["ALIGN_DATA_DIR"] = str(_local / "Align-Test")
os.environ["ALIGN_LEGACY_DATABASES"] = ""
os.environ["ALIGN_PORT"] = "8011"
os.environ["ALIGN_UPDATE_BRANCH"] = "test/align-v3-ready-20261106"
os.environ["ALIGN_TEST_BUILD"] = "1"
os.environ["ALIGN_STUDIO_LOCAL"] = "1"
os.environ["ALIGN_BETA_MODE"] = "0"
os.environ["ALIGN_LOCAL_LOGIN_ENABLED"] = "1"

try:
    from desktop.app_code import prepare_runtime
    prepare_runtime()
except Exception:
    # The normal launch health check reports failures without falling back to
    # the user's standard Align data directory.
    pass

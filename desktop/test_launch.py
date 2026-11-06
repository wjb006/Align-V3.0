"""Safe entry point for the isolated Align V3.0 Windows test build."""
from __future__ import annotations

import os
from pathlib import Path

if os.name == "nt":
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    os.environ["ALIGN_DATA_DIR"] = str(local / "Align-Test")
    # Never adopt or copy the user's normal Align database into this test build.
    os.environ["ALIGN_LEGACY_DATABASES"] = ""
    # Run beside the normal desktop app without competing for its port.
    os.environ["ALIGN_PORT"] = "8011"
    # Keep test-build updates on the test branch, never on the normal dev branch.
    os.environ["ALIGN_UPDATE_BRANCH"] = "test/align-v3-readiness"
    os.environ["ALIGN_TEST_BUILD"] = "1"
    os.environ["ALIGN_STUDIO_LOCAL"] = "1"
    os.environ["ALIGN_BETA_MODE"] = "0"
    os.environ["ALIGN_LOCAL_LOGIN_ENABLED"] = "1"

from desktop.launch import main

if __name__ == "__main__":
    raise SystemExit(main())

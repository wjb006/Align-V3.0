# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Align V3.0 desktop programme.

Build from the repository root:
    py -3.12 -m PyInstaller --noconfirm --clean desktop/align.spec
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
TEST_BUILD = os.environ.get("ALIGN_TEST_BUILD") == "1"
APP_NAME = "Align V3.0 Test" if TEST_BUILD else "Align"
ENTRY_SCRIPT = "test_launch.py" if TEST_BUILD else "__main__.py"

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "migrations"), "migrations"),
    (str(ROOT / "schema.sql"), "."),
    (str(ROOT / "schema_v3.sqlite.sql"), "."),
    (str(ROOT / "merseyside_stops.json"), "."),
    (str(ROOT / "transport_sources.json"), "."),
    (str(ROOT / "transport_schema.sql"), "."),
]

# Bundle the local Tesseract executable, its Windows DLLs and English model
# into the onedir application. No OCR service or network request is used.
tesseract_dir = Path(os.environ.get("TESSERACT_INSTALL_DIR", "")).expanduser()
if tesseract_dir.is_dir():
    for candidate in tesseract_dir.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(tesseract_dir)
        if candidate.name.lower() == "tesseract.exe" or candidate.suffix.lower() == ".dll" or relative.as_posix().lower() == "tessdata/eng.traineddata":
            datas.append((str(candidate), str(Path("ocr") / relative.parent)))

hidden = [
    "app",
    "align_paths",
    "desktop",
    "desktop.launch",
    "desktop.status",
    "desktop.persistence",
    "desktop.supervisor",
    "beta_support",
    "icloud_sync",
    "postgres_support",
    "studio_update",
    "studio_deploy",
]
hidden += collect_submodules("desktop")
hidden += collect_submodules("pytesseract")
hidden += collect_submodules("fitz")
hidden += collect_submodules("pillow_heif")

a = Analysis(
    [str(ROOT / "desktop" / ENTRY_SCRIPT)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "desktop" / "pyi_rth_appcode.py")],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    icon=str(ROOT / "static" / "icons" / "align.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

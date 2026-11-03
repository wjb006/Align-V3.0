# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Align V3.0 desktop programme.

Build from the repository root:
    py -3.12 -m PyInstaller --noconfirm --clean desktop/align.spec
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "migrations"), "migrations"),
    (str(ROOT / "schema.sql"), "."),
    (str(ROOT / "schema_v3.sqlite.sql"), "."),
    (str(ROOT / "merseyside_stops.json"), "."),
    (str(ROOT / "transport_sources.json"), "."),
    (str(ROOT / "transport_schema.sql"), "."),
]

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

a = Analysis(
    [str(ROOT / "desktop" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Align",
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
    name="Align",
)

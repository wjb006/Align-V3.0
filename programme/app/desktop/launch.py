"""Launch Align on this computer and open the desktop home screen."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from desktop.errors import DesktopError
from desktop.paths import install_dir, legacy_database_candidates, user_data_dir
from desktop.persistence import adopt_database, inspect_database
from desktop.supervisor import chosen_port, fetch_health, start_server
from desktop.window import open_window


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="align",
        description="Open the Align V3.0 planner and Management Studio on this computer.",
    )
    parser.add_argument("--serve", action="store_true", help="Run the local server until it is stopped.")
    parser.add_argument("--dry-run", action="store_true", help="Print the launch plan without starting Align or copying data.")
    parser.add_argument("--no-browser", action="store_true", help="Start Align without opening a window.")
    parser.add_argument("--port", type=int, default=None, help="Loopback port. Defaults to ALIGN_PORT or 8001.")
    return parser.parse_args(argv)


def home_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/desktop"


def report_error(message: str) -> None:
    text = message.strip() or "Align could not open."
    print(text, file=sys.stderr)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "Align", 0x10)
        except (AttributeError, OSError):
            return


def _write_state(data_dir: Path, port: int, database_action: str) -> None:
    payload = {
        "port": port,
        "database_action": database_action,
        "surface": "local-desktop",
    }
    path = data_dir / "desktop-state.json"
    temporary = path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def _serve(data_dir: Path) -> int:
    os.environ["ALIGN_DATA_DIR"] = str(data_dir)
    os.environ["ALIGN_STUDIO_LOCAL"] = "1"
    os.environ["ALIGN_BETA_MODE"] = "0"
    import app
    app.main()
    return 0


def run(args: argparse.Namespace) -> int:
    data_dir = user_data_dir()
    port = chosen_port(args.port)
    legacy = legacy_database_candidates(install_dir())
    if args.serve:
        adopt_database(data_dir, legacy)
        return _serve(data_dir)
    plan = inspect_database(data_dir, legacy)
    ready, responding = fetch_health(port) if port else (False, False)
    if args.dry_run:
        print(f"data: {data_dir}")
        print(f"database: {plan['action']}")
        if plan.get("source") and plan["action"] == "copy":
            print(f"database-source: {plan['source']}")
        if ready:
            print(f"server: already-running {port}")
        elif responding:
            print(f"server: blocked {port}")
        else:
            print(f"server: start {port}")
        print("open", home_url(port))
        return 0
    if responding and not ready:
        raise DesktopError(
            f"Port {port} is already in use by something that is not Align. "
            "Close that programme or set ALIGN_PORT to another port."
        )
    # A server that is already up owns its open database. Do not copy files under it.
    if ready:
        if not args.no_browser:
            try:
                open_window(home_url(port))
            except OSError as error:
                raise DesktopError(f"Align is already running at {home_url(port)}. Open that address.") from error
        return 0
    adopted = adopt_database(data_dir, legacy)
    handle = start_server(data_dir, port)
    port = handle.port
    _write_state(data_dir, port, str(adopted["action"]))
    if not args.no_browser:
        try:
            open_window(home_url(port))
        except OSError as error:
            print(f"Align is ready at {home_url(port)}", file=sys.stderr)
            print("A window could not be opened. Use the address above.", file=sys.stderr)
            if handle is not None:
                return 0
            raise DesktopError(f"Align is running at {home_url(port)}, but a window could not be opened.") from error
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except DesktopError as error:
        report_error(str(error))
        return 1
    except KeyboardInterrupt:
        print("Align stopped. Saved planner data was kept.", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

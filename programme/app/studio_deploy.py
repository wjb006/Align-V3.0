"""Dispatch verified Align releases through the repository's GitHub workflow."""
from __future__ import annotations

import re
import shutil
import subprocess

REPOSITORY = "wjb006/Align-V3.0"
WORKFLOW = "deploy-align-v3.yml"
WORKFLOW_URL = f"https://github.com/{REPOSITORY}/actions/workflows/{WORKFLOW}"
DEFAULT_REF = "codex/align-v3-rebuild"
_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")


def validate_release(ref: str, target: str) -> tuple[str, str]:
    if not isinstance(ref, str):
        raise ValueError("Choose a GitHub branch or tag.")
    ref = ref.strip()
    if (
        not _REF_PATTERN.fullmatch(ref)
        or ".." in ref
        or "//" in ref
        or "@{" in ref
        or ref.endswith(("/", "."))
        or any(part.endswith(".lock") for part in ref.split("/"))
    ):
        raise ValueError("Enter a valid GitHub branch or tag name.")
    if target != "production":
        raise ValueError("Only the configured production app can be released right now.")
    return ref, target


def _gh_path() -> str:
    path = shutil.which("gh")
    if not path:
        raise RuntimeError("GitHub CLI is not installed on this PC.")
    return path


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=flags,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("GitHub CLI did not respond in time.") from error
    except OSError as error:
        raise RuntimeError("GitHub CLI could not be started.") from error


def availability() -> dict:
    path = shutil.which("gh")
    if not path:
        return {
            "available": False,
            "reason": "Install GitHub CLI and sign in on this PC to send code releases.",
        }
    result = _run([path, "auth", "status", "--hostname", "github.com"], timeout=12)
    if result.returncode != 0:
        return {
            "available": False,
            "reason": "Sign in to GitHub CLI on this PC before sending a release.",
        }
    return {
        "available": True,
        "reason": "GitHub is connected. Releases run the checks before requesting a Render deploy.",
    }


def dispatch_release(ref: str, target: str) -> dict:
    ref, target = validate_release(ref, target)
    state = availability()
    if not state["available"]:
        raise RuntimeError(state["reason"])
    path = _gh_path()
    result = _run(
        [
            path,
            "workflow",
            "run",
            WORKFLOW,
            "--repo",
            REPOSITORY,
            "--ref",
            DEFAULT_REF,
            "--field",
            f"source_ref={ref}",
            "--field",
            f"target={target}",
        ],
        timeout=60,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            raise RuntimeError(f"GitHub could not start the release: {detail[:400]}")
        raise RuntimeError("GitHub could not start the release.")
    return {
        "ok": True,
        "ref": ref,
        "target": target,
        "workflow_url": WORKFLOW_URL,
        "summary": "Release checks were queued on GitHub. Render is updated only if they pass.",
    }

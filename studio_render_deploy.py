"""Deploy a previously tested Align commit to the configured Render service."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

RENDER_API = "https://api.render.com/v1"
EXPECTED_SERVICE_NAME = "align-v3"
EXPECTED_REPOSITORY = "https://github.com/wjb006/Align-V3.0"
PRODUCTION_HEALTH_URL = "https://getalign.co.uk/api/health"
SERVICE_ID_PATTERN = re.compile(r"^srv-[A-Za-z0-9]+$")
FAILED_STATUSES = {
    "build_failed",
    "update_failed",
    "pre_deploy_failed",
    "canceled",
    "deactivated",
}


def _request_json(path: str, api_key: str, method: str = "GET", payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{RENDER_API}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Render API request failed with HTTP {error.code}.") from error
    except urllib.error.URLError as error:
        raise RuntimeError("Could not reach the Render API.") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Render returned an unreadable response.") from error


def _check_public_health(url: str = PRODUCTION_HEALTH_URL):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"Production health check returned HTTP {response.status}.")
            health = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Production health check returned HTTP {error.code}.") from error
    except urllib.error.URLError as error:
        raise RuntimeError("Production health check could not reach getalign.co.uk.") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Production health check returned unreadable data.") from error
    if health.get("version", {}).get("app") != "3.0":
        raise RuntimeError("Production health check did not identify Align 3.0.")
    if health.get("database", {}).get("available") is not True:
        raise RuntimeError("Production is responding, but its database health check failed.")


def run_deployment(
    environ=None,
    request_json=_request_json,
    health_check=_check_public_health,
    sleep=time.sleep,
    clock=time.monotonic,
):
    env = os.environ if environ is None else environ
    api_key = env.get("RENDER_API_KEY", "").strip()
    service_id = env.get("ALIGN_RENDER_SERVICE_ID", "").strip()
    commit_id = env.get("TESTED_SHA", "").strip()
    if not api_key:
        raise RuntimeError("The production GitHub environment is missing RENDER_API_KEY.")
    if not SERVICE_ID_PATTERN.fullmatch(service_id):
        raise RuntimeError("The production GitHub environment has an invalid ALIGN_RENDER_SERVICE_ID.")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
        raise RuntimeError("The release workflow did not provide a tested commit SHA.")

    encoded_service_id = urllib.parse.quote(service_id, safe="")
    status, service = request_json(f"/services/{encoded_service_id}", api_key)
    if status != 200:
        raise RuntimeError(f"Render service lookup returned HTTP {status}.")
    if service.get("name") != EXPECTED_SERVICE_NAME:
        raise RuntimeError("The configured Render service is not named align-v3; deployment stopped.")
    actual_repository = str(service.get("repo", "")).rstrip("/").removesuffix(".git").casefold()
    if actual_repository != EXPECTED_REPOSITORY.casefold():
        raise RuntimeError("The configured Render service is not connected to wjb006/Align-V3.0.")

    status, deployment = request_json(
        f"/services/{encoded_service_id}/deploys",
        api_key,
        method="POST",
        payload={"commitId": commit_id},
    )
    if status == 202:
        raise RuntimeError("Render already has a deployment in progress. Wait for it to finish, then retry.")
    if status != 201 or not deployment.get("id"):
        raise RuntimeError(f"Render did not create the deployment (HTTP {status}).")

    deploy_id = urllib.parse.quote(str(deployment["id"]), safe="")
    deadline = clock() + 1800
    while clock() < deadline:
        status, current = request_json(
            f"/services/{encoded_service_id}/deploys/{deploy_id}",
            api_key,
        )
        if status != 200:
            raise RuntimeError(f"Render deployment status returned HTTP {status}.")
        state = current.get("status")
        if state == "live":
            reported_commit = (current.get("commit") or {}).get("id") or current.get("commitId")
            if reported_commit and reported_commit.casefold() != commit_id.casefold():
                raise RuntimeError("Render reports a different commit than the one that passed checks.")
            health_check()
            return {
                "deploy_id": deployment["id"],
                "commit_id": commit_id,
                "status": "live",
            }
        if state in FAILED_STATUSES:
            raise RuntimeError(f"Render deployment ended with status '{state}'.")
        sleep(20)
    raise RuntimeError("Render did not finish the deployment within 30 minutes.")


if __name__ == "__main__":
    result = run_deployment()
    print(f"Render deployment {result['deploy_id']} is live for tested commit {result['commit_id']}.")

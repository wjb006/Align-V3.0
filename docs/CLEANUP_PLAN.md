# Align V3.0 cleanup plan

Audit date: 9 November 2026.  
Repository: `wjb006/Align-V3.0`.  
Default branch: `codex/align-v3-rebuild` at `c3d2a71` (15:46 UTC), merge of pull request #134.  
This document is the only change in the audit pull request. Nothing was merged, deleted, force-pushed, closed, or deployed. Production data was not read or changed. A read-only `GET /api/health` was used to check that the live service is up.

Will's PC tracks `codex/align-v3-rebuild`. There is no `main` or `master` branch, and there are no tags.

## How to approve this in one go

Reply with the safe steps and the decisions you want. A later change can then do exactly that list.

Suggested reply:

- Safe: S1, S2, S3
- Decisions: D1 keep and open a PR, D2 delete `programme/` after a Windows check, D4 bump Pillow and retest, D5 fix the clock and add the timeline spec to CI, D6 leave cache strings for a later UI pass, D7 refresh the three docs, D8 and D9 only if the Go launcher stays, D10 keep the mockups

## Done on 9 November 2026

These are open for review. None of them are merged.

| Item | Result |
| --- | --- |
| S1 | The ten `copilot/*` branches were deleted. Each tip was already in `codex/align-v3-rebuild`. `wjb006-fix-travel-and-weather` is still there. |
| S2, S3 | https://github.com/wjb006/Align-V3.0/pull/136 |
| D1 | https://github.com/wjb006/Align-V3.0/pull/137 |
| D2 | https://github.com/wjb006/Align-V3.0/pull/141 |
| D4 | https://github.com/wjb006/Align-V3.0/pull/138 |
| D5 | https://github.com/wjb006/Align-V3.0/pull/139 |
| D7 | https://github.com/wjb006/Align-V3.0/pull/140 |

Still waiting: D3 (Align-app launcher), D6 (cache strings), D8 and D9 (Go and Playwright, only if the Go launcher stays), D10 (mockups kept).

## 1. Branches

Ahead and behind are measured against `origin/codex/align-v3-rebuild` (`c3d2a71`). "Contained" means the branch tip is already an ancestor of that commit, so the branch has no unique work.

| Branch | Last commit (UTC) | Ahead | Behind | Contained | Recommendation |
| --- | --- | --- | --- | --- | --- |
| `codex/align-v3-rebuild` | 2026-11-09 15:46 `c3d2a71` Merge PR #134 | 0 | 0 | yes | **Keep.** This is the default branch. |
| `wjb006-fix-travel-and-weather` | 2026-11-09 14:37 `59990e2` Fix timeline travel review feedback | 1 | 16 | no | **Rebase and open a PR.** Do not delete until D1 is decided. |
| `copilot/94264b21d65f87fa0e061a7f868ecd4a317ea352` | 2026-11-08 01:01 `94264b2` Test HERE pedestrian access configuration | 0 | 57 | yes | **Delete as merged.** |
| `copilot/fix-failing-github-actions-job-please-work` | 2026-10-25 10:25 `9f25355` Initial plan | 0 | 723 | yes | **Delete as merged.** |
| `copilot/fix-persistence-github-actions-job` | 2026-10-25 10:19 `f4f25fd` Initial plan | 0 | 732 | yes | **Delete as merged.** |
| `copilot/fix-failing-github-actions-job-one-more-time` | 2026-10-25 10:15 `9a512b2` Initial plan | 0 | 743 | yes | **Delete as merged.** |
| `copilot/fix-persistence-job-failure` | 2026-10-25 10:14 `2c30f77` Initial plan | 0 | 743 | yes | **Delete as merged.** |
| `copilot/fix-mobile-chrome-pixel7-job` | 2026-10-25 10:11 `0f54981` Initial plan | 0 | 746 | yes | **Delete as merged.** |
| `copilot/fix-failing-github-actions-job-another-one` | 2026-10-25 09:57 `e6ff4fa` Initial plan | 0 | 767 | yes | **Delete as merged.** |
| `copilot/fix-failing-github-action-mobile-chrome` | 2026-10-25 09:57 `0c614f7` Initial plan | 0 | 767 | yes | **Delete as merged.** |
| `copilot/fix-desktop-chromium-failure-again` | 2026-10-25 09:45 `2afc998` Initial plan | 0 | 776 | yes | **Delete as merged.** |
| `copilot/fix-failing-github-actions-job` | 2026-10-25 09:38 `1ef920c` Initial plan | 0 | 781 | yes | **Delete as merged.** |

Twelve remote branches were present at the start of the audit, including the default. The ten `copilot/*` rows were deleted on 9 November 2026 after this table was written. `git merge-tree` of `wjb006-fix-travel-and-weather` onto `c3d2a71` completes with no conflicts.

### The one unmerged commit

Pull request #132 merged commit `1eac630` ("Fix timeline travel review feedback") at 14:39 UTC. The branch tip `59990e2` is a second commit with the same message, parented on `1eac630`, and it is not in the default branch. The patch is three files, 46 insertions:

- `post_event_travel.py`: a non-drive route returns the provider's first usable journey even when the route has no deadline. On the default branch that shortcut only runs when a deadline is set; otherwise the earliest arrival wins.
- `test_post_event_travel.py`: `test_transit_without_deadline_keeps_provider_order`.
- `browser-tests/timeline.spec.js`: extra checks for strip wrapping and for reusing a saved journey. It does not fix the clock failure in section 5.

## 2. Pull requests

Open pull requests: **none**. Nothing is conflicted, review-blocked, or waiting to merge.

Totals from GitHub search on 9 November 2026: 115 merged, 19 closed and unmerged, 0 open. The latest merged request is #134.

The 19 closed-unmerged requests already have their branches deleted. Do not reopen them. They are duplicates of work that landed in other requests, or abandoned Copilot attempts from 25 October. The list is in the appendix.

## 3. Duplicate, dead, and superseded files

Tracked tree is about 7.6 MB across 525 files. No tracked `.exe`, `dist/`, `__pycache__`, `.pyc`, or SQLite database. `rsrc_windows_amd64.syso` under the Go launchers is a small Windows resource blob used by the Go build, not a stray PyInstaller output.

Canonical runtime, from the Dockerfile, `render.yaml`, and `desktop/align.spec`:

- Root `app.py`, root `static/`, root `migrations/`, root `desktop/`.
- Service worker asset version on this commit: build **158**, asset **`158-v92`** (`static/service-worker.js`). Live `GET /api/health` on `https://www.getalign.co.uk` and `https://getalign.co.uk` returned HTTP 200, build 158, app 3.0, mode beta, Postgres available. Hosted migrations are reported as externally managed, which is what `health_backup.py` returns for Postgres.

### `programme/` is a second, drifted tree

`programme/README.md` says this folder is the programme to keep and that it matches `9a45a37` (28 October 2026, pull request #61). The 4 November repair audit (`docs/FULL_REPAIR_AUDIT.md`) says the opposite: root is canonical and `programme/app/` must not be copied back over it. Deploy and the PyInstaller spec follow the root.

| Comparison | Result |
| --- | --- |
| Tracked size | 2,693.6 KB, 156 files |
| Identical to current root | 77 files, 1,765,520 bytes |
| Different from current root | 70 files, 958,322 bytes |
| Versus the claimed snapshot `9a45a37` | 126 identical, 21 different, 0 missing |

The 21 files that no longer match `9a45a37` include `app.py`, `static/app.js`, `static/service-worker.js`, and the Management Studio pages. `programme/app/requirements.txt` also omits `requirements-ocr.txt`, which the root file includes. The copy is neither current nor a clean snapshot.

Identical large files that exist only twice because of this copy:

| File | Size | Notes |
| --- | --- | --- |
| `merseyside_stops.json` and `programme/app/merseyside_stops.json` | 749,669 bytes each | Same SHA-256. Root is the file the app loads. |
| `static/journey-icons/train.png` and the `programme/app` copy | 209,634 bytes each | Same SHA-256. |
| `static/icon.svg` | 99,030 bytes at root, 274 bytes in `programme/app` | Different files. Root is current. |

`studio-launcher/` is 30,657 bytes. `programme/studio-launcher/` is 28,744 bytes and differs in `main.go` and `main_test.go`. `programme/app/desktop/` is a shorter copy of `desktop/` (it has no `auth.py`, `update.py`, or `secrets.py`). `programme/Install-Align-Studio.ps1` differs from `installer/windows/Install-Align-Studio.ps1`.

### Windows launchers, and Align-app

This token can see only `wjb006/Align-V3.0`. `https://github.com/wjb006/Align-app` returned 404, so this audit could not diff that repository. These are the launcher copies inside this repo:

| Path | Role | Recommendation |
| --- | --- | --- |
| `desktop/` and `desktop/align.spec` | Local Windows programme. PyInstaller builds `dist/Align/Align.exe`. The Windows workflow packages this. | **Keep** unless Align-app has taken the local programme as well. |
| `studio-launcher/` | Go starter (`go 1.22`) that runs `python -m desktop` and opens `/desktop`. | The Windows workflow still builds `dist/Align-Management-Studio.exe` from it, then does not put that exe in the zip. See D3. |
| `programme/studio-launcher/` and `programme/app/desktop/` | Older copies. | Delete with `programme/` if D2 is yes. |
| Root `Start Align*.bat`, `align.ps1`, OTP and Merseyside scripts | Local server and OpenTripPlanner starters. `personal_otp.py` still tells the user to run `Start Align Merseyside.bat`. `Start Align.bat` calls it. | **Keep.** They are not the hosted launcher. |

### Other leftovers

- Root `149_asset_studio.sql` (10,164 bytes) and `149_asset_studio_rollback.sql` (1,218 bytes) differ from `migrations/`. The migration runner reads `migrations/` only. The root asset-studio script still wraps itself in `BEGIN IMMEDIATE` / `COMMIT` and has weaker checks than the migrations copy. See S3.
- `scripts/` (`Build-Align-V3-Test.ps1`, `Configure-Align-Render.ps1`) and `Scripts/` (`Clean-Align.ps1`, `Update-AlignFolders.ps1`) are two directories that differ only by case. Nothing in the repo references the `Scripts/` path. On a case-insensitive Windows checkout one directory can hide the other. See S2.
- The three unreferenced HTML mockups named in D10 have been deleted.
- Beta, desktop, Management Studio, owner-builder, widget and phone-notification pages now use the shell token `158-v94`. See D6.
- `.github/workflows/live-health.yml` still requests `https://align-beta-preview.onrender.com/api/health`. That URL returned HTTP 404 on 9 November 2026. See D7.
- `.github/workflows/build-158-windows.yml` only runs on push to `test/align-v3-build-158`, which no longer exists, plus a manual dispatch. It can stay as a manual archive builder or be folded into the current Windows workflow later.
- `docs/FULL_REPAIR_AUDIT.md` (4 November) is partly out of date: rota OCR is now implemented and the Docker image runs the real OCR test. `BUILD_CHECKLIST.md` still describes an 11 October CI baseline and says the Render service is not created. The live health check shows build 158 on getalign.co.uk. `programme/README.md` contradicts the root README. See D7.

## 4. Dependencies and security

`pip-audit` against the installed environment (the versions `requirements*.txt` resolved to in this VM) reported one package. Every other installed distribution was clean. `npm audit` in `browser-tests/` reported 0 vulnerabilities.

Pillow is pinned exactly at **12.3.0** in `requirements-asset-studio.txt`. `pip-audit` reported **39 advisory records** for that version, covering **21 CVE/GHSA identifiers**, and every record is fixed in **Pillow 13.0.0**:

`CVE-2026-96638`, `CVE-2026-96640`, `CVE-2026-96778`, `CVE-2026-112390`, `CVE-2026-112391`, `CVE-2026-112393`, `CVE-2026-112395`, `CVE-2026-112399`, `CVE-2026-112400`, `CVE-2026-112401`, `CVE-2026-112404`, `CVE-2026-112406`, `CVE-2026-112891`, `CVE-2026-112892`, `CVE-2026-112893`, `CVE-2026-112894`, `CVE-2026-112895`, `CVE-2026-112897`, `CVE-2026-112899`, `CVE-2026-112900`, `GHSA-78g4-xqwv-q3g8`.

The extra records are PYSEC aliases of those identifiers. This audit did not re-score each advisory. Pillow is on the upload path: `asset_studio.py` opens uploaded images, and `rota_ocr_provider.py` opens rota photos. A major pin move needs a test run (D4). It was not changed here.

Other version notes, none of which produced an advisory:

| Item | Here | Current check on 9 November 2026 |
| --- | --- | --- |
| Playwright | pinned `1.65.0` in `browser-tests/package.json` | Was `1.63.0`. npm latest on 9 November 2026 was `1.65.0`. |
| Go module | `go 1.27.4` in `studio-launcher/go.mod` | Was `go 1.22`. Stable `go1.27.4` was published on 2 November 2026. |
| Python | 3.12, Docker `python:3.12-slim-bookworm` | Still the version the repo and CI request. |
| Other Python pins | ranges such as `cryptography>=45,<51`, `psycopg[binary]>=3.2,<4`, `caldav==3.2.1` | Resolved install was clean under `pip-audit`. There is no lockfile, so a future install can still float inside the ranges. |

## 5. Tests run in this VM

GitHub Actions are billing-locked, so nothing was dispatched. Commands were run locally on commit `c3d2a71` with hosted credentials unset. No `DATABASE_URL` was present in the environment.

### Python

```text
.venv/bin/python -m pytest -q
394 passed, 7 skipped, 34 subtests passed in 112.81s
exit 0
```

Skipped, and why:

| Test | Reason |
| --- | --- |
| `test_here_quota.py::test_shared_quota_survives_connections_and_concurrency` | Needs `ALIGN_TEST_POSTGRES_URL`. This VM has no Postgres client. |
| `test_hosted_persistence.py::PostgresIntegrationTests::test_fresh_v3_schema_starts_without_legacy_schedule_tables` | Same. The class refuses any host other than loopback `align_persistence_test`. |
| `...::test_tester_schema_includes_restored_shift_planner_ddl` | Same. |
| `...::test_schema_survives_commit_rollback_and_sql_boundaries` | Same. |
| `...::test_owner_restart_inbox_and_adapter_contract` | Same. |
| `test_work_rota_import.py` real OCR test | Tesseract is not installed in this VM. The Docker image does install it and runs this test at build time. |
| `test_rota_ocr_provider.py` real OCR test | Same. |

The hosted-persistence workflow already runs the Postgres tests against a disposable `postgres:18` service. That job was not run here.

### Node syntax and plain Node tests

`node --check` passed for the 13 scripts named in `.github/workflows/pr-navigation-checks.yml`.

All 12 navigation scripts in that workflow passed: `test_core_navigation.js`, `test_page_scripts.js`, `test_ui_polish.js`, `test_display_dates.js`, `test_travel_autofill.js`, `test_related_travel.js`, `test_post_event_travel_ui.js`, `test_weather_timeout.js`, `test_work_calendar_entry.js`, `test_work_shift_autofill.js`, `test_work_rota_entry.js`, `test_desktop_shell.js`.

Nine further Node scripts passed and are not in that workflow: `test_scriptable_bridge.js`, `test_today_weather.js`, `test_travel_results.js`, `test_weather_views.js`, `test_widget_views.js`, `test_align_v22.js`, `test_apple_maps_links.js`, `test_journey_breakdown.js`, `test_phone_push_worker.js`.

### Go

`go test ./...` in `studio-launcher` passed (`ok align-management-studio`).

### Browser

Playwright `1.63.0`, headless.

| Spec | Chromium desktop | Pixel 7 | WebKit desktop | iPhone 13 |
| --- | --- | --- | --- | --- |
| `browser-tests/align.spec.js` | pass | pass | pass | pass |
| `browser-tests/address-suggestions.spec.js` | pass | pass | pass | pass |
| `browser-tests/timeline.spec.js` | **fail** | **fail** | **fail** | not re-run |

`timeline.spec.js` is not in `.github/workflows/build-browser.yml`, so the green CI browser job would not have run it. The failure is the same in each browser: the first compact item's text is `Leave` / `09:00`, and the spec expects `/08:00/`. The fixture time is `2030-10-01T08:00`, which is during British Summer Time. `journeyClock` in `static/journey-breakdown.js` does `new Date(value)` and then formats `Europe/London`. A value with no offset is parsed in the host timezone. This VM is UTC, so 08:00 UTC is displayed as 09:00 in London. `parseAlignDateTime` in `static/post-event-travel.js` already treats offset-less planner times as London wall clocks. `journeyClock` does not. A machine whose local zone is already London can pass this spec by accident. See D5.

## 6. Prioritised plan

### Safe once you say yes

These do not change planner behaviour. They were not done in this pull request.

**S1. Delete ten merged Copilot branches.** Delete the ten `copilot/*` branches in the table. Each tip is already contained in `codex/align-v3-rebuild`. Leave `wjb006-fix-travel-and-weather` until D1 is done. Do not force-push.

**S2. Collapse `Scripts/` into `scripts/`.** Move `Clean-Align.ps1` and `Update-AlignFolders.ps1` into `scripts/`. The filenames do not collide with `Build-Align-V3-Test.ps1` or `Configure-Align-Render.ps1`. No reference to the capitalised path was found. This removes the case collision on Windows.

**S3. Remove the stale root Asset Studio SQL pair.** Delete root `149_asset_studio.sql` and `149_asset_studio_rollback.sql` only. Keep `migrations/149_asset_studio.sql`, `schema.sql`, `schema_v3.sqlite.sql`, and `transport_schema.sql`. The runner and the health check read `migrations/`. Before deleting, confirm no shortcut outside the repo executes the root filenames. The Docker `COPY *.sql` line will simply stop copying the stale pair; `COPY migrations` remains.

### Needs a decision

**D1. Travel follow-up on `wjb006-fix-travel-and-weather`.** Rebase the one commit onto current `codex/align-v3-rebuild` and open a PR, or drop it. The behaviour change is real: non-drive journeys with no deadline keep provider order instead of picking the earliest arrival. The merge onto `c3d2a71` is clean. Do not delete the branch until you choose.

**D2. Delete `programme/`.** Recommended, as its own pull request, after you confirm no Windows machine still installs from `programme/Install-Align-Studio.ps1` or `programme/app`. That removes the 2.7 MB drifted copy, the duplicate stops file, the duplicate train icon, and the old desktop and Go copies. Update `programme/README.md` by deleting it with the folder. Do not copy `programme/app` back over the root.

**D3. Which Windows launcher lives in this repo.** Keep `desktop/` and `desktop/align.spec` as the local programme. Confirm whether `https://github.com/wjb006/Align-app` now owns the hosted Windows launcher. If it does, stop building the unused Go exe in `.github/workflows/windows-studio-installer.yml` and either keep `studio-launcher/` as the source-install starter or remove it in that same PR. This audit could not read Align-app.

**D4. Move Pillow from 12.3.0 to 13.0.0.** Do this in its own pull request and rerun pytest plus the rota and Asset Studio image tests. Both requirement copies must change if `programme/` still exists; if D2 lands first, only the root pin remains.

**D5. Make journey clocks use London wall time, then put `timeline.spec.js` in the browser workflow.** `journeyClock` should treat offset-less timestamps the way `parseAlignDateTime` does, then the spec should expect `08:00` on a UTC runner. Until that lands, the spec fails on UTC and is invisible to CI.

**D6. Cache-busting strings.** Done. Beta, desktop, Management Studio, owner-builder, widget, and phone-notification pages use `158-v94`, the same token as `static/index.html` and the service worker. Per-record image versions (`?v=${a.version}`) are unchanged.

**D7. Docs and the dead health URL.** Rewrite the release-gate section of `BUILD_CHECKLIST.md` so it matches build 158 on getalign.co.uk, and mark `docs/FULL_REPAIR_AUDIT.md` as historical or update the OCR and hosting gaps. Retarget `live-health.yml` from `align-beta-preview.onrender.com` (HTTP 404) to `https://www.getalign.co.uk/api/health`, or delete the workflow. The check should keep printing only version, mode, and database availability.

**D8. Go toolchain.** Done. `studio-launcher/go.mod` asks for Go 1.27.4, the stable release published on 2 November 2026. The launcher stays until D3 is decided.

**D9. Playwright.** Done. `browser-tests/package.json` pins Playwright 1.65.0.

**D10. Mockups.** Done. `daily-timeline-mockup.html`, `today-weather-mockup.html`, and `work-shift-autofill-mockup.html` are deleted. Nothing else referenced them.

### Explicitly leave alone

- Beta account modules, `/api/beta/*`, and `ALIGN_BETA_MODE`. The November repair audit already says these stay until there is a migration and rollback plan. The live service is in beta mode.
- Root `schema.sql` and `schema_v3.sqlite.sql`. Fresh SQLite uses the V3 file. `schema.sql` is still the compatibility initialiser and is packaged by `desktop/align.spec`.
- Merseyside and OTP batch files. They are still how local transport is started.
- Production Render, Neon, DNS, object storage, and secrets. This plan does not change them.

## Appendix: closed unmerged pull requests

Branches for all of these are already gone.

| PR | Closed (UTC) | Head branch | Title |
| --- | --- | --- | --- |
| 99 | 2026-11-06 18:19 | `test/align-v3-completion-20261106` | Build 157 test version |
| 98 | 2026-11-06 18:23 | `test/align-v3-readiness` | Build Align V3.0 test release with local rota OCR |
| 76 | 2026-10-29 14:09 | `feature/studio-live-app-mirror-ci-ready` | Management Studio phone preview mirror |
| 75 | 2026-10-29 14:07 | `feature/studio-live-app-mirror-tested` | same title |
| 74 | 2026-10-29 14:06 | `feature/studio-live-app-mirror-final-checks` | same title |
| 73 | 2026-10-29 14:04 | `feature/studio-live-app-mirror-release` | same title |
| 72 | 2026-10-29 14:03 | `feature/studio-live-app-mirror-final` | same title |
| 71 | 2026-10-29 14:02 | `feature/studio-live-app-mirror-verified` | same title |
| 50–40 | 2026-10-25 11:13 | `copilot/fix-*-job*` | Abandoned Copilot CI-flake attempts, closed together |

PRs 98 and 99 were closed the same day #100 merged the build 157 test release. The Studio mirror series was closed within ten minutes; later Studio work merged through #130. PRs 40–50 match the leftover Copilot branches that are already contained in the default branch.

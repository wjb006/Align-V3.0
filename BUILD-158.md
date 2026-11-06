# Align V3.0 — Build 158

Status: isolated Windows test build; not a production release.

## Release contents

- Application and server build identifiers aligned at 158.
- Static asset cache advanced to 158-v72 to prevent stale Build 157 files being reused.
- Guided planner-section setup and guided event entry are included.
- Migration 158 adds saved places, planner labels, section defaults, and organiser event details.
- Build 157 Work rota import, local desktop Owner sign-in, and bundled local Tesseract OCR remain included.
- Test installation remains isolated at `%LOCALAPPDATA%\Align-Test` on port `8011`.

## Safety

The test installer must not adopt, migrate, overwrite, or open the normal database at `%LOCALAPPDATA%\Align\align.sqlite3`. This branch does not deploy to Render, Neon, or production domains.

## Verification gate

The Windows builder runs the regression suite, JavaScript syntax checks, Go launcher tests, PyInstaller packaging, and package-content checks. A ZIP is a completed test candidate only after every gate passes.

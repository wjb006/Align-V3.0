# Align V3.0 Test — Windows

This is an isolated test build, not a production release.

## Install

1. Extract the ZIP to a normal folder.
2. Right-click `Install-Align-Test.ps1` and choose **Run with PowerShell**, or run it from PowerShell.
3. Open **Align V3.0 Test** from the desktop shortcut.

The test executable is deliberately built with a separate entry point:

- Programme: `%LOCALAPPDATA%\Programs\Align V3.0 Test`
- Test database and local Owner sign-in: `%LOCALAPPDATA%\Align-Test`
- Test web address: `http://127.0.0.1:8011/desktop`
- Update branch: `test/align-v3-ready-20261106`

It does **not** adopt, copy, migrate, open or overwrite the normal Align database at `%LOCALAPPDATA%\Align\align.sqlite3`. It also uses a different port, so the normal Align desktop app can remain installed and running.

On first launch, create a separate local Owner account for the test build. Do not reuse a production password.

## Included test areas

- Local desktop sign-in and remembered session
- Work Settings and the restored shift planner
- Rota upload from CSV, Excel, PDF and supported photos
- Local Tesseract OCR for JPEG/JPG, PNG and HEIC/HEIF
- Scanned and mixed text/scanned PDF extraction
- Review and correction before importing shifts
- Saving new workplaces and shift areas from rota review
- Planner, calendar, travel and reminder regression coverage
- Management Studio, Owner builder and asset-storage regression coverage

## Important

This test build is not connected to the live Render/Neon database and is not a production deployment. Rota uploads are temporary during processing; only reviewed fields are retained after approval. OCR runs locally and does not send the image or PDF to an external OCR provider.

To remove the test installation, close it and delete `%LOCALAPPDATA%\Programs\Align V3.0 Test` and `%LOCALAPPDATA%\Align-Test`. Leave the normal `%LOCALAPPDATA%\Align` folder alone.

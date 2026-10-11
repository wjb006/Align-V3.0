@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Align - Save Remote Access Token

echo ==============================================
echo       ALIGN - SAVE REMOTE ACCESS TOKEN
echo ==============================================
echo.
echo This stores the Cloudflare Tunnel token encrypted with Windows DPAPI.
echo It can only be decrypted by your current Windows account on this PC.
echo.
echo In Cloudflare: Networking ^> Tunnels ^> your Align tunnel ^> Add a replica.
echo Copy ONLY the long token value from the cloudflared command.
echo.

if not exist ".align_beta" mkdir ".align_beta"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$secure = Read-Host 'Paste tunnel token' -AsSecureString;" ^
  "if ($secure.Length -lt 20) { throw 'That token looks too short.' };" ^
  "$secure | ConvertFrom-SecureString | Set-Content -LiteralPath '.align_beta\tunnel-token.dpapi' -Encoding UTF8;" ^
  "Write-Host ''; Write-Host 'Align remote access token saved securely.'"

if not %errorlevel%==0 (
  echo.
  echo Token was not saved.
  pause
  exit /b 1
)

echo.
pause

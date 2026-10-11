#requires -Version 5.1
<#
.SYNOPSIS
  Installs optional Align integrations from one grouped setup menu.
.DESCRIPTION
  Shared Python environment setup for iCloud, hosted Owner/remote access,
  and local iPhone HTTPS support. It never stores credentials.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

function Find-Python {
    $candidates = @()
    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { $candidates += $venvPython }
    foreach ($name in @('py.exe','python.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        try {
            & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    throw 'Python 3.10 or later was not found. Install Python, then run this setup again.'
}

function Get-AlignPython {
    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    $python = Find-Python
    if ((Split-Path -Leaf $python) -ieq 'py.exe') {
        & $python -3 -m venv (Join-Path $Root '.venv')
    } else {
        & $python -m venv (Join-Path $Root '.venv')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Align .venv.' }
    if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Align .venv was not created.' }
    return $venvPython
}

function Install-Requirements([string]$File) {
    $requirements = Join-Path $Root $File
    if (-not (Test-Path -LiteralPath $requirements)) { throw "Missing optional dependency list: $File" }
    $python = Get-AlignPython
    & $python -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "Installing $File failed." }
}

function Install-HttpsSupport {
    $python = Get-AlignPython
    & $python -m pip install 'cryptography>=45'
    if ($LASTEXITCODE -ne 0) { throw 'Installing HTTPS support failed.' }
    & $python (Join-Path $Root 'https_setup.py') --serve-ca
    if ($LASTEXITCODE -ne 0) { throw 'The temporary iPhone certificate setup did not complete.' }
}

function Install-RemoteAccess {
    Install-Requirements 'requirements-accounts.txt'
    if (Get-Command cloudflared.exe -ErrorAction SilentlyContinue) {
        Write-Host 'Cloudflare Tunnel is already installed.'
        return
    }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'Install cloudflared from https://developers.cloudflare.com/tunnel/downloads/, then run this setup again.' }
    & $winget.Source install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Cloudflare Tunnel installation failed.' }
}

Write-Host ''
Write-Host 'Align V3.0 optional setup' -ForegroundColor Cyan
Write-Host '1. iCloud calendar support'
Write-Host '2. Owner accounts and remote access'
Write-Host '3. iPhone HTTPS certificate support'
Write-Host '4. Install all optional Python packages and remote access'
Write-Host '0. Exit'
$choice = Read-Host 'Choose an option'

try {
    switch ($choice) {
        '1' { Install-Requirements 'requirements-icloud.txt' }
        '2' { Install-RemoteAccess }
        '3' { Install-HttpsSupport }
        '4' {
            Install-Requirements 'requirements-icloud.txt'
            Install-RemoteAccess
            $python = Get-AlignPython
            & $python -m pip install 'cryptography>=45'
            if ($LASTEXITCODE -ne 0) { throw 'Installing HTTPS certificate support failed.' }
            Write-Host 'Optional packages are installed. Choose option 3 when you are ready to install the iPhone certificate.'
        }
        '0' { exit 0 }
        default { throw 'Choose 0, 1, 2, 3, or 4.' }
    }
    Write-Host ''
    Write-Host 'Align optional setup completed.' -ForegroundColor Green
} catch {
    Write-Host "`nSetup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

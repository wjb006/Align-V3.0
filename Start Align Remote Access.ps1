$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Write-Step([string]$Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Fail([string]$Text) { Write-Host "`nERROR: $Text" -ForegroundColor Red; throw $Text }
function Read-LogTail([string]$Path, [int]$Lines = 25) {
    if (Test-Path -LiteralPath $Path) {
        Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction SilentlyContinue
    }
}
function Test-LocalAccountService {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8010/api/beta/status' -TimeoutSec 3
        if ($r.StatusCode -ne 200) { return $false }
        $j = $r.Content | ConvertFrom-Json
        return [bool]$j.beta
    } catch { return $false }
}

Write-Host '=============================================='
Write-Host '        ALIGN V3.0 - REMOTE ACCESS'
Write-Host '=============================================='

if (-not (Test-Path -LiteralPath '.\app.py')) { Fail 'app.py was not found. Put this launcher inside the Align folder.' }
$appText = Get-Content -Raw -LiteralPath '.\app.py'
$m = [regex]::Match($appText, '(?m)^BUILD_VERSION\s*=\s*(\d+)')
if (-not $m.Success -or [int]$m.Groups[1].Value -lt 137) { Fail 'This launcher requires Align Build 137 or later.' }
$build = [int]$m.Groups[1].Value
Write-Host "Align Build $build detected."

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { Fail 'Run Install Align Add-ons.bat and choose Owner accounts and remote access first. The .venv Python was not found.' }
$cloudflared = (Get-Command cloudflared.exe -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) { Fail 'cloudflared.exe was not found. Run Install Align Add-ons.bat and choose Owner accounts and remote access first.' }
if (-not (Test-Path -LiteralPath '.\beta_users.sqlite3')) { Fail 'Run Set Up Align Owner.bat first.' }

# Important: refuse to launch over an existing server. The old launcher could
# health-check an older process and then accidentally tunnel to it.
if (Test-LocalAccountService) {
    Fail 'An Align server is already running on port 8010. Close every old Align Server window, wait 3 seconds, then run this launcher again.'
}
try {
    $listener = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
    if ($listener) { Fail 'Port 8010 is already in use by another program. Close the old process before starting Align.' }
} catch {
    if ($_.Exception.Message -like 'Port 8010*' -or $_.Exception.Message -like 'An Align*') { throw }
}

$stateDir = Join-Path $PSScriptRoot '.align_beta'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$serverOut = Join-Path $stateDir 'beta-server-out.log'
$serverErr = Join-Path $stateDir 'beta-server-err.log'
$tunnelOut = Join-Path $stateDir 'cloudflared-out.log'
$tunnelErr = Join-Path $stateDir 'cloudflared-err.log'
$currentUrl = Join-Path $stateDir 'CURRENT BETA URL.txt'
Remove-Item $serverOut,$serverErr,$tunnelOut,$tunnelErr,$currentUrl -Force -ErrorAction SilentlyContinue

$server = $null
$tunnel = $null
try {
    Write-Step 'Starting Align locally on 127.0.0.1:8010'
    if (-not $env:ALIGN_TRANSPORT_ENABLED) { $env:ALIGN_TRANSPORT_ENABLED = '1' }
    if (-not $env:ALIGN_OTP_URL) { $env:ALIGN_OTP_URL = 'http://127.0.0.1:8080/otp/gtfs/v1' }
    $env:ALIGN_BETA_MODE = '1'
    $env:ALIGN_PORT = '8010'
    $server = Start-Process -FilePath $python -ArgumentList @('launch.py','--beta') -WorkingDirectory $PSScriptRoot -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -PassThru -WindowStyle Hidden

    $ready = $false
    for ($i=0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if ($server.HasExited) { break }
        if (Test-LocalAccountService) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Host "`n--- Align server output ---" -ForegroundColor Yellow
        Read-LogTail $serverOut
        Read-LogTail $serverErr
        Fail 'Align did not stay running on port 8010.'
    }
    Write-Host 'LOCAL CHECK: PASS' -ForegroundColor Green

    $tokenFile = Join-Path $stateDir 'tunnel-token.dpapi'
    if (Test-Path -LiteralPath $tokenFile) {
        Write-Step 'Starting saved stable Cloudflare Tunnel'
        $enc = (Get-Content -Raw -LiteralPath $tokenFile).Trim()
        $sec = ConvertTo-SecureString $enc
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try { $env:TUNNEL_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        $tunnel = Start-Process -FilePath $cloudflared -ArgumentList @('tunnel','run') -WorkingDirectory $PSScriptRoot -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelErr -PassThru -WindowStyle Hidden
        Write-Host 'Stable Align tunnel process started. Use your configured Align hostname.' -ForegroundColor Green
    } else {
        Write-Step 'Starting a fresh Cloudflare Quick Tunnel'
        $tunnel = Start-Process -FilePath $cloudflared -ArgumentList @('tunnel','--url','http://127.0.0.1:8010') -WorkingDirectory $PSScriptRoot -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelErr -PassThru -WindowStyle Hidden

        $url = $null
        for ($i=0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            if ($tunnel.HasExited) { break }
            $text = ''
            if (Test-Path $tunnelOut) { $text += (Get-Content -Raw $tunnelOut -ErrorAction SilentlyContinue) }
            if (Test-Path $tunnelErr) { $text += "`n" + (Get-Content -Raw $tunnelErr -ErrorAction SilentlyContinue) }
            $u = [regex]::Match($text, 'https://[a-z0-9-]+\.trycloudflare\.com', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if ($u.Success) { $url = $u.Value; break }
        }
        if (-not $url) {
            Write-Host "`n--- Cloudflare output ---" -ForegroundColor Yellow
            Read-LogTail $tunnelOut
            Read-LogTail $tunnelErr
            Fail 'Cloudflare did not produce a Quick Tunnel URL.'
        }
        Set-Content -LiteralPath $currentUrl -Value $url -Encoding UTF8
        Write-Host "PUBLIC URL: $url" -ForegroundColor Green

        Write-Step 'Waiting for the new public URL to become reachable'
        $publicOK = $false
        $publicStatus = "$url/api/beta/status"
        $lastPublicError = $null

        # Quick Tunnels can be announced before the public hostname is fully usable.
        # Give Cloudflare up to 2 minutes, and do NOT kill a healthy tunnel merely
        # because this local PowerShell probe cannot verify the public edge.
        for ($i=0; $i -lt 24; $i++) {
            Start-Sleep -Seconds 5
            if ($server.HasExited -or $tunnel.HasExited) { break }
            try {
                $r = Invoke-WebRequest -UseBasicParsing -Uri $publicStatus -TimeoutSec 8 -MaximumRedirection 5
                if ($r.StatusCode -eq 200) {
                    $j = $r.Content | ConvertFrom-Json
                    if ($j.beta) { $publicOK = $true; break }
                }
                $lastPublicError = "HTTP $($r.StatusCode)"
            } catch {
                $lastPublicError = $_.Exception.Message

                # Windows PowerShell/network policy can occasionally disagree with
                # Safari/Edge. Try the built-in curl.exe as a second probe.
                try {
                    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
                    if ($curl) {
                        $body = & $curl.Source -fsS --max-time 8 $publicStatus 2>$null
                        if ($LASTEXITCODE -eq 0 -and $body) {
                            $cj = $body | ConvertFrom-Json
                            if ($cj.beta) { $publicOK = $true; break }
                        }
                    }
                } catch { }
            }
        }

        if ($server.HasExited) {
            Write-Host "`n--- Align server output ---" -ForegroundColor Yellow
            Read-LogTail $serverOut 40
            Read-LogTail $serverErr 40
            Fail 'Align stopped while the public tunnel was starting.'
        }
        if ($tunnel.HasExited) {
            Write-Host "`n--- Cloudflare output ---" -ForegroundColor Yellow
            Read-LogTail $tunnelOut 40
            Read-LogTail $tunnelErr 40
            Fail 'Cloudflare stopped while the public tunnel was starting.'
        }

        if ($publicOK) {
            Write-Host 'PUBLIC CHECK: PASS' -ForegroundColor Green
        } else {
            Write-Host "`nPUBLIC CHECK: NOT CONFIRMED (tunnel remains running)" -ForegroundColor Yellow
            if ($lastPublicError) { Write-Host "Last automatic check: $lastPublicError" -ForegroundColor DarkYellow }
            Write-Host 'Cloudflare registered successfully and Align is still healthy locally.' -ForegroundColor Yellow
            Write-Host 'Open the URL below manually in Safari/Edge. Do NOT close this window.' -ForegroundColor Yellow
        }

        Write-Host "`nUSE THIS EXACT ADDRESS:`n$url" -ForegroundColor White -BackgroundColor DarkGreen
        Write-Host "`nThe current remote access address is saved in Align's local state folder."
        try { Start-Process $url } catch { }
    }

    Write-Host "`nAlign is running. Keep THIS window open." -ForegroundColor Green
    Write-Host 'Press Ctrl+C to stop Align and the tunnel.'
    while ($true) {
        Start-Sleep -Seconds 3
        if ($server.HasExited) {
            Write-Host "`nALIGN SERVER STOPPED unexpectedly." -ForegroundColor Red
            Read-LogTail $serverOut 40
            Read-LogTail $serverErr 40
            break
        }
        if ($tunnel.HasExited) {
            Write-Host "`nCLOUDFLARE TUNNEL STOPPED unexpectedly." -ForegroundColor Red
            Read-LogTail $tunnelOut 40
            Read-LogTail $tunnelErr 40
            break
        }
    }
} catch {
    Write-Host "`n$($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item Env:ALIGN_BETA_MODE -ErrorAction SilentlyContinue
    Remove-Item Env:ALIGN_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:TUNNEL_TOKEN -ErrorAction SilentlyContinue
}

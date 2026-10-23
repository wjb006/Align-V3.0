# Configure-Align-Render.ps1
# Interactively configures Align V3 environment variables on Render.
# Existing Render variables are preserved; blank answers leave a variable unchanged.
# Requires Windows PowerShell 5.1+ and a Render API key.

[CmdletBinding()]
param(
    [string]$ServiceId = "srv-dbdp95a9lscs73a9uh40",
    [string]$ServiceName = "align-v3"
)

$ErrorActionPreference = "Stop"
$ApiBase = "https://api.render.com/v1"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ALIGN V3 - RENDER ENVIRONMENT CONFIGURATION" -ForegroundColor Cyan
Write-Host " Service: $ServiceName ($ServiceId)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Existing variables will be preserved. Press Enter to leave a value unchanged."
Write-Host "Values are sent directly to Render and are not written to a file or log."
Write-Host ""

$secureKey = Read-Host "Render API key (create one at https://dashboard.render.com/u/settings#api-keys)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try { $ApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw "A Render API key is required."
}

$headers = @{ Authorization = "Bearer $ApiKey"; Accept = "application/json" }
$envUrl = "$ApiBase/services/$ServiceId/env-vars"

try {
    $current = Invoke-RestMethod -Method Get -Uri $envUrl -Headers $headers
} catch {
    throw "Could not read the Render environment for $ServiceName. Check the API key and service ID. $($_.Exception.Message)"
}

# Render returns an array of { key, value } objects. Build a case-sensitive-safe map.
$map = @{}
foreach ($item in @($current)) {
    if ($item.key) { $map[[string]$item.key] = [string]$item.value }
}

$definitions = @(
    @{ Key="ALIGN_TRANSPORT_ENABLED"; Label="Enable transport integrations? (true/false)"; Default="true"; Secret=$false },
    @{ Key="ALIGN_JOURNEY_PROVIDER"; Label="Journey provider (confirm existing or enter e.g. here)"; Default=""; Secret=$false },
    @{ Key="ALIGN_HERE_ROUTING_KEY"; Label="HERE Routing API key"; Default=""; Secret=$true },
    @{ Key="ALIGN_HERE_TRANSIT_ENABLED"; Label="Enable HERE transit? (true/false)"; Default="true"; Secret=$false },
    @{ Key="ALIGN_GOOGLE_ROUTES_KEY"; Label="Google Routes API key"; Default=""; Secret=$true },
    @{ Key="ALIGN_OTP_URL"; Label="OpenTripPlanner base URL"; Default=""; Secret=$false },
    @{ Key="ALIGN_NAPTAN_CSV"; Label="NaPTAN CSV file path or URL, as supported by your deployment"; Default=""; Secret=$false },
    @{ Key="ALIGN_BODS_LIVE_URL"; Label="BODS live API URL"; Default=""; Secret=$false },
    @{ Key="ALIGN_BODS_TOKEN"; Label="BODS API token"; Default=""; Secret=$true },
    @{ Key="ALIGN_DARWIN_LIVE_URL"; Label="Darwin live API URL"; Default=""; Secret=$false },
    @{ Key="ALIGN_DARWIN_TOKEN"; Label="Darwin API token"; Default=""; Secret=$true },
    @{ Key="ALIGN_CREDENTIAL_KEY"; Label="Align credential-encryption key (use a long random secret)"; Default=""; Secret=$true },
    @{ Key="DATABASE_URL"; Label="Neon/Postgres connection URL"; Default=""; Secret=$true },
    @{ Key="AWS_ENDPOINT_URL_S3"; Label="S3-compatible endpoint URL"; Default=""; Secret=$false },
    @{ Key="AWS_REGION"; Label="S3 bucket region"; Default=""; Secret=$false },
    @{ Key="AWS_ACCESS_KEY_ID"; Label="S3 access key ID"; Default=""; Secret=$true },
    @{ Key="AWS_SECRET_ACCESS_KEY"; Label="S3 secret access key"; Default=""; Secret=$true },
    @{ Key="ALIGN_ASSET_BUCKET"; Label="S3 bucket name for Align assets"; Default=""; Secret=$false }
)

$changed = @{}
foreach ($definition in $definitions) {
    $key = $definition.Key
    $hasValue = $map.ContainsKey($key) -and -not [string]::IsNullOrWhiteSpace($map[$key])
    $status = if ($hasValue) { "currently set" } else { "NOT SET" }
    Write-Host ""
    Write-Host "$key [$status]" -ForegroundColor Yellow
    Write-Host $definition.Label

    if ($definition.Secret) {
        $answerSecure = Read-Host "Enter new value (blank = keep current/skip)" -AsSecureString
        $answerPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($answerSecure)
        try { $answer = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($answerPtr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($answerPtr) }
    } else {
        $answer = Read-Host "Value (blank = keep current/skip)"
    }

    if (-not [string]::IsNullOrWhiteSpace($answer)) {
        $map[$key] = $answer.Trim()
        $changed[$key] = $true
    }
    if ($answer) { $answer = $null }
}

if ($changed.Count -eq 0) {
    Write-Host ""
    Write-Host "No changes entered. Render was not updated." -ForegroundColor Yellow
    exit 0
}

# Keep the existing variables and only replace values explicitly supplied above.
$payload = @()
foreach ($key in $map.Keys) {
    $payload += @{ key = [string]$key; value = [string]$map[$key] }
}

Write-Host ""
Write-Host "Ready to update $($changed.Count) variable(s) on Render." -ForegroundColor Cyan
Write-Host ("Changed names: " + (($changed.Keys | Sort-Object) -join ", "))
$confirm = Read-Host "Type UPDATE to apply these changes (anything else cancels)"
if ($confirm -cne "UPDATE") {
    Write-Host "Cancelled. Render was not changed." -ForegroundColor Yellow
    exit 0
}

try {
    # Render's service env-vars endpoint accepts the full environment list, so merge
    # current values first to avoid deleting unrelated existing settings.
    $json = ConvertTo-Json -InputObject @($payload) -Depth 5
    $result = Invoke-RestMethod -Method Put -Uri $envUrl -Headers $headers -ContentType "application/json" -Body $json
} catch {
    throw "Render rejected the environment update. No secret values have been printed. $($_.Exception.Message)"
} finally {
    $ApiKey = $null
    $headers = $null
    $secureKey = $null
}

Write-Host ""
Write-Host "Render accepted the environment update." -ForegroundColor Green
Write-Host "If the service is configured for automatic deploys, Render may start a deploy."
Write-Host "Check the deployment at: https://dashboard.render.com/web/$ServiceId"
Write-Host ""
Write-Host "Important: only enter integrations you actually use. Do not invent API keys or URLs."

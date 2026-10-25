# Complete-Align-OTP.ps1
# One-command local OTP verification. Preserves an existing graph.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = $PSScriptRoot
$Data = Join-Path $Root 'otp-data'
$Runtime = Join-Path $Root 'otp-runtime'
$Jar = Join-Path $Runtime 'otp-shaded-2.8.0.jar'
$JavaCandidates = @((Join-Path $Runtime 'jdk-25\bin\java.exe'),(Join-Path $Runtime 'jdk-25.0.4.1+1\bin\java.exe'))
$Java = $JavaCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (!$Java) { $cmd = Get-Command java.exe -ErrorAction SilentlyContinue; if ($cmd) { $Java = $cmd.Source } }
$Graph = Join-Path $Data 'graph.obj'
$Api = 'http://127.0.0.1:8080/otp/gtfs/v1'
$Log = Join-Path $Root 'otp-complete-check.log'
Start-Transcript -Path $Log -Force | Out-Null
try {
    Write-Host '=== Align V3.0 OTP: complete local verification ===' -ForegroundColor Cyan
    if (!(Test-Path $Graph) -or (Get-Item $Graph).Length -lt 1000000) { throw "A valid existing graph.obj was not found at $Graph. This script will not rebuild it." }
    Write-Host ("Existing graph preserved: {0:N1} MB" -f ((Get-Item $Graph).Length / 1MB)) -ForegroundColor Green
    if (!$Java) { throw "Java was not found. Expected $($JavaCandidates[0]) or java.exe on PATH." }
    if (!(Test-Path $Jar) -or (Get-Item $Jar).Length -lt 10000000) { throw "OTP 2.8.0 JAR is missing or invalid: $Jar" }
    Write-Host "Java: $Java"
    Write-Host "OTP:  $Jar"
    function Invoke-OtpGraphQL([string]$Query) {
        $body = @{ query = $Query; variables = @{} } | ConvertTo-Json -Depth 10
        Invoke-RestMethod -Uri $Api -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 30
    }
    $ready = $false
    try { $null = Invoke-OtpGraphQL 'query { stops(name: "Birkenhead") { gtfsId name } }'; $ready = $true; Write-Host 'OTP GraphQL already responds.' -ForegroundColor Green }
    catch { Write-Host 'OTP is not responding yet; starting it in a separate window...' }
    if (!$ready) {
        $argLine = '-Xmx4G -jar "' + $Jar + '" --load --serve --bindAddress 127.0.0.1 "' + $Data + '"'
        $proc = Start-Process -FilePath $Java -ArgumentList $argLine -WorkingDirectory $Root -PassThru -WindowStyle Minimized
        $deadline = (Get-Date).AddMinutes(3)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 3
            if ($proc.HasExited) { throw "OTP exited during startup (exit code $($proc.ExitCode)). Check the OTP window and $Log." }
            try { $null = Invoke-OtpGraphQL 'query { stops(name: "Birkenhead") { gtfsId name } }'; $ready = $true; break } catch {}
        }
        if (!$ready) { throw 'OTP did not become ready within 3 minutes. Inspect the OTP window output.' }
        Write-Host 'OTP started and GraphQL is responding.' -ForegroundColor Green
    }
    $stops = Invoke-OtpGraphQL 'query { stops(name: "Birkenhead") { gtfsId name lat lon } }'
    if ($stops.errors) { throw ("Stops query failed: " + ($stops.errors | ConvertTo-Json -Depth 8 -Compress)) }
    $stopList = @($stops.data.stops)
    if ($stopList.Count -lt 1) { throw 'GraphQL responded, but no Birkenhead stops were returned.' }
    $stopsPath = Join-Path $Root 'otp-birkenhead-stops.json'
    $stops | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $stopsPath
    Write-Host "Birkenhead stop search: PASS ($($stopList.Count) results)" -ForegroundColor Green
    $stopList | Select-Object -First 12 name,gtfsId,lat,lon | Format-Table -AutoSize
    $journeyQuery = @'
query {
  plan(
    from: { lat: 53.3946919, lon: -3.0136796 }
    to: { lat: 53.4075, lon: -2.9916 }
    date: "2026-10-26"
    time: "08:30"
    transportModes: [{ mode: WALK }, { mode: TRANSIT }]
  ) {
    itineraries {
      duration
      legs { mode startTime endTime from { name } to { name } }
    }
  }
}
'@
    $journeyPath = Join-Path $Root 'otp-journey-test.json'
    try {
        $journey = Invoke-OtpGraphQL $journeyQuery
        $journey | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 $journeyPath
        if ($journey.errors) {
            Write-Host 'Journey query was rejected by this GraphQL schema; details saved to otp-journey-test.json.' -ForegroundColor Yellow
            $journey.errors | ForEach-Object { Write-Host $_.message -ForegroundColor Yellow }
        } elseif (@($journey.data.plan.itineraries).Count -gt 0) {
            Write-Host "Journey planning: PASS ($(@($journey.data.plan.itineraries).Count) itineraries)" -ForegroundColor Green
        } else { Write-Host 'Journey query ran but returned no itineraries. Full result saved.' -ForegroundColor Yellow }
    } catch {
        @{ error = $_.Exception.Message; query = $journeyQuery } | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $journeyPath
        Write-Host "Journey test needs schema/date adjustment: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Details saved to $journeyPath"
    }
    Write-Host ''
    Write-Host 'LOCAL OTP CHECK COMPLETE' -ForegroundColor Green
    Write-Host "API: $Api"
    Write-Host "Stops result: $stopsPath"
    Write-Host "Journey result: $journeyPath"
    Write-Host "Run log: $Log"
    Write-Host 'Graph was not rebuilt. Production transport settings were not changed.'
    Write-Host 'Keep the OTP server window open while testing locally.'
} catch {
    Write-Host ("FAILED: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Log: $Log"
    exit 1
} finally { Stop-Transcript | Out-Null }

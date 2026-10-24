# Rebuild-Align-OTP.ps1
# Recreates the Align V3.0 local Merseyside OTP graph in this project folder.
# Run from PowerShell: & "C:\Align V3.0\Rebuild-Align-OTP.ps1"
# Source code stays in Git; large feed files and graph are ignored by .gitignore.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ProjectRoot = $PSScriptRoot
$Data = Join-Path $ProjectRoot 'otp-data'
$Runtime = Join-Path $ProjectRoot 'otp-runtime'
$Log = Join-Path $ProjectRoot 'otp-rebuild.log'
$OtpVersion = '2.8.0'
$OtpJar = Join-Path $Runtime "otp-shaded-$OtpVersion-shaded.jar"
$JavaExe = Join-Path $Runtime 'jdk-25\bin\java.exe'

New-Item -ItemType Directory -Force -Path $Data,$Runtime | Out-Null
Start-Transcript -Path $Log -Force | Out-Null

function Get-File([string]$Url,[string]$Path,[long]$MinimumBytes = 1000) {
    if (Test-Path $Path) {
        if ((Get-Item $Path).Length -ge $MinimumBytes) { return }
        Remove-Item $Path -Force
    }
    Write-Host "Downloading $([IO.Path]::GetFileName($Path))..."
    Invoke-WebRequest -Uri $Url -OutFile $Path -TimeoutSec 900
    if (!(Test-Path $Path) -or (Get-Item $Path).Length -lt $MinimumBytes) {
        throw "Download failed or returned an unexpectedly small file: $Path"
    }
}

try {
    $osm = Join-Path $Data 'merseyside-latest.osm.pbf'
    $bus = Join-Path $Data 'uk-busmetro-NW.gtfs.zip'
    $rail = Join-Path $Data 'gb-nationalrail.gtfs.zip'
    $railOriginal = Join-Path $Data 'gb-nationalrail.gtfs.zip.orig'

    Get-File 'https://download.geofabrik.de/europe/united-kingdom/england/merseyside-latest.osm.pbf' $osm 1000000
    Get-File 'https://storage.travelwhiz.app/generated-gtfs/uk-busmetro-NW.gtfs.zip' $bus 10000
    if (!(Test-Path $railOriginal) -and (Test-Path $rail)) { Copy-Item $rail $railOriginal }
    Get-File 'https://storage.travelwhiz.app/generated-gtfs/gb-nationalrail.gtfs.zip' $rail 10000
    if (!(Test-Path $railOriginal)) { Copy-Item $rail $railOriginal }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($feed in @($bus,$rail)) {
        $zip = [IO.Compression.ZipFile]::OpenRead($feed)
        try {
            $names = @($zip.Entries | ForEach-Object { $_.FullName })
            foreach ($required in @('stops.txt','routes.txt','trips.txt')) {
                if ($names -notcontains $required) { throw "GTFS feed $feed is missing $required" }
            }
        } finally { $zip.Dispose() }
    }

    if (!(Test-Path $OtpJar)) {
        Get-File "https://repo.maven.apache.org/maven2/org/opentripplanner/otp-shaded/$OtpVersion/otp-shaded-$OtpVersion-shaded.jar" $OtpJar 10000000
    }

    if (!(Test-Path $JavaExe)) {
        $javaZip = Join-Path $Runtime 'jdk25.zip'
        Get-File 'https://api.adoptium.net/v3/binary/latest/25/ga/windows/x64/jdk/hotspot/normal/eclipse' $javaZip 10000000
        $extract = Join-Path $Runtime 'jdk-extract'
        if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
        Expand-Archive $javaZip -DestinationPath $extract -Force
        $jdk = Get-ChildItem $extract -Directory | Select-Object -First 1
        if (!$jdk -or !(Test-Path (Join-Path $jdk.FullName 'bin\java.exe'))) {
            throw 'Java runtime extraction did not contain bin\java.exe.'
        }
        $javaHome = Join-Path $Runtime 'jdk-25'
        if (Test-Path $javaHome) { Remove-Item $javaHome -Recurse -Force }
        Move-Item $jdk.FullName $javaHome
        Remove-Item $extract -Recurse -Force
        Remove-Item $javaZip -Force
    }

    # Use the repository's established rail-feed sanitiser when supplied.
    $sanitiser = Join-Path $Runtime 'sanitize_nationalrail.py'
    if (Test-Path $sanitiser) {
        Write-Host 'Running the existing National Rail feed sanitiser...'
        python $sanitiser
        if ($LASTEXITCODE -ne 0) { throw 'National Rail feed sanitiser failed.' }
    } else {
        Write-Warning 'Existing National Rail sanitiser is not present; feed preserved as downloaded.'
    }

    Write-Host 'Building OTP graph (this may take several minutes)...'
    & $JavaExe '-Xmx4G' '-jar' $OtpJar '--build' '--save' $Data
    if ($LASTEXITCODE -ne 0) { throw "OTP graph build failed (exit $LASTEXITCODE)." }

    $graph = Join-Path $Data 'graph.obj'
    if (!(Test-Path $graph) -or (Get-Item $graph).Length -lt 1000000) {
        throw 'OTP graph.obj was not created or is unexpectedly small.'
    }

    Write-Host ''
    Write-Host 'OTP GRAPH BUILD SUCCESSFUL' -ForegroundColor Green
    Get-Item $graph | Select-Object FullName,Length,LastWriteTime
    Write-Host "Build log: $Log"
    Write-Host 'Production transport remains disabled; this script does not alter Render.'
} catch {
    Write-Host "OTP rebuild failed: $($_.Exception.Message)" -ForegroundColor Red
    throw
} finally {
    Stop-Transcript | Out-Null
}

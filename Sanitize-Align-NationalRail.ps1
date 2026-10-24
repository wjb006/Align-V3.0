param(
    [Parameter(Mandatory = $true)]
    [string]$FeedPath
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $FeedPath)) { throw "GTFS feed not found: $FeedPath" }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Read-ZipTextEntry([System.IO.Compression.ZipArchive]$Archive, [string]$Name) {
    $e = $Archive.GetEntry($Name)
    if ($null -eq $e) { return $null }
    $reader = [System.IO.StreamReader]::new($e.Open(), [System.Text.Encoding]::UTF8, $true)
    try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}
function Write-ZipTextEntry([System.IO.Compression.ZipArchive]$Archive, [string]$Name, [string]$Text) {
    $old = $Archive.GetEntry($Name)
    if ($null -ne $old) { $old.Delete() }
    $e = $Archive.CreateEntry($Name, [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $e.Open()
    try {
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        try { $writer.Write($Text) } finally { $writer.Dispose() }
    } finally { $stream.Dispose() }
}

$zip = [System.IO.Compression.ZipFile]::Open($FeedPath, [System.IO.Compression.ZipArchiveMode]::Update)
try {
    # OTP 2.8 requires every stop_id referenced by stop_times.txt to have
    # location_type 0. Some National Rail feed snapshots incorrectly reference
    # parent-station rows (location_type 1) directly from stop_times.
    $stopsText = Read-ZipTextEntry $zip 'stops.txt'
    $timesText = Read-ZipTextEntry $zip 'stop_times.txt'
    if ($null -eq $stopsText -or $null -eq $timesText) {
        throw 'National Rail GTFS must contain stops.txt and stop_times.txt.'
    }

    $stopLines = @($stopsText -split "\r?\n" | Where-Object { $_ -ne '' })
    $timeLines = @($timesText -split "\r?\n" | Where-Object { $_ -ne '' })
    if ($stopLines.Count -lt 2 -or $timeLines.Count -lt 2) { throw 'National Rail stops.txt or stop_times.txt has no data rows.' }

    $stopRows = @($stopLines | ConvertFrom-Csv)
    $timeRows = @($timeLines | ConvertFrom-Csv)
    $stopHeaders = @($stopRows[0].PSObject.Properties.Name)
    $timeHeaders = @($timeRows[0].PSObject.Properties.Name)
    if ($stopHeaders -notcontains 'stop_id' -or $stopHeaders -notcontains 'location_type') {
        throw 'National Rail stops.txt must contain stop_id and location_type columns.'
    }
    if ($timeHeaders -notcontains 'stop_id') { throw 'National Rail stop_times.txt must contain stop_id.' }

    $referenced = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($row in $timeRows) { [void]$referenced.Add([string]$row.stop_id) }

    $invalidParents = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($row in $stopRows) {
        if ([string]$row.location_type -eq '1' -and $referenced.Contains([string]$row.stop_id)) {
            [void]$invalidParents.Add([string]$row.stop_id)
        }
    }

    if ($invalidParents.Count -gt 0) {
        # Convert only directly referenced parent rows to ordinary stops, and
        # clear child parent_station references to those converted rows so the
        # resulting hierarchy remains internally consistent.
        foreach ($row in $stopRows) {
            if ($invalidParents.Contains([string]$row.stop_id)) {
                $row.location_type = '0'
            }
            if ($stopHeaders -contains 'parent_station' -and $invalidParents.Contains([string]$row.parent_station)) {
                $row.parent_station = ''
            }
        }
        $newStops = @($stopRows | ConvertTo-Csv -NoTypeInformation) -join "`n"
        Write-ZipTextEntry $zip 'stops.txt' ($newStops + "`n")
        Write-Host "Corrected $($invalidParents.Count) National Rail parent-station row(s) referenced directly by stop_times.txt."
    } else {
        Write-Host 'National Rail stop_times.txt references only location_type 0 stops.'
    }

    # Deduplicate calendar service rows by service_id, retaining the first row.
    $calendarText = Read-ZipTextEntry $zip 'calendar.txt'
    if ($null -ne $calendarText) {
        $lines = @($calendarText -split "\r?\n" | Where-Object { $_ -ne '' })
        if ($lines.Count -ge 2) {
            $columns = $lines[0].Split(',')
            $serviceIndex = [Array]::IndexOf($columns, 'service_id')
            if ($serviceIndex -lt 0) { throw 'calendar.txt has no service_id column; refusing to modify the feed.' }
            $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
            $output = [System.Collections.Generic.List[string]]::new()
            $output.Add($lines[0])
            $removed = 0
            for ($i = 1; $i -lt $lines.Count; $i++) {
                $fields = $lines[$i].Split(',')
                if ($fields.Count -le $serviceIndex) { throw "Malformed calendar.txt row $($i + 1)." }
                if ($seen.Add($fields[$serviceIndex])) { $output.Add($lines[$i]) } else { $removed++ }
            }
            if ($removed -gt 0) {
                Write-ZipTextEntry $zip 'calendar.txt' (($output -join "`n") + "`n")
                Write-Host "Removed $removed duplicate National Rail calendar service row(s)."
            } else {
                Write-Host 'National Rail calendar.txt contains no duplicate service_id rows.'
            }
        } else {
            Write-Host 'No National Rail calendar service rows to deduplicate.'
        }
    } else {
        Write-Host 'No calendar.txt in National Rail feed; no calendar deduplication needed.'
    }
} finally {
    $zip.Dispose()
}

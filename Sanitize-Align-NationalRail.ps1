param(
    [Parameter(Mandatory = $true)]
    [string]$FeedPath,
    [string]$FeedLabel = 'GTFS'
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $FeedPath)) { throw "GTFS feed not found: $FeedPath" }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName Microsoft.VisualBasic

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
    # OTP 2.8 requires each stop_times stop_id to identify a physical stop
    # (location_type 0). Some feeds reference parent-station rows directly.
    $stopsText = Read-ZipTextEntry $zip 'stops.txt'
    $timesEntry = $zip.GetEntry('stop_times.txt')
    if ($null -eq $stopsText -or $null -eq $timesEntry) {
        throw "$FeedLabel GTFS must contain stops.txt and stop_times.txt."
    }

    $stopRows = @($stopsText | ConvertFrom-Csv)
    if ($stopRows.Count -eq 0) { throw "$FeedLabel stops.txt has no data rows." }
    $stopHeaders = @($stopRows[0].PSObject.Properties.Name)
    if ($stopHeaders -notcontains 'stop_id' -or $stopHeaders -notcontains 'location_type') {
        throw "$FeedLabel stops.txt must contain stop_id and location_type columns."
    }

    # Stream stop_times.csv rather than loading potentially millions of rows into RAM.
    $referenced = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $entryStream = $timesEntry.Open()
    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new($entryStream, [System.Text.Encoding]::UTF8, $true)
    try {
        $parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
        $parser.SetDelimiters(',')
        $parser.HasFieldsEnclosedInQuotes = $true
        $timeHeaders = $parser.ReadFields()
        $stopIndex = [Array]::IndexOf($timeHeaders, 'stop_id')
        if ($stopIndex -lt 0) { throw "$FeedLabel stop_times.txt must contain stop_id." }
        while (-not $parser.EndOfData) {
            $fields = $parser.ReadFields()
            if ($fields.Length -gt $stopIndex -and -not [string]::IsNullOrEmpty($fields[$stopIndex])) {
                [void]$referenced.Add([string]$fields[$stopIndex])
            }
        }
    } finally {
        $parser.Dispose()
        $entryStream.Dispose()
    }

    $invalidParents = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($row in $stopRows) {
        if ([string]$row.location_type -eq '1' -and $referenced.Contains([string]$row.stop_id)) {
            [void]$invalidParents.Add([string]$row.stop_id)
        }
    }

    if ($invalidParents.Count -gt 0) {
        foreach ($row in $stopRows) {
            if ($invalidParents.Contains([string]$row.stop_id)) { $row.location_type = '0' }
            if ($stopHeaders -contains 'parent_station' -and $invalidParents.Contains([string]$row.parent_station)) {
                $row.parent_station = ''
            }
        }
        $newStops = @($stopRows | ConvertTo-Csv -NoTypeInformation) -join "`n"
        Write-ZipTextEntry $zip 'stops.txt' ($newStops + "`n")
        Write-Host "Corrected $($invalidParents.Count) $FeedLabel parent-station row(s) referenced directly by stop_times.txt."
    } else {
        Write-Host "$FeedLabel stop_times.txt references only location_type 0 stops."
    }

    # National Rail snapshots may contain duplicate calendar service rows.
    if ($FeedLabel -eq 'National Rail') {
        $calendarText = Read-ZipTextEntry $zip 'calendar.txt'
        if ($null -ne $calendarText) {
            $lines = @($calendarText -split "\r?\n" | Where-Object { $_ -ne '' })
            if ($lines.Count -ge 2) {
                $columns = $lines[0].Split(',')
                $serviceIndex = [Array]::IndexOf($columns, 'service_id')
                if ($serviceIndex -lt 0) { throw 'National Rail calendar.txt has no service_id column; refusing to modify the feed.' }
                $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
                $output = [System.Collections.Generic.List[string]]::new()
                $output.Add($lines[0])
                $removed = 0
                for ($i = 1; $i -lt $lines.Count; $i++) {
                    $fields = $lines[$i].Split(',')
                    if ($fields.Count -le $serviceIndex) { throw "Malformed National Rail calendar.txt row $($i + 1)." }
                    if ($seen.Add($fields[$serviceIndex])) { $output.Add($lines[$i]) } else { $removed++ }
                }
                if ($removed -gt 0) {
                    Write-ZipTextEntry $zip 'calendar.txt' (($output -join "`n") + "`n")
                    Write-Host "Removed $removed duplicate National Rail calendar service row(s)."
                } else { Write-Host 'National Rail calendar.txt contains no duplicate service_id rows.' }
            }
        }
    }
} finally {
    $zip.Dispose()
}

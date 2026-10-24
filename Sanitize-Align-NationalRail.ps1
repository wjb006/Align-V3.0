param(
    [Parameter(Mandatory = $true)]
    [string]$FeedPath
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $FeedPath)) { throw "GTFS feed not found: $FeedPath" }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = [System.IO.Compression.ZipFile]::Open($FeedPath, [System.IO.Compression.ZipArchiveMode]::Update)
try {
    $entry = $zip.GetEntry('calendar.txt')
    if ($null -eq $entry) {
        Write-Host 'No calendar.txt in National Rail feed; no calendar deduplication needed.'
        return
    }
    $reader = [System.IO.StreamReader]::new($entry.Open(), [System.Text.Encoding]::UTF8, $true)
    try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
    $lines = $text -split "\r?\n" | Where-Object { $_ -ne '' }
    if ($lines.Count -lt 2) { throw 'calendar.txt has no service rows; refusing to modify the feed.' }
    $header = $lines[0]
    $columns = $header.Split(',')
    $serviceIndex = [Array]::IndexOf($columns, 'service_id')
    if ($serviceIndex -lt 0) { throw 'calendar.txt has no service_id column; refusing to modify the feed.' }
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $output = [System.Collections.Generic.List[string]]::new()
    $output.Add($header)
    $removed = 0
    for ($i = 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        $fields = $line.Split(',')
        if ($fields.Count -le $serviceIndex) { throw "Malformed calendar.txt row $($i + 1)." }
        $serviceId = $fields[$serviceIndex]
        if ($seen.Add($serviceId)) { $output.Add($line) } else { $removed++ }
    }
    if ($removed -gt 0) {
        $entry.Delete()
        $replacement = $zip.CreateEntry('calendar.txt', [System.IO.Compression.CompressionLevel]::Optimal)
        $stream = $replacement.Open()
        try {
            $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
            try { $writer.Write(($output -join [char]10) + [char]10) } finally { $writer.Dispose() }
        } finally { $stream.Dispose() }
        Write-Host "Removed $removed duplicate National Rail calendar service row(s)."
    } else {
        Write-Host 'National Rail calendar.txt contains no duplicate service_id rows.'
    }
} finally {
    $zip.Dispose()
}

# Preview: .\Clean-Align.ps1
# Archive old items: .\Clean-Align.ps1 -Apply
# Also permanently delete old disposable files: .\Clean-Align.ps1 -Apply -DeleteTemporary
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$AlignRoot = 'C:\Align',
    [switch]$Apply,
    [switch]$DeleteTemporary,
    # EASY TO EDIT: age in days, and minimum recent snapshots to retain.
    [ValidateRange(1,3650)][int]$TemporaryDays = 7,
    [ValidateRange(1,3650)][int]$BackupDays = 90,
    [ValidateRange(1,3650)][int]$ReleaseDays = 90,
    [ValidateRange(1,1000)][int]$KeepNewest = 3,
    [string]$ReportFolder = ''
)
$ErrorActionPreference = 'Stop'
$AlignRoot = [IO.Path]::GetFullPath($AlignRoot).TrimEnd('\')
if(-not (Test-Path -LiteralPath $AlignRoot -PathType Container)){throw 'Align folder not found.'}
if($AlignRoot -eq [IO.Path]::GetPathRoot($AlignRoot).TrimEnd('\')){throw 'A drive root cannot be cleaned.'}
if((Get-Item -LiteralPath $AlignRoot).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Use a real folder, not a linked folder.'}
if($DeleteTemporary -and -not $Apply){throw 'Deletion requires both -Apply and -DeleteTemporary. Run without switches to preview.'}

function Assert-InRoot([string]$Path){
    $full=[IO.Path]::GetFullPath($Path)
    if(-not $full.StartsWith($AlignRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw "Path outside Align: $full"}
    $cursor=$full
    while($cursor -ne $AlignRoot){
        if((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw "Linked path skipped: $cursor"}
        $cursor=[IO.Path]::GetDirectoryName($cursor)
    }
    return $full
}
function Get-SafeFiles([string]$Path){
    foreach($item in Get-ChildItem -LiteralPath $Path -Force){
        if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){continue}
        if($item.PSIsContainer){Get-SafeFiles $item.FullName}else{$item}
    }
}
$now=Get-Date
$plan=[Collections.Generic.List[object]]::new()
# Only these locations are eligible for disposable-file cleanup.
# Active remote-access tunnel logs, .venv, OTP runtime/data, .git, .vs and _REVIEW are excluded.
foreach($relative in @('Align_App\__pycache__','Align_App\temp','Align_App\tmp','Align_App\logs')){
    $folder=Join-Path $AlignRoot $relative
    if(-not (Test-Path -LiteralPath $folder)){continue}
    [void](Assert-InRoot $folder)
    foreach($file in Get-SafeFiles $folder){
        if($file.Extension -notin @('.pyc','.tmp','.temp','.log')){continue}
        if($file.LastWriteTime -ge $now.AddDays(-$TemporaryDays)){continue}
        $plan.Add([pscustomobject]@{Source=$file.FullName;Kind='Temporary';Reason="Disposable file older than $TemporaryDays days";Stamp=$file.LastWriteTimeUtc.Ticks;Size=$file.Length})
    }
}
# Backups are archived, NEVER deleted. Retain at least KeepNewest per category.
foreach($relative in @('01_Backups\Daily','01_Backups\Weekly','01_Backups\Pre-Merge','03_Database_Backups','02_Releases')){
    $folder=Join-Path $AlignRoot $relative
    if(-not (Test-Path -LiteralPath $folder)){continue}
    [void](Assert-InRoot $folder)
    $days=if($relative -eq '02_Releases'){$ReleaseDays}else{$BackupDays}
    $entries=@(foreach($item in Get-ChildItem -LiteralPath $folder -Force){
        if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){continue}
        if($relative -eq '02_Releases' -and ($item.PSIsContainer -or $item.Extension -ne '.zip')){continue}
        if(-not $item.PSIsContainer -and $item.Extension -notin @('.zip','.db','.sqlite','.sqlite3','.bak')){continue}
        $latest=$item.LastWriteTime
        if($item.PSIsContainer){
            # Never move a snapshot containing links; do not follow cloud/junction targets.
            if(@(Get-ChildItem -LiteralPath $item.FullName -Recurse -Force -Attributes ReparsePoint).Count){continue}
            foreach($file in Get-SafeFiles $item.FullName){if($file.LastWriteTime -gt $latest){$latest=$file.LastWriteTime}}
        }
        [pscustomobject]@{Item=$item;Latest=$latest}
    })
    foreach($entry in @($entries | Sort-Object Latest -Descending | Select-Object -Skip $KeepNewest)){
        if($entry.Latest -ge $now.AddDays(-$days)){continue}
        $plan.Add([pscustomobject]@{Source=$entry.Item.FullName;Kind='Snapshot';Reason="Older than $days days; newest $KeepNewest retained";Stamp=$entry.Item.LastWriteTimeUtc.Ticks;Size=$null})
    }
}
if($Apply -and $plan.Count -and -not $WhatIfPreference){
    $running=Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^(python|pythonw|java|cloudflared)\.exe$' -and
        ($_.ExecutablePath -like "$AlignRoot\*" -or ($_.CommandLine -and $_.CommandLine.Contains($AlignRoot)))
    }
    if($running){throw 'Close Align, OpenTripPlanner and the remote-access tunnel before applying cleanup. Preview is safe while they run.'}
}
$run=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
if(-not $ReportFolder){$ReportFolder=Join-Path $AlignRoot '05_Documentation\Cleanup reports'}
$ReportFolder=Assert-InRoot $ReportFolder
[IO.Directory]::CreateDirectory($ReportFolder) | Out-Null
$report=Join-Path $ReportFolder ("Cleanup-$run.csv")
$results=[Collections.Generic.List[object]]::new()
foreach($item in $plan){
    $source=Assert-InRoot $item.Source
    $delete=$DeleteTemporary -and $item.Kind -eq 'Temporary'
    $destination=if($delete){''}else{Assert-InRoot (Join-Path $AlignRoot ('99_Archive\Cleanup-'+$run+'\'+$source.Substring($AlignRoot.Length+1)))}
    $action=if($delete){'Delete temporary file'}else{'Archive'}
    $row=[pscustomobject]@{Source=$source;Destination=$destination;Action=$action;Reason=$item.Reason;Status='Preview only'}
    $results.Add($row)
    $results | Export-Csv -LiteralPath $report -NoTypeInformation -WhatIf:$false
    if(-not $Apply -or -not $PSCmdlet.ShouldProcess($source,$action)){continue}
    try{
        $current=Get-Item -LiteralPath $source -Force
        if($current.LastWriteTimeUtc.Ticks -ne $item.Stamp -or ($item.Kind -eq 'Temporary' -and $current.Length -ne $item.Size)){throw 'Item changed since preview; rerun cleanup.'}
        if($delete){
            # Individual disposable files only. No recursive deletion anywhere.
            if($current.PSIsContainer){throw 'Directory deletion is not supported.'}
            Remove-Item -LiteralPath $source -ErrorAction Stop
            $row.Status='Deleted'
        }else{
            if(Test-Path -LiteralPath $destination){throw 'Destination conflict; nothing overwritten.'}
            $files=if($current.PSIsContainer){@(Get-SafeFiles $source)}else{@($current)}
            $hashes=@($files | ForEach-Object {[pscustomobject]@{Relative=if($current.PSIsContainer){$_.FullName.Substring($source.Length+1)}else{''};Hash=(Get-FileHash -LiteralPath $_.FullName).Hash}})
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
            Move-Item -LiteralPath $source -Destination $destination -ErrorAction Stop
            foreach($h in $hashes){$target=if($h.Relative){Join-Path $destination $h.Relative}else{$destination};if((Get-FileHash -LiteralPath $target).Hash -ne $h.Hash){throw 'Archive verification failed; inspect report.'}}
            $row.Status='Archived and verified'
        }
    }catch{$row.Status='ERROR: '+$_.Exception.Message;throw}
    finally{$results | Export-Csv -LiteralPath $report -NoTypeInformation -WhatIf:$false}
}
if(-not $plan.Count){'Source,Destination,Action,Reason,Status' | Set-Content -LiteralPath $report -WhatIf:$false}
$results | Format-Table Action,Source,Status -AutoSize
Write-Host "$($plan.Count) candidates. Report: $report"
if(-not $Apply){Write-Host 'Preview only. Use -Apply to archive candidates. Add -DeleteTemporary only to permanently delete disposable files.'}



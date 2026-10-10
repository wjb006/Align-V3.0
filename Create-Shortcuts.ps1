<#
.SYNOPSIS  Creates Desktop shortcuts to start, stop and check the local Align server (align.ps1).
#>
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
foreach ($item in @(@('Start','Start Align'),@('Stop','Stop Align'),@('Status','Align status'))) {
    $link = $shell.CreateShortcut((Join-Path $desktop ($item[1] + '.lnk')))
    $link.TargetPath = (Get-Command powershell.exe).Source
    $link.Arguments = '-NoProfile -ExecutionPolicy Bypass -NoExit -File "' + (Join-Path $PSScriptRoot 'align.ps1') + '" ' + $item[0].ToLower()
    $link.WorkingDirectory = $PSScriptRoot
    $link.Save()
    Write-Host "Created $($item[1]) shortcut"
}

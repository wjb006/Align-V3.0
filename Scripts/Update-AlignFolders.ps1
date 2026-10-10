[CmdletBinding(SupportsShouldProcess)]
param([string]$AlignRoot='C:\Align')
$ErrorActionPreference='Stop'
# EDIT THIS LIST to maintain the numbered local structure.
# This script only creates missing folders; it does not sort, move or delete files.
$folders=@(
 '01_Backups\Daily','01_Backups\Weekly','01_Backups\Pre-Merge',
 '02_Releases','03_Database_Backups','04_Assets','05_Documentation',
 '99_Archive','Align_App\Scripts'
)
foreach($relative in $folders){
 $path=Join-Path $AlignRoot $relative
 if(Test-Path -LiteralPath $path){
  if(-not (Test-Path -LiteralPath $path -PathType Container)){throw "A file blocks this folder: $path"}
  [pscustomobject]@{Status='Already exists';Path=$path}
 }elseif($PSCmdlet.ShouldProcess($path,'Create missing folder')){
  [IO.Directory]::CreateDirectory($path) | Out-Null
  [pscustomobject]@{Status='Created';Path=$path}
 }
}

#requires -Version 5.1
<# Build 156 Windows installer. $ExpectedBuild must match BUILD_VERSION in app.py. Does not delete the existing Align database. #>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
$ExpectedBuild = 156
$LogDir = Join-Path $Root 'install-logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("install-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

function Write-Log { param([string]$Message,[string]$Level='INFO'); $line = "[{0}] [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$Level,$Message; Write-Host $line; Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 }
function Stop-Install { param([string]$Message); Write-Log $Message 'ERROR'; Write-Host ''; Write-Host 'ALIGN INSTALLATION FAILED' -ForegroundColor Red; Write-Host $Message -ForegroundColor Red; Write-Host "Log: $LogFile" -ForegroundColor Yellow; exit 1 }
function Run-Step { param([string]$File,[string[]]$StepArgs,[string]$Name); Write-Log $Name; & $File @StepArgs 2>&1 | ForEach-Object { Write-Host $_; Add-Content -LiteralPath $LogFile -Value ([string]$_) -Encoding UTF8 }; if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE." } }

function Find-Python {
  foreach ($candidate in @(@{File='py.exe';Args=@('-3')},@{File='python.exe';Args=@()})) {
    if (-not (Get-Command $candidate.File -ErrorAction SilentlyContinue)) { continue }
    try {
      $raw = & $candidate.File @($candidate.Args) -c "import sys; print(f'{sys.version_info[0]}|{sys.version_info[1]}|{sys.executable}')" 2>$null
      if ($LASTEXITCODE -eq 0 -and $raw) {
        $p = ([string]$raw).Trim().Split('|')
        if ($p.Count -ge 3 -and [int]$p[0] -eq 3 -and [int]$p[1] -ge 10) { return @{File=$candidate.File;Args=$candidate.Args;Version=('{0}.{1}' -f $p[0],$p[1]);Path=$p[2]} }
      }
    } catch {}
  }
  return $null
}

try {
  Write-Log "Starting Align V3.0 Build $ExpectedBuild installation."
  Write-Log "Root: $Root"
  if ($env:OS -ne 'Windows_NT') { throw 'This installer is intended for Windows.' }

  $required = @('app.py','launch.py','schema_v3.sqlite.sql','requirements.txt','build152.py','static\app.js','static\service-worker.js','static\build152.js')
  foreach ($f in $required) { if (-not (Test-Path -LiteralPath (Join-Path $Root $f) -PathType Leaf)) { throw "Required file is missing: $f" } }
  foreach ($d in @('migrations','static')) { if (-not (Test-Path -LiteralPath (Join-Path $Root $d) -PathType Container)) { throw "Required folder is missing: $d" } }

  $appText = Get-Content -Raw -LiteralPath (Join-Path $Root 'app.py')
  $clientText = Get-Content -Raw -LiteralPath (Join-Path $Root 'static\app.js')
  $workerText = Get-Content -Raw -LiteralPath (Join-Path $Root 'static\service-worker.js')
  $serverMatch = [regex]::Match($appText,'(?m)^BUILD_VERSION\s*=\s*(\d+)')
  $clientMatch = [regex]::Match($clientText,'(?m)const\s+BUILD_VERSION\s*=\s*(\d+)')
  $workerMatch = [regex]::Match($workerText,'(?m)const\s+BUILD\s*=\s*(\d+)')
  if (-not $serverMatch.Success -or -not $clientMatch.Success -or -not $workerMatch.Success) { throw 'Could not find all Build version markers.' }
  Write-Log "Server=$($serverMatch.Groups[1].Value), Client=$($clientMatch.Groups[1].Value), Worker=$($workerMatch.Groups[1].Value)"
  if ([int]$serverMatch.Groups[1].Value -ne $ExpectedBuild -or [int]$clientMatch.Groups[1].Value -ne $ExpectedBuild -or [int]$workerMatch.Groups[1].Value -ne $ExpectedBuild) { throw "Build mismatch. This installer requires Build $ExpectedBuild." }

  $python = Find-Python
  if ($null -eq $python) { throw 'Python 3.10 or newer was not found. Install Python 3.12 and run the installer again.' }
  Write-Log "Python $($python.Version): $($python.Path)"

  $venv = Join-Path $Root '.venv'
  $venvPython = Join-Path $venv 'Scripts\python.exe'
  if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { Run-Step $python.File ($python.Args + @('-m','venv',$venv)) 'Create Python virtual environment' } else { Write-Log "Using existing virtual environment: $venv" }
  if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw 'Virtual environment was not created correctly.' }

  Run-Step $venvPython @('-m','pip','install','--upgrade','pip') 'Upgrade pip'
  Run-Step $venvPython @('-m','pip','install','-r',(Join-Path $Root 'requirements.txt')) 'Install Align dependencies'

  $compile = @"
import pathlib, py_compile
root=pathlib.Path.cwd()
files=[p for p in root.rglob('*.py') if '.venv' not in p.parts and 'install-logs' not in p.parts]
for p in files: py_compile.compile(str(p), doraise=True)
print(f'Compiled {len(files)} Python files successfully.')
"@
  Run-Step $venvPython @('-c',$compile) 'Compile Python sources'

  $db = @"
import app, build152, json
app.initialise_database()
with app.db_connection() as connection:
    build152.ensure(connection)
    connection.execute(build152.CONTACT_SCHEMA)
    connection.commit()
status=app.health_status()
print(json.dumps(status,indent=2,sort_keys=True))
"@
  Run-Step $venvPython @('-c',$db) 'Initialise and migrate local SQLite database'
  $database = Join-Path $Root 'align.sqlite3'
  if (-not (Test-Path -LiteralPath $database -PathType Leaf)) { throw 'align.sqlite3 was not created.' }

  $verify = @"
import sqlite3
con=sqlite3.connect('align.sqlite3')
try:
    if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('SQLite integrity check failed')
    required={'settings','schema_migrations','personal_items','calendar_sources','calendar_events','organiser_sections','organiser_events','calendar_links','assets','asset_categories','asset_variants','asset_usage_rules','asset_audit_log','transport_preferences','transport_journey_cache','icloud_config','calendar_sync_state','user_favourites','align_contacts'}
    tables={r[0] for r in con.execute('SELECT name FROM sqlite_master WHERE type=?',('table',))}
    missing=sorted(required-tables)
    if missing: raise RuntimeError('Missing required tables: '+', '.join(missing))
    print('SQLite integrity: OK')
    print('Required tables: OK')
finally: con.close()
"@
  Run-Step $venvPython @('-c',$verify) 'Verify SQLite database'

  $appVerify = @"
import app
if app.BUILD_VERSION != $ExpectedBuild`: raise RuntimeError(f'Expected Build $ExpectedBuild, found {app.BUILD_VERSION}')
s=app.health_status()
if not s['database']['available']: raise RuntimeError('Align database is not available')
if s['database'].get('backend','sqlite') != 'sqlite': raise RuntimeError('Local installer expected SQLite backend')
print('Application import: OK')
print('Build ${ExpectedBuild}: OK')
print('SQLite backend: OK')
print('Health check: OK')
"@
  Run-Step $venvPython @('-c',$appVerify) 'Verify Align application'

  Write-Host ''
  Write-Host '============================================================' -ForegroundColor Green
  Write-Host ' ALIGN INSTALLATION COMPLETE' -ForegroundColor Green
  Write-Host '============================================================' -ForegroundColor Green
  Write-Host "Build: $ExpectedBuild"
  Write-Host "Python: $($python.Version)"
  Write-Host "Environment: $venv"
  Write-Host "Database: $database"
  Write-Host 'Start with Start-Align.bat' -ForegroundColor Cyan
  Write-Host 'http://127.0.0.1:8001/' -ForegroundColor Cyan
  Write-Host "Log: $LogFile" -ForegroundColor DarkGray
  exit 0
} catch { Stop-Install $_.Exception.Message }

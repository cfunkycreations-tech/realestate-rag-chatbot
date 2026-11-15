# Runs only an isolated disposable Compose project. Never removes volumes.
$ErrorActionPreference = 'Stop'
$project = "funkbot-smoke-$PID"
$composeFile = Join-Path $PSScriptRoot 'smoke-compose.yml'
$started = $false
$failed = $false
try {
    docker compose version
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is not available.' }
    $started = $true
    docker compose -p $project -f $composeFile up --build -d
    if ($LASTEXITCODE -ne 0) { throw 'The isolated smoke stack failed to build or start.' }
    $binding = docker compose -p $project -f $composeFile port frontend 3000
    if ($LASTEXITCODE -ne 0 -or "$binding" -notmatch ':(\d+)\s*$') { throw 'Could not determine the frontend smoke port.' }
    $port = $Matches[1]
    $healthy = $false
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 3
            if ($health.status -eq 'ok') { $healthy = $true; break }
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $healthy) { throw 'The frontend proxy did not return a healthy API response.' }
    $check = "import sqlite3; from alembic.script import ScriptDirectory; from alembic.config import Config; c=Config(); c.set_main_option('script_location','funkbot/migrations'); head=ScriptDirectory.from_config(c).get_current_head(); db=sqlite3.connect('/data/funk.db'); actual=db.execute('select version_num from alembic_version').fetchone()[0]; assert actual == head, f'migration {actual} != {head}'; print('Migration head:',actual)"
    docker compose -p $project -f $composeFile exec -T backend python -c $check
    if ($LASTEXITCODE -ne 0) { throw 'The database is not at the current migration head.' }
    Write-Host "Smoke test passed at http://127.0.0.1:$port/api/health (project $project)."
} catch {
    Write-Error -ErrorRecord $_ -ErrorAction Continue
    $failed = $true
} finally {
    if ($started) {
        docker compose -p $project -f $composeFile down
        if ($LASTEXITCODE -ne 0) { Write-Error 'Could not stop the isolated smoke stack.' -ErrorAction Continue; $failed = $true }
        Write-Host "The isolated $project data volume was retained; existing installation volumes were not touched."
    }
}
if ($failed) { exit 1 }
exit 0

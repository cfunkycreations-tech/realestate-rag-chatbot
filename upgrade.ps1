# Funk Bot upgrade: backs up Docker volumes (never removes them), rebuilds, shows status.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $PSScriptRoot "_volume_backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$volumes = docker volume ls --format "{{.Name}}" | Where-Object { $_ -match "(funk_data|omniroute_data)$" }
if (-not $volumes) { throw "No funk_data or omniroute_data Docker volumes found. Run 'docker volume ls' and check the names." }

foreach ($v in $volumes) {
    Write-Host "Backing up volume $v ..."
    docker run --rm -v "${v}:/data:ro" -v "${backupDir}:/backup" alpine tar czf "/backup/$v-$stamp.tgz" -C /data .
    if ($LASTEXITCODE -ne 0) { throw "Backup of $v failed. Nothing was changed." }
}
Write-Host "Backups saved in $backupDir"

Write-Host "Rebuilding Funk Bot ..."
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose reported an error. Your volumes are untouched and backed up." }

Start-Sleep -Seconds 10
$bannerSrc = Join-Path $PSScriptRoot "_patch1_stage\banner.png"
if (Test-Path $bannerSrc) {
    Start-Sleep -Seconds 5
    docker compose cp $bannerSrc backend:/data/banner.png
    if ($LASTEXITCODE -eq 0) { Write-Host "New banner installed."; Move-Item -Force $bannerSrc (Join-Path $PSScriptRoot "_patch1_stage\banner.installed.png") } else { Write-Host "Banner copy failed; it will retry on the next run." }
}
$ErrorActionPreference = "Continue"
docker compose ps
docker compose ps -a 2>&1 | Out-File -Encoding utf8 (Join-Path $PSScriptRoot "last-run-log.txt")
"----- BACKEND LOG -----" | Out-File -Append -Encoding utf8 (Join-Path $PSScriptRoot "last-run-log.txt")
docker compose logs backend --tail 300 2>&1 | Out-File -Append -Encoding utf8 (Join-Path $PSScriptRoot "last-run-log.txt")
"----- FRONTEND LOG -----" | Out-File -Append -Encoding utf8 (Join-Path $PSScriptRoot "last-run-log.txt")
docker compose logs frontend --tail 60 2>&1 | Out-File -Append -Encoding utf8 (Join-Path $PSScriptRoot "last-run-log.txt")
docker compose logs backend --tail 40

Write-Host ""
Write-Host "Checking the Agent Computer in a separate throwaway Docker project (first run takes several minutes)..."
if (Test-Path (Join-Path $PSScriptRoot "scripts\verify-computer.bat")) {
    cmd /c "`"$PSScriptRoot\scripts\verify-computer.bat`"" 2>&1 | Out-Null
    Write-Host "Agent Computer check finished. Results saved in computer-verification.txt"
}
Write-Host ""
Write-Host "Done. Open http://localhost:3000"

param(
  [string]$Port = "COM7",
  [string]$RepoRawBase = "https://raw.githubusercontent.com/sjorsansems/retro-alarm-clock/main"
)

$ErrorActionPreference = "Stop"

Write-Host "== Retro AlarmKlok post-flash deploy =="
Write-Host "Port: $Port"

$files = @(
  "main.py",
  "retro_georgy_alarm_klok_v6.py",
  "retro_georgy_alarm_klok_v6_backup.py",
  "config_manager.py",
  "index_v6.html"
)

$tmpDir = Join-Path $env:TEMP "alarmklok-deploy"
if (-not (Test-Path $tmpDir)) {
  New-Item -ItemType Directory -Path $tmpDir | Out-Null
}

foreach ($name in $files) {
  $url = "$RepoRawBase/$name"
  $dst = Join-Path $tmpDir $name
  Write-Host "Download: $url"
  Invoke-WebRequest -Uri $url -OutFile $dst
}

Write-Host "Uploading files with mpremote..."
$cmd = @(
  "-m", "mpremote", "connect", $Port,
  "+", "cp", (Join-Path $tmpDir "main.py"), ":main.py",
  "+", "cp", (Join-Path $tmpDir "retro_georgy_alarm_klok_v6.py"), ":retro_georgy_alarm_klok_v6.py",
  "+", "cp", (Join-Path $tmpDir "retro_georgy_alarm_klok_v6_backup.py"), ":retro_georgy_alarm_klok_v6_backup.py",
  "+", "cp", (Join-Path $tmpDir "config_manager.py"), ":config_manager.py",
  "+", "cp", (Join-Path $tmpDir "index_v6.html"), ":index_v6.html",
  "+", "reset"
)

& python @cmd

Write-Host "Done. Device reboot command sent."
$ErrorActionPreference = "Stop"

$dir = Join-Path $env:USERPROFILE ".claude-code-router"
$cfg = Join-Path $dir "config.json"
$src = Join-Path $env:TEMP "glm_ccr_config.json"

New-Item -ItemType Directory -Force -Path $dir | Out-Null

if (Test-Path $cfg) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $bak = Join-Path $dir "config.qwen_backup_$stamp.json"
  Copy-Item $cfg $bak
  Write-Output "backup=$bak"
}

Copy-Item $src $cfg -Force
Write-Output "config=$cfg"


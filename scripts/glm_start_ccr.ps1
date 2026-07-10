$ErrorActionPreference = "Continue"

$cli = Join-Path $env:APPDATA "npm\node_modules\@musistudio\claude-code-router\dist\cli.js"
$node = "node"
$out = Join-Path $env:TEMP "glm_ccr_start.out.log"
$err = Join-Path $env:TEMP "glm_ccr_start.err.log"
Remove-Item -Force $out,$err -ErrorAction SilentlyContinue

Start-Process -FilePath $node -ArgumentList @($cli, "start") -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
Start-Sleep -Seconds 5

ccr status
netstat -ano | findstr ":3456"
Write-Output "--- stdout ---"
if (Test-Path $out) { Get-Content $out }
Write-Output "--- stderr ---"
if (Test-Path $err) { Get-Content $err }

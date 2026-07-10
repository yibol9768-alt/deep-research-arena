$ErrorActionPreference = "Stop"

$p = Join-Path $env:APPDATA "npm/node_modules/@musistudio/claude-code-router/dist/cli.js"
$s = Get-Content -Raw $p

$patterns = @(
  "RD=async",
  "getServer:()=>",
  "getServer=",
  "getServer:()",
  "lC.getServer",
  "start:async",
  "async start",
  "Z0=async",
  "async function Z0",
  "function Z0"
)

foreach ($pat in $patterns) {
  $idx = $s.IndexOf($pat)
  if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 3000)
    $len = [Math]::Min(12000, $s.Length - $start)
    Write-Output "FOUND pattern=$pat idx=$idx"
    Write-Output $s.Substring($start, $len)
    exit 0
  }
}

Write-Output "not found"

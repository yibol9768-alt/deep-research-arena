$ErrorActionPreference = "Stop"

$p = Join-Path $env:APPDATA "npm/node_modules/@musistudio/claude-code-router/dist/cli.js"
$s = Get-Content -Raw $p

$matches = [regex]::Matches($s, "(?<![A-Za-z0-9_])RD\s*=")
$n = 0
foreach ($m in $matches) {
  $n += 1
  $idx = $m.Index
  $start = [Math]::Max(0, $idx - 180)
  $len = [Math]::Min(900, $s.Length - $start)
  Write-Output "---- match $n idx=$idx ----"
  Write-Output $s.Substring($start, $len)
}

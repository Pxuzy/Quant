$ErrorActionPreference = 'Stop'
$root = 'E:\hermes\workspace\Quant\gstack'
$agents = Join-Path $root '.agents\skills'
New-Item -ItemType Directory -Force -Path $agents | Out-Null

$skills = Get-ChildItem 'C:\Users\PuSzy\.codex\skills' -Force |
  Where-Object { $_.Name -like 'gstack*' } |
  Select-Object -ExpandProperty Name

foreach ($name in $skills) {
  $dest = Join-Path $agents $name
  if (Test-Path $dest) { continue }

  $candidates = @(
    Join-Path $root $name
    Join-Path $root ($name -replace '^gstack-', '')
  )

  $target = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $target) { continue }

  cmd /c "mklink /J `"$dest`" `"$target`"" | Out-Null
}

Get-ChildItem $agents | Select-Object Name, Mode

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

Write-Host "Configuring git hooks path to .githooks in $repoRoot"
git -C $repoRoot config core.hooksPath .githooks

Write-Host "Done. Verify with: git -C $repoRoot config --get core.hooksPath"

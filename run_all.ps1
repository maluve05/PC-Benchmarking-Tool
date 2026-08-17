# run_all.ps1 — PowerShell wrapper for the Mandelbrot benchmark suite.
# Usage:  .\run_all.ps1            (full run)
#         .\run_all.ps1 -Quick     (reduced workload)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Prefer the `python` launcher, else `py`, else `python3`.
$Python = $null
foreach ($candidate in @("python", "py", "python3")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $candidate; break }
}
if (-not $Python) {
    Write-Host "ERROR: Python not found on PATH." -ForegroundColor Red
    exit 1
}

$args = @()
if ($Quick) { $args += "--quick" }
& $Python "run_all.py" @args
exit $LASTEXITCODE

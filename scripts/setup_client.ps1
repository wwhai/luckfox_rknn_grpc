$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root "client\.venv"
$python = Join-Path $venv "Scripts\python.exe"

$available = & py -0p 2>&1
if ($LASTEXITCODE -ne 0 -or -not ($available -match "3\.12")) {
    throw "Python 3.12 is required. Install it from python.org, then rerun this script."
}

if (Test-Path $venv) {
    Remove-Item -Recurse -Force $venv
}

& py -3.12 -m venv $venv
& $python -m pip install -r (Join-Path $root "client\requirements.txt")
& $python (Join-Path $root "scripts\generate_python.py")
& $python -c "import sys; sys.path.insert(0, r'$($root.Replace("'", "''"))\client'); import rknn_client, tk_app; print('Windows client setup passed')"

Write-Host "Run: & `"$python`" `"$(Join-Path $root 'client\tk_app.py')`""
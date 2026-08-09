$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$BootstrapCommand = $null
$BootstrapArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $BootstrapCommand = "py"
    $BootstrapArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $BootstrapCommand = "python"
} else {
    throw "Python 3 is required to prepare Accessible Caption Studio."
}

if (-not (Test-Path ".bootstrap\Scripts\python.exe")) {
    Write-Host "Preparing the private local installer..."
    & $BootstrapCommand @BootstrapArgs -m venv .bootstrap
    & ".bootstrap\Scripts\python.exe" -m pip install --upgrade pip uv
}

$env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD ".runtime\python"
$env:UV_CACHE_DIR = Join-Path $PWD ".runtime\cache"
$env:MPLCONFIGDIR = Join-Path $PWD "storage\temporary\matplotlib"

if (-not (Test-Path ".setup-complete-v6") -or -not (Test-Path ".studio-venv\Scripts\python.exe")) {
    Write-Host "Preparing Accessible Caption Studio. The first setup can take several minutes."
    & ".bootstrap\Scripts\python.exe" -m uv python install 3.11 --install-dir $env:UV_PYTHON_INSTALL_DIR --no-bin
    & ".bootstrap\Scripts\python.exe" -m uv venv --python 3.11 --clear .studio-venv
    & ".bootstrap\Scripts\python.exe" -m uv pip install --python ".studio-venv\Scripts\python.exe" -e ".[ml]"
    New-Item -ItemType File -Path ".setup-complete-v6" -Force | Out-Null
}

& ".studio-venv\Scripts\accessible-caption-studio.exe" start

param(
    [string]$Name = "blink_call"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "Conda is not installed or not available in PATH."
    exit 1
}

function Invoke-BlinkCallConda {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )
    & conda @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Conda command failed: conda $($Args -join ' ')"
    }
}

# Avoid plugin or console-encoding side effects when running conda commands in scripts.
$env:CONDA_NO_PLUGINS = "true"
$env:PYTHONIOENCODING = "utf-8"
$env:CONDA_SOLVER = "classic"

$EnvPattern = "^\s*" + [Regex]::Escape($Name) + "\s"
$EnvExists = conda env list | Select-String -Pattern $EnvPattern
if (-not $EnvExists) {
    Write-Host "Creating conda environment '$Name' with Python 3.10..."
    Invoke-BlinkCallConda -Args @("create", "-y", "-n", $Name, "python=3.10")
} else {
    Write-Host "Conda environment '$Name' already exists. Skipping creation."
}

Write-Host "Installing project dependencies..."
Invoke-BlinkCallConda -Args @("run", "-n", $Name, "python", "-m", "pip", "install", "--upgrade", "pip")
Invoke-BlinkCallConda -Args @("run", "-n", $Name, "--cwd", $ProjectRoot, "python", "-m", "pip", "install", "-e", ".")
Invoke-BlinkCallConda -Args @("run", "-n", $Name, "--cwd", $ProjectRoot, "pre-commit", "install")

Write-Host "Setup completed successfully in conda environment '$Name'."
Write-Host "To activate your environment, run: conda activate $Name"

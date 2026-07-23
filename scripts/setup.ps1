param(
    [switch]$Postgres
)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "A criar ambiente virtual em .venv..."
    python -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e ".[dev]"
if ($Postgres) {
    & $VenvPython -m pip install -e ".[postgres]"
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Copy-Item (Join-Path $ProjectRoot ".env.example") (Join-Path $ProjectRoot ".env")
}

Push-Location $ProjectRoot
try {
    & $VenvPython -m alembic upgrade head
} finally {
    Pop-Location
}

Write-Host "Ambiente pronto. Execute .\scripts\run.ps1 para iniciar a aplicação."

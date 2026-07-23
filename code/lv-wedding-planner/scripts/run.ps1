$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Ambiente .venv não encontrado. Execute .\scripts\setup.ps1 primeiro."
    exit 1
}

Push-Location $ProjectRoot
try {
    & $VenvPython -m uvicorn app.main:app --reload
} finally {
    Pop-Location
}

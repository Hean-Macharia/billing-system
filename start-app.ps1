param(
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Python virtual environment not found at: $venvPython"
}

Write-Host "Checking for processes using port $Port..."
$connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        if ($conn.OwningProcess) {
            Write-Host "Stopping PID $($conn.OwningProcess) on port $Port"
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

$uvicornArgs = @(
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "$Port"
)

if ($Reload) {
    $uvicornArgs += "--reload"
}

Write-Host "Starting app with: $venvPython $($uvicornArgs -join ' ')"
& $venvPython @uvicornArgs

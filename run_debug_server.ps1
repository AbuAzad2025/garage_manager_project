# Flask Debug Server Runner
# ========================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Flask Server with Debug Mode" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server URL: " -NoNewline
Write-Host "http://localhost:5000" -ForegroundColor Yellow
Write-Host "Debug Mode: " -NoNewline
Write-Host "ENABLED" -ForegroundColor Green
Write-Host "Auto-Reload: " -NoNewline
Write-Host "ENABLED" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set environment variables
$env:FLASK_APP = "app.py"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "1"
$env:PYTHONIOENCODING = "utf-8"

# Change to script directory
Set-Location $PSScriptRoot

# Check if virtual environment exists
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & .venv\Scripts\Activate.ps1
}

# Run the Flask app
Write-Host "Starting Flask application..." -ForegroundColor Green
Write-Host ""
python app.py


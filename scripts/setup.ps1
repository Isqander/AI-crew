# ===========================================
# AI-crew Setup Script (PowerShell)
# ===========================================

Write-Host "🚀 AI-crew Setup" -ForegroundColor Cyan
Write-Host "==================" -ForegroundColor Cyan

# Check for required tools
function Test-Command {
    param([string]$Command)
    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        Write-Host "✓ $Command found" -ForegroundColor Green
        return $true
    } else {
        Write-Host "❌ $Command is required but not installed." -ForegroundColor Red
        return $false
    }
}

Write-Host ""
Write-Host "Checking requirements..."

$dockerOk = Test-Command "docker"
$nodeOk = Test-Command "node"
$npmOk = Test-Command "npm"

if (-not ($dockerOk -and $nodeOk -and $npmOk)) {
    Write-Host "Please install missing requirements and try again." -ForegroundColor Red
    exit 1
}

# Create .env file if not exists
if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "Creating .env file from template..."
    Copy-Item "env.example" ".env"
    Write-Host "✓ .env created - please edit it with your API keys" -ForegroundColor Green
} else {
    Write-Host "✓ .env already exists" -ForegroundColor Green
}

# Install frontend dependencies
Write-Host ""
Write-Host "Installing frontend dependencies..."
Set-Location frontend
npm install
Set-Location ..
Write-Host "✓ Frontend dependencies installed" -ForegroundColor Green

# Create Python virtual environment
if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host ""
    Write-Host "Setting up Python environment..."
    
    if (-not (Test-Path "venv")) {
        python -m venv venv
        Write-Host "✓ Virtual environment created" -ForegroundColor Green
    }
    
    # Activate and install
    & ".\venv\Scripts\Activate.ps1"
    pip install -r requirements.txt
    Write-Host "✓ Python dependencies installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Edit .env file with your API keys"
Write-Host "2. Start the services:"
Write-Host "   docker-compose up -d" -ForegroundColor Yellow
Write-Host ""
Write-Host "3. Start frontend (dev mode):"
Write-Host "   cd frontend; npm run dev" -ForegroundColor Yellow
Write-Host ""
Write-Host "4. Open in browser:"
Write-Host "   - Web UI: http://localhost:5173"
Write-Host "   - API: http://localhost:8000"
Write-Host "   - Langfuse: http://localhost:3000"
Write-Host ""
Write-Host "5. Connect LangGraph Studio to http://localhost:8000"
Write-Host "==========================================" -ForegroundColor Cyan

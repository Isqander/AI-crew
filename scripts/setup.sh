#!/bin/bash
# ===========================================
# AI-crew Setup Script
# ===========================================

set -e

echo "🚀 AI-crew Setup"
echo "=================="

# Check for required tools
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "❌ $1 is required but not installed."
        exit 1
    fi
    echo "✓ $1 found"
}

echo ""
echo "Checking requirements..."
check_command docker
check_command docker-compose
check_command node
check_command npm

# Create .env file if not exists
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from template..."
    cp env.example .env
    echo "✓ .env created - please edit it with your API keys"
else
    echo "✓ .env already exists"
fi

# Install frontend dependencies
echo ""
echo "Installing frontend dependencies..."
cd frontend
npm install
cd ..
echo "✓ Frontend dependencies installed"

# Create Python virtual environment (optional)
if command -v python3 &> /dev/null; then
    echo ""
    echo "Setting up Python environment..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        echo "✓ Virtual environment created"
    fi
    
    # Activate and install
    source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null
    pip install -r requirements.txt
    echo "✓ Python dependencies installed"
fi

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Start the services:"
echo "   docker-compose up -d"
echo ""
echo "3. Start frontend (dev mode):"
echo "   cd frontend && npm run dev"
echo ""
echo "4. Open in browser:"
echo "   - Web UI: http://localhost:5173"
echo "   - API: http://localhost:8000"
echo "   - Langfuse: http://localhost:3001"
echo ""
echo "5. Connect LangGraph Studio to http://localhost:8000"
echo "=========================================="

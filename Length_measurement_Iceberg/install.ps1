# Iceberg Tracking System - Installation Script for Windows
# Run in PowerShell as Administrator

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "ICEBERG TRACKING SYSTEM - INSTALLATION" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "[1/5] Checking Python version..." -ForegroundColor Yellow
python --version

if ($LASTEXITCODE -ne 0) {
    Write-Host " Python not found. Please install Python 3.8 or higher." -ForegroundColor Red
    Write-Host "   Download from: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Python found" -ForegroundColor Green
Write-Host ""

# Update pip
Write-Host "[2/5] Updating pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install dependencies
Write-Host ""
Write-Host "[3/5] Installing dependencies..." -ForegroundColor Yellow
Write-Host "This may take 5-10 minutes..." -ForegroundColor Yellow
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host " Installation failed. Check error messages above." -ForegroundColor Red
    exit 1
}

Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Check for RealSense (Windows doesn't have lsusb by default)
Write-Host "[4/5] Camera check..." -ForegroundColor Yellow
Write-Host "⚠ Please ensure Intel RealSense D415 is connected" -ForegroundColor Yellow
Write-Host ""

# Test imports
Write-Host "[5/5] Testing module imports..." -ForegroundColor Yellow
python -c @"
import sys
sys.path.insert(0, 'src')

try:
    from modules import VisionProcessor, DepthMeasurement
    from utils import RealSenseCamera
    print('✓ All modules imported successfully')
except Exception as e:
    print(f' Import error: {e}')
    sys.exit(1)
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host " Module import failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "✓ INSTALLATION COMPLETE!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Quick Start:" -ForegroundColor Cyan
Write-Host "  Desktop App:    python src/main.py" -ForegroundColor White
Write-Host "  Web Interface:  python src/gui/web_interface.py" -ForegroundColor White
Write-Host ""
Write-Host "Documentation: README.md" -ForegroundColor Cyan
Write-Host "Quick Guide: QUICK_RUN.md" -ForegroundColor Cyan
Write-Host ""
Write-Host "Good luck with the competition! "" -ForegroundColor Yellow

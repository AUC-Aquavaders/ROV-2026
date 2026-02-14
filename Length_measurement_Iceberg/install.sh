#!/bin/bash

# Iceberg Tracking System - Installation Script
# For Raspberry Pi / Linux systems

echo "========================================="
echo "ICEBERG TRACKING SYSTEM - INSTALLATION"
echo "========================================="
echo ""

# Check Python version
echo "[1/5] Checking Python version..."
python3 --version

if [ $? -ne 0 ]; then
    echo "❌ Python 3 not found. Please install Python 3.8 or higher."
    exit 1
fi

echo "✓ Python 3 found"
echo ""

# Update pip
echo "[2/5] Updating pip..."
python3 -m pip install --upgrade pip

# Install dependencies
echo ""
echo "[3/5] Installing dependencies..."
echo "This may take 5-10 minutes..."
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Installation failed. Check error messages above."
    exit 1
fi

echo "✓ Dependencies installed"
echo ""

# Verify RealSense
echo "[4/5] Checking for RealSense camera..."
if lsusb | grep -q "8086:0b07"; then
    echo "✓ Intel RealSense D415 detected"
else
    echo "⚠ RealSense camera not detected"
    echo "  Please connect camera and restart"
fi

echo ""

# Test imports
echo "[5/5] Testing module imports..."
python3 -c "
import sys
sys.path.insert(0, 'src')

try:
    from modules import VisionProcessor, DepthMeasurement
    from utils import RealSenseCamera
    print('✓ All modules imported successfully')
except Exception as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Module import failed"
    exit 1
fi

echo ""
echo "========================================="
echo "✓ INSTALLATION COMPLETE!"
echo "========================================="
echo ""
echo "Quick Start:"
echo "  Desktop App:    python3 src/main.py"
echo "  Web Interface:  python3 src/gui/web_interface.py"
echo ""
echo "Documentation: README.md"
echo "Quick Guide: QUICK_RUN.md"
echo ""
echo "Good luck with the competition! 🏆"

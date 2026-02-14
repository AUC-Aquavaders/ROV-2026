# Iceberg Tracking System - Production Release

**MATE ROV Competition 2026 - Task 2.2: Iceberg Tracking**

Complete automated system for ROV iceberg survey, depth measurement, and threat assessment.

---

## 🎯 System Overview

This system enables your ROV to automatically:

1. **Survey Iceberg Corners** - Detect and recognize 5 sequential numbers (0-4 or 5-9) using OCR
2. **Measure Keel Depth** - Accurately measure depth (0.5m - 1.5m) using stereo depth camera
3. **Calculate Threat Levels** - Assess danger to oil platforms and subsea assets
4. **Generate Judge Reports** - Export competition-ready data and scoring

**Maximum Points: 35**
- Survey all 5 corners: 10 points
- Keel depth within ±5cm: 10 points
- Platform threats (all correct): 10 points
- Subsea threats (all correct): 5 points

---

## 📋 Hardware Requirements

### Required Hardware
- **Raspberry Pi 4** (4GB RAM minimum, 8GB recommended)
- **Intel RealSense D415** Stereo Depth Camera
- **USB 3.0 Connection** (blue USB port on Raspberry Pi)
- **Waterproof housing** for camera
- **Stable camera mount** on ROV frame

### Network Setup
- ROV running BlueOS
- Network: 192.168.2.x (default BlueOS configuration)
- Raspberry Pi IP: 192.168.2.2

---

## 🚀 Quick Start

### 1. Install on Raspberry Pi

```bash
# SSH into Raspberry Pi
ssh pi@192.168.2.2

# Copy this folder to Raspberry Pi
# (use scp, USB drive, or git clone)

cd final\ product

# Install dependencies
pip install -r requirements.txt
```

### 2. Verify Camera Connection

```bash
# Check if RealSense is detected
lsusb | grep Intel

# Should show:
# Bus 002 Device XXX: ID 8086:0b07 Intel Corp. RealSense D415
```

### 3. Run the System

**Option A: Desktop Application (OpenCV GUI)**
```bash
python src/main.py
```

**Option B: Web Interface (Remote Operation)**
```bash
cd src/gui
python web_interface.py

# Access from surface computer:
# http://192.168.2.2:5000
```

---

## 🎮 Operation Guide

### Desktop Application Controls

| Key | Action |
|-----|--------|
| **D** | Detect number in current view |
| **M** | Measure keel depth at crosshair |
| **S** | Save current survey |
| **T** | Calculate threat levels (interactive) |
| **R** | Reset survey (start over) |
| **Q** | Quit application |

### Survey Workflow

1. **Start the application**
   - Camera feed appears with HUD overlay
   - Survey status shows "0/5 corners found"

2. **Navigate to first number**
   - Drive ROV to iceberg corner
   - Center number in camera view
   - Press **D** to detect

3. **Repeat for all 5 corners**
   - System validates numbers are sequential (0-4 or 5-9)
   - Progress shown on HUD: "3/5 corners found"

4. **Measure keel depth**
   - Navigate to keel pipe
   - Center pipe in crosshair
   - Hold ROV steady (30-50cm from pipe)
   - Press **M** to measure
   - System takes 20 samples and averages

5. **Save survey**
   - Press **S** to save all data
   - Judge report exported to `data/exports/`

6. **Calculate threats** (after competition)
   - Press **T** to enter interactive mode
   - Input iceberg data from judge:
     - Latitude, Longitude
     - Heading (degrees)
     - Keel depth (uses measured value)
   - System calculates all threat levels
   - Results saved automatically

---

## 🌐 Web Interface

For remote operation from surface computer:

### Starting Web Server
```bash
cd src/gui
python web_interface.py
```

### Access Interface
- Open browser: `http://192.168.2.2:5000`
- Live video feed with HUD overlay
- Click buttons for all operations:
  - **Detect Number**
  - **Measure Depth**
  - **Save Survey**
  - **Calculate Threats** (form input)
  - **Reset Survey**

### Features
- Real-time video streaming
- Survey progress panel
- Threat level calculator
- Automatic data logging
- Export judge reports

---

## 📁 File Structure

```
final product/
├── README.md                   # This file - Complete documentation
├── QUICK_RUN.md               # Quick reference guide
├── requirements.txt            # Python dependencies
│
├── src/
│   ├── main.py                # Desktop application (OpenCV GUI)
│   │
│   ├── modules/               # Core functionality
│   │   ├── vision_processor.py      # OCR number detection
│   │   ├── depth_measurement.py     # RealSense depth sensing
│   │   ├── survey_tracker.py        # Progress tracking
│   │   ├── threat_calculator.py     # Threat assessment
│   │   ├── data_manager.py          # Database & export
│   │   └── video_overlay.py         # HUD display
│   │
│   ├── utils/                 # Helper functions
│   │   ├── realsense_camera.py      # Camera interface
│   │   ├── navigation.py            # GPS calculations
│   │   └── image_processing.py      # Image enhancement
│   │
│   └── gui/                   # Web interface
│       ├── web_interface.py         # Flask server
│       └── templates/
│           └── index.html           # Web UI
│
├── config/                    # Configuration files
│   ├── camera_config.yaml          # RealSense settings
│   ├── ocr_config.yaml             # OCR tuning
│   └── platform_data.json          # Platform coordinates
│
└── data/                      # Generated data (auto-created)
    ├── surveys/               # Survey database
    ├── logs/                  # System logs
    └── exports/               # Judge reports
```

---

## ⚙️ Configuration

### Camera Settings (`config/camera_config.yaml`)

```yaml
camera:
  width: 1280          # Resolution
  height: 720
  fps: 30
  
  depth:
    preset: "high_accuracy"
    min_distance: 0.3
    max_distance: 3.0
  
underwater:
  enhancement:
    enable_clahe: true      # Contrast enhancement
    enable_white_balance: true
    enable_denoise: true
```

**Tuning Tips:**
- Increase `clahe_clip_limit` for murky water (3.0-5.0)
- Decrease `laser_power` if too much backscatter
- Use `high_density` preset for close-range work

### OCR Settings (`config/ocr_config.yaml`)

```yaml
ocr:
  engine: easyocr              # or 'tesseract'
  
postprocessing:
  confidence:
    minimum_threshold: 0.6     # Reject low-confidence detections
    
preprocessing:
  underwater_mode: true        # Enable underwater enhancement
```

**Tuning Tips:**
- Lower `minimum_threshold` to 0.5 if missing numbers
- Increase to 0.7-0.8 to reduce false detections
- Try `tesseract` if EasyOCR struggles with font

---

## 🔧 Troubleshooting

### Camera Not Detected

**Problem:** `pyrealsense2 not found` or camera not initializing

**Solutions:**
1. Verify USB 3.0 connection (blue port)
2. Check cable is securely connected
3. Test with: `rs-enumerate-devices`
4. Reinstall driver: `pip install --upgrade pyrealsense2`

### OCR Not Detecting Numbers

**Problem:** Numbers not being recognized

**Solutions:**
1. Check image clarity (reduce motion blur)
2. Adjust distance from number (30-60cm optimal)
3. Improve lighting conditions
4. Lower confidence threshold in `ocr_config.yaml`
5. Clean camera viewport (check for scratches/fog)

### Depth Measurement Errors

**Problem:** "Invalid measurement" or unstable depth readings

**Solutions:**
1. Hold ROV steady (minimize movement)
2. Ensure target is 30-50cm away
3. Avoid transparent/reflective surfaces
4. Check for bubbles in camera view
5. Increase `measurement_samples` to 30-50

### Web Interface Won't Start

**Problem:** Flask server fails to start

**Solutions:**
1. Verify all dependencies installed: `pip install flask flask-cors`
2. Check port 5000 not in use: `netstat -an | grep 5000`
3. Check firewall allows port 5000
4. Try different port: `app.run(port=5001)`

---

## 📊 Understanding the Output

### Survey Status Display

```
Corners Found: 3/5
Keel Depth: 1.234m (confidence: 95%)
Sequence: 5, 6, 7 [VALID]
Points: 15/35
```

### Threat Assessment Report

```
PLATFORM THREATS
----------------
Hibernia:    GREEN (distance: 15.3 nm)
Sea Rose:    YELLOW (distance: 8.2 nm)
Terra Nova:  RED (distance: 2.1 nm)
Hebron:      GREEN (distance: 12.7 nm)

SUBSEA THREATS
--------------
Hibernia:    GREEN (keel: 1.2m, water: -78m)
Sea Rose:    GREEN (keel: 1.2m, water: -107m)
Terra Nova:  YELLOW (keel: 1.2m, water: -91m)
Hebron:      GREEN (keel: 1.2m, water: -93m)
```

### Threat Level Criteria

**Platform Distance Threats:**
- RED: < 5 nautical miles
- YELLOW: 5-10 nautical miles
- GREEN: > 10 nautical miles

**Subsea Depth Threats:**
- RED: Keel depth > 70% of water depth
- YELLOW: Keel depth 50-70% of water depth
- GREEN: Keel depth < 50% of water depth

---

## 🎯 Competition Checklist

### Pre-Competition (24 hours before)

- [ ] Test camera connection on Raspberry Pi
- [ ] Verify all dependencies installed
- [ ] Run full survey test with practice iceberg
- [ ] Verify OCR detecting numbers accurately
- [ ] Test depth measurement (±5cm accuracy)
- [ ] Check network connectivity (Pi accessible from surface)
- [ ] Clean camera viewport (no scratches/fog)
- [ ] Charge all batteries
- [ ] Export test survey report (verify format)

### During Competition

- [ ] Power on Raspberry Pi first
- [ ] Wait 30 seconds for boot
- [ ] SSH and start application
- [ ] Verify camera feed visible
- [ ] Complete survey (all 5 corners)
- [ ] Measure keel depth (hold steady 5 seconds)
- [ ] Save survey immediately
- [ ] Export report for judges
- [ ] Record all measurements on paper (backup)

### Post-Survey (Threat Calculation)

- [ ] Receive iceberg data from judges
- [ ] Run threat calculator (press T)
- [ ] Input: latitude, longitude, heading
- [ ] Use measured keel depth
- [ ] Export final report
- [ ] Submit to judges

---

## 🏆 Scoring Guide

### Corner Survey (10 points)

- All 5 corners correct sequence: **10 points**
- 4 corners correct: **8 points**
- 3 corners correct: **6 points**
- Sequence must be 0-4 OR 5-9 (no mixing)

### Keel Depth (10 points)

- Within ±5cm of actual: **10 points**
- Within ±10cm: **7 points**
- Within ±15cm: **5 points**
- System shows confidence level - aim for >90%

### Platform Threats (10 points)

- All 4 platforms correct: **10 points**
- 3 correct: **7 points**
- 2 correct: **5 points**

### Subsea Threats (5 points)

- All 4 assets correct: **5 points**
- 3 correct: **3 points**
- 2 correct: **2 points**

---

## 🔒 System Features

### Computer Vision
- **Underwater image enhancement** (CLAHE, white balance, denoising)
- **OCR with confidence scoring** (EasyOCR or Tesseract)
- **Number validation** (0-9, sequential checking)
- **Real-time detection** with visual feedback

### Depth Measurement
- **Multi-sample averaging** (20+ samples for accuracy)
- **Outlier filtering** (reject erroneous readings)
- **Confidence scoring** (validates measurement quality)
- **±5cm accuracy** achievable with stable positioning

### Data Management
- **SQLite database** (all surveys logged)
- **Automatic exports** (CSV format for judges)
- **Timestamped logging** (full mission replay)
- **Backup on save** (data integrity)

### User Interface
- **HUD overlay** (survey status, depth, crosshair)
- **Web interface** (remote operation)
- **Keyboard controls** (quick operation)
- **Visual feedback** (color-coded alerts)

---

## 📞 Support & Maintenance

### System Health Check

```bash
# Test all components
python -c "
from src.modules import *
from src.utils import *
print('✓ All modules imported successfully')
"

# Test camera
rs-enumerate-devices

# Test OCR
python -c "import easyocr; print('✓ EasyOCR ready')"
```

### Performance Optimization

**For faster OCR:**
1. Enable GPU acceleration
2. Install CUDA toolkit
3. Set `gpu: true` in `ocr_config.yaml`
4. 3-5x faster detection

**For better accuracy:**
1. Use higher resolution (1920x1080)
2. Increase `measurement_samples` to 50
3. Lower `minimum_threshold` slightly
4. Improve lighting on ROV

---

## 📝 License & Credits

**Developed for:** MATE ROV Competition 2026  
**Task:** 2.2 - Iceberg Tracking  
**Version:** 1.0.0 Production Release  
**Platform:** Raspberry Pi 4 + Intel RealSense D415

This system integrates:
- EasyOCR / Tesseract (OCR)
- Intel RealSense SDK (depth sensing)
- OpenCV (computer vision)
- Flask (web interface)
- NumPy, Pandas (data processing)

---

## 🚦 Quick Reference

**Start Desktop App:** `python src/main.py`  
**Start Web Interface:** `python src/gui/web_interface.py`  
**Web Access:** `http://192.168.2.2:5000`  
**Export Location:** `data/exports/`  
**Logs Location:** `data/logs/`  

**Emergency Reset:** Press **R** or restart application  
**Save Work:** Press **S** frequently during operation  

**Competition Day:** See [QUICK_RUN.md](QUICK_RUN.md) for streamlined checklist

---

**Good luck with the competition! 🤖🌊**

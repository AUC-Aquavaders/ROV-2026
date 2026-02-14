# Quick Run Guide - Competition Day

**Iceberg Tracking System - MATE ROV 2026**

Quick reference for competition operation. For full documentation, see [README.md](README.md).

---

## ⚡ Competition Day Startup

### 1. Power On Sequence (2 minutes)

```bash
# 1. Power on Raspberry Pi
# 2. Wait 30 seconds for boot
# 3. SSH from surface computer
ssh pi@192.168.2.2

# 4. Navigate to project
cd final\ product

# 5. Start application
python src/main.py
```

**OR use Web Interface:**
```bash
cd src/gui
python web_interface.py
# Access: http://192.168.2.2:5000
```

---

## 🎮 Operation - Desktop App

### Controls
| Key | Action | When to Use |
|-----|--------|-------------|
| **D** | Detect Number | When number centered in view |
| **M** | Measure Depth | When crosshair on keel pipe |
| **S** | Save Survey | After completing all 5 corners & depth |
| **T** | Threat Calculator | After judge provides iceberg data |
| **R** | Reset | If need to start over |
| **Q** | Quit | End of competition |

---

## 📋 Survey Procedure (10 minutes)

### Phase 1: Corner Survey (6-8 min)

1. **Navigate to Corner 1**
   - Drive ROV to first iceberg corner
   - Number should be ~15cm below waterline
   - Center number in camera view
   - Distance: 30-60cm from number
   
2. **Detect Number**
   - Press **D** key
   - Wait for confirmation (1-2 seconds)
   - Check HUD: "1/5 corners found"
   - Note: System expects 0-4 OR 5-9 sequence

3. **Repeat for Corners 2-5**
   - Navigate to each remaining corner
   - Press **D** at each corner
   - Track progress on HUD: "2/5", "3/5", etc.
   - System validates sequence automatically

4. **Confirm Survey Complete**
   - HUD shows: "5/5 corners found"
   - Sequence validated (GREEN status)

### Phase 2: Keel Depth (2-3 min)

1. **Locate Keel Pipe**
   - Navigate to deepest part of iceberg
   - Find vertical PVC pipe (0.5m - 1.5m long)

2. **Position ROV**
   - Distance: 30-50cm from pipe
   - Center pipe in crosshair
   - **HOLD ROV STEADY** (critical for accuracy)

3. **Measure**
   - Press **M** key
   - Hold position for 5 seconds
   - System takes 20 samples and averages
   - Wait for confirmation: "Depth: X.XXXm"

4. **Verify Measurement**
   - Check confidence score (aim for >90%)
   - If low confidence, remeasure:
     - Get closer (40cm optimal)
     - Reduce ROV movement
     - Check for bubbles blocking view

### Phase 3: Save Data (30 seconds)

1. **Save Survey**
   - Press **S** key
   - Confirmation: "Survey saved!"
   - Report exported to: `data/exports/`

2. **Backup (Optional but Recommended)**
   - Record measurements on paper:
     - Numbers found: ______
     - Keel depth: ______ m
   - In case of system failure

---

## 🎯 Post-Survey: Threat Calculator (3 minutes)

**After judge provides iceberg data sheet:**

1. **Press T** (Threat Calculator)

2. **Input Iceberg Data:**
   ```
   Latitude: [from judge sheet]
   Longitude: [from judge sheet]
   Heading: [from judge sheet, 0-360°]
   Keel depth: [auto-filled from measurement OR manual entry]
   ```

3. **Review Results**
   - Platform threats displayed (RED/YELLOW/GREEN)
   - Subsea threats displayed
   - All calculations automatic

4. **Export Final Report**
   - Results auto-saved
   - Report ready at: `data/exports/survey_report_YYYYMMDD_HHMMSS.csv`

---

## ⚠️ Quick Troubleshooting

### Numbers Not Detecting
- **Move closer** (30-60cm optimal)
- **Center number** in frame
- **Hold steady** (avoid motion blur)
- **Check lighting** (ROV lights on)
- **Clean viewport** (check for scratches/fog)

### Depth Reading "Invalid"
- **Hold ROV steady** (no movement for 5 sec)
- **Check distance** (30-50cm from pipe)
- **Avoid bubbles** (wait for bubbles to clear)
- **Remeasure** (press M again)

### Camera Not Working
- **Check USB cable** (blue USB 3.0 port)
- **Restart system** (Ctrl+C, then rerun)
- **Check connection:** `lsusb | grep Intel`

### Survey Won't Save
- **Check disk space:** `df -h`
- **Verify data folder exists**
- **Try again** (press S again)

---

## 📊 Scoring Quick Check

### Maximum Points: 35

✓ **Corner Survey (10 pts)**
- All 5 numbers in sequence: 10 pts
- Sequence must be 0-4 OR 5-9

✓ **Keel Depth (10 pts)**
- Within ±5cm: 10 pts
- Within ±10cm: 7 pts
- Aim for >90% confidence

✓ **Platform Threats (10 pts)**
- All 4 correct: 10 pts

✓ **Subsea Threats (5 pts)**
- All 4 correct: 5 pts

---

## 🔥 Competition Timeline

```
00:00 - Power on & start application
01:00 - Begin corner survey
02:00 - Corner 1 detected
03:00 - Corner 2 detected
04:00 - Corner 3 detected
05:00 - Corner 4 detected
06:00 - Corner 5 detected ✓ Survey complete
07:00 - Navigate to keel
08:00 - Position for depth measurement
09:00 - Depth measured ✓
09:30 - Save survey (Press S)
10:00 - Surface ROV
---
POST: Receive judge data sheet
POST: Run threat calculator (Press T)
POST: Submit final report
```

---

## 🚨 Emergency Procedures

### System Crash
1. **Restart application:** `python src/main.py`
2. **Data preserved** (auto-saved on each detection)
3. **Continue survey** from last saved state

### Lost Connection
1. **Check network:** `ping 192.168.2.2`
2. **Reconnect SSH:** `ssh pi@192.168.2.2`
3. **Restart if needed**

### Wrong Number Detected
1. **Press R** to reset survey
2. **OR** ignore and continue (system validates final sequence)
3. **Cannot remove individual number** - must reset all

---

## 📁 File Locations

**Export Reports:** `final product/data/exports/`  
**Logs:** `final product/data/logs/`  
**Database:** `final product/data/mission_data.db`

---

## ✅ Pre-Competition Checklist

**24 Hours Before:**
- [ ] Test full survey with practice iceberg
- [ ] Verify OCR detecting numbers (3+ tests)
- [ ] Test depth measurement accuracy (±5cm)
- [ ] Clean camera viewport
- [ ] Charge all batteries
- [ ] Backup configuration files

**1 Hour Before:**
- [ ] Power on Raspberry Pi
- [ ] SSH connection working
- [ ] Camera detected: `lsusb | grep Intel`
- [ ] Start test run (verify video feed)
- [ ] Close test run (ready for competition)

**Competition Start:**
- [ ] Start application
- [ ] Verify HUD overlay visible
- [ ] Survey status shows "0/5 corners"
- [ ] Ready to begin!

---

## 💡 Pro Tips

1. **OCR Accuracy**
   - Approach numbers slowly (reduce motion blur)
   - Center number perfectly before pressing D
   - Wait 1 second after centering before detecting

2. **Depth Precision**
   - Practice holding ROV steady beforehand
   - Use thruster micro-adjustments
   - Optimal distance: 40cm from pipe
   - Measure twice if first confidence <90%

3. **Time Management**
   - Budget 2 min per corner (10 min total)
   - Don't rush - accuracy > speed
   - Save progress frequently (press S)

4. **Backup Strategy**
   - Write numbers on slate as detected
   - Note depth reading on paper
   - Take photo of HUD screen (backup data)

---

## 🎯 Competition Workflow Summary

```
START → Camera On → Survey 5 Corners → Measure Depth → 
Save (Press S) → Surface → Get Judge Data → 
Calculate Threats (Press T) → Submit Report → WIN!
```

---

**For detailed help:** See [README.md](README.md)  
**System issues:** Restart application  
**Questions:** Refer to configuration files in `config/`

**GOOD LUCK! 🏆**

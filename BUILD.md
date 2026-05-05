# Synergy Teacher Dashboard — Build & Run Guide

## Quick Start (run from source)

```bash
# 1. Install Python 3.10+  →  https://python.org
# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

---

## Build a Portable Single-File EXE (Windows)

```bash
pip install pyinstaller
pyinstaller synergy_tool.spec
# Output:  dist\SynergyDashboard.exe
```

Copy `SynergyDashboard.exe` anywhere — USB stick, school laptop, etc.
Data is stored in `%USERPROFILE%\.synergy_tool\`.

---

## OCR Setup (timetable teacher detection)

OCR lets the tool read teacher names and codes directly from timetable screenshots.

### 1 — Install Tesseract

**Windows**
  Download and run the installer from:
  https://github.com/UB-Mannheim/tesseract/wiki
  Default install path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
  Add that folder to your PATH, or the tool will find it automatically.

**macOS**
```bash
brew install tesseract
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt install tesseract-ocr
```

### 2 — Install Python bindings
```bash
pip install pytesseract Pillow
```

### 3 — Verify
```bash
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

If OCR is not installed the timetable screenshot feature still works —
it just won't detect teacher names automatically.
You can still use the teacher filter by typing a name manually.

---

## Timetable Capture Workflow

1. Select a student in the sidebar.
2. Click the **🗓 Timetable** tab → **📸 Capture Timetable**.
   This switches you to the **🎯 Live Map** tab automatically.
3. Navigate to the student's timetable page in the embedded browser
   (log in to Synergy first if needed).
4. Click **📸 Capture Timetable** in the browser toolbar.
   A gold-bordered overlay appears.
5. Click and drag to draw a box around the timetable grid.
6. Press **C** to capture.
   The tool waits for the page to settle (configurable in ⚙ Settings),
   takes a screenshot of exactly the region you drew, and runs OCR.
7. You're returned to the **🗓 Timetable** tab where the image appears.

### Page settle time
If the timetable is dynamically loaded (e.g. loaded via JavaScript after
the page opens), increase the settle time in **⚙ Settings → Timetable Capture**.
Try 2000–3000 ms for slow-loading pages.

---

## Teacher Filter

- **Per-student:** In the 🗓 Timetable tab, use the "Teacher:" dropdown
  to highlight timetables containing a specific teacher.
  Blue tint = this teacher is in the timetable.
  Red tint = this teacher is NOT in this timetable.

- **Global:** The **🗂 All Timetables** tab shows every captured timetable
  across all students. Use the "Filter by teacher" dropdown to show only
  timetables that mention a given teacher — useful for finding all students
  taught by a particular teacher at a glance.

Teacher names are extracted by OCR from the screenshot using two methods:
  1. Full names:   "Mr Smith", "Mrs Jones", "Miss Taylor" etc.
  2. Staff codes:  2–4 uppercase letters appearing multiple times in the grid
                   (e.g. "SMI", "JON") — common in Synergy timetables.

---

## Data stored locally

All data lives in `~/.synergy_tool/` (never sent anywhere):
  `synergy.db`        — SQLite database (students, behaviours, contacts, mappings)
  `timetables/*.png`  — Timetable screenshots

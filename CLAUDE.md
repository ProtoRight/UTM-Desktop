# UTM Desktop — Project Notes for Claude

## Project Overview

A standalone Windows desktop application to control a Universal Test Machine (UTM) built on Arduino Uno + Arduino Nano. Replaces the Arduino IDE serial monitor with a proper GUI that handles serial communication, live graphing, test completion detection, specimen data entry, mechanical property calculations, and CSV export.

**GitHub Repo:** https://github.com/ProtoRight/UTM-Desktop  
**Working Directory:** `D:\Documents\3D Prints\1_Universal Tester\Code\Claude_UTM Desktop`  
**Arduino Source:** `DualMCU_UNO_V13_ISR_Stepper\DualMCU_UNO_V13_ISR_Stepper.ino`

---

## Technology Stack

- **Language:** Python
- **GUI:** PyQt6
- **Graphing:** matplotlib (embedded in PyQt6 via FigureCanvasQTAgg)
- **Serial:** pyserial
- **Math/Analysis:** numpy
- **Export:** csv (stdlib), future: reportlab or matplotlib for PDF/PNG
- **Packaging:** PyInstaller → standalone `.exe`

---

## Arduino Serial Protocol

**Baud rate:** 250,000  
**Format:** newline-terminated ASCII text

### Commands sent TO Arduino

| Command | Effect | State restriction |
|---|---|---|
| `IDLE` | Return to idle | Any |
| `RUN_3PT` | Start 3-point bend test (compression) | Any |
| `RUN_T` | Start tensile test (tension) | Any |
| `STOP` | Halt → FINISHED state | Any |
| `TARE` | Zero load cell | IDLE only |
| `ZERO` | Zero the DRO displacement | Any |
| `JOGSPEED <value>` | Set jog speed mm/min (0–150) | Any |
| `TESTSPEED <value>` | Set test crosshead speed mm/min (0–150) | Any (takes effect on next test start) |
| `RAW` | Switch to raw ADC output mode | Any |
| `CAL` | Enter load cell calibration mode | Any |
| `ZERO` *(in CAL)* | Zero step of calibration | LOADCAL |
| `WEIGHT <value>` *(in CAL)* | Apply known weight for calibration | LOADCAL |

### Data received FROM Arduino

| Pattern | Frequency | State |
|---|---|---|
| `Disp: X.XXX Load: X.XXX MotorState X Jog Speed Xmm/min` | 1000 ms | IDLE |
| `Disp: X.XXX Load: X.XXX` | 200 ms | RUNNING_3PT / RUNNING_T |
| `BOOT OK` | Once | Boot |
| `TESTING ABORTED - TRAVEL LIMIT REACHED` | On event | RUNNING |
| `TESTING ABORTED - LOAD LIMIT REACHED` | On event | RUNNING |
| `ESTOP PRESSED - ALL MOTORS DISABLED` | On event | Any |
| `MACHINE IS E-STOPPED - ENTER "IDLE" TO RETURN TO IDLE` | 1000 ms | ESTOP |
| `Raw Reading: XXXXXXX` | 1000 ms | RAWOUTPUT |

### Arduino Machine States
`IDLE` → `RUNNING_3PT` or `RUNNING_T` → `FINISHED` (or `ESTOP`)  
Also: `RAWOUTPUT`, `LOADCAL`

---

## Application Architecture

```
UTM_Desktop/
├── main.py                  # Entry point, launches QApplication
├── serial_worker.py         # QThread: continuous serial read, queued writes
├── data_store.py            # In-memory buffer for current test data
├── parser.py                # Parses Arduino strings → structured data
├── calculations.py          # Mechanical property math
├── settings.py              # Persistent user settings (QSettings or JSON)
├── gui/
│   ├── main_window.py       # Top-level window, layout manager
│   ├── control_panel.py     # Run, Stop, Tare, Zero, Jog Speed controls
│   ├── live_graph.py        # Embedded matplotlib: Force vs Displacement
│   ├── specimen_panel.py    # Specimen info + geometry input (pre-test)
│   ├── results_panel.py     # Post-test calculated results
│   └── status_bar.py        # Connection status, machine state, live values
├── requirements.txt
├── CLAUDE.md
└── DualMCU_UNO_V11_ISR_Stepper/   # Arduino source (reference only)
```

---

## GUI Panels & Features

### Connection Panel
- COM port dropdown (auto-populated from available ports)
- Refresh button to re-scan ports
- Connect / Disconnect button
- Auto-detection: on connect, app verifies it sees expected Arduino output (`BOOT OK` or idle data pattern) to confirm correct port
- Baud rate fixed at 250,000 (no need to expose this)

### Control Panel
Buttons mapped to serial commands:
- **Run 3PT Bend** → `RUN_3PT`
- **Run Tensile** → `RUN_T`
- **Stop** → `STOP`
- **Tare Load Cell** → `TARE` (greyed out unless state is IDLE)
- **Zero Displacement** → `ZERO`
- **Jog Speed** → text input + set button → `JOGSPEED <value>`
- Motor enable state indicator (read from idle output)

### Status Bar
- Connection state (Connected / Disconnected)
- Machine state (IDLE / RUNNING_3PT / RUNNING_T / FINISHED / ESTOP)
- Live load (kg)
- Live displacement (mm)
- E-stop alert (red highlight when ESTOP state)

### Live Graph
- Force (kg, Y-axis) vs Displacement (mm, X-axis)
- Updates at 200 ms intervals during test
- Auto-scales both axes as data arrives
- Marks test-completion point (fracture, limit hit, etc.)
- Clears on new test start
- Retains last test graph until next test begins

### Test Completion Detection (software side)
Three configurable triggers — all user-adjustable in the settings panel:
1. **Travel limit:** DRO >= user-set limit (mm)
2. **Load limit:** Load >= user-set limit (kg)
3. **Load drop:** Load falls ≥ X% from rolling peak (default 20%) — fracture detection

On any trigger: send `STOP`, freeze graph, mark completion point, run calculations.

### Specimen Information Panel (pre-test)
Fields always present:
- **Material name** (text) — included in CSV and future PDF/PNG export
- **Sample name / ID** (text) — included in CSV and future PDF/PNG export
- **Test type** (dropdown: 3-Point Bend / Tensile) — drives geometry fields

Cross-section selector with **graphical geometry preview** showing which dimension maps to which measurement:
- **Rectangular** — preview shows width (b) and height/thickness (d) labels on a rectangle
- **Circular (solid)** — preview shows diameter (d) label on a circle
- **Hollow tube (circular)** — preview shows outer diameter (D) and inner diameter (d)
- **I-beam / custom** — future addition

For **3-Point Bend**, additional fields:
- Support span (L, mm)
- Specimen width (b, mm)
- Specimen thickness (d, mm)

For **Tensile**, additional fields:
- Gauge length (L₀, mm)
- Cross-section dimensions (driven by cross-section selector above)

### Results Panel (post-test)
Displayed after test completes:

**Both test types:**
- Peak load (kg / N)
- Peak displacement (mm)

**3-Point Bend:**
- Flexural stress at peak: `σ = 3FL / (2bd²)` (MPa)
- Flexural strain at peak: `ε = 6δd / L²`
- Flexural modulus (linear region slope): `E = L³F / (4bd³δ)` (GPa)

**Tensile:**
- Cross-sectional area (mm²) — calculated from geometry inputs
- Ultimate tensile strength: `UTS = F_peak / A` (MPa)
- Engineering strain at peak: `ε = ΔL / L₀`
- Young's modulus (linear region slope): `E = stress / strain` (GPa)
- Yield strength (0.2% offset method — best-effort, noted as approximate)

### CSV Export
- **Raw data file:** `YYYY-MM-DD_HH-MM_<SampleID>_<TestType>_raw.csv`
  - Columns: timestamp, displacement (mm), load (kg)
- **Summary file:** appends one row per test to a running log
  - Columns: date, sample ID, material, test type, all calculated properties, specimen dimensions

---

## Settings (Persisted Between Sessions)

| Setting | Default | Notes |
|---|---|---|
| Last used COM port | — | Pre-selected on next launch |
| Travel limit | 40 mm | Arduino default |
| Load limit | 300 kg | Arduino default |
| Load drop threshold | 20% | Fracture detection |
| Load drop window | 10 samples | Rolling window size |
| Default jog speed | 50 mm/min | |
| CSV export directory | User's Documents | |

---

## Future Plans (Do Not Implement Yet)

- Testing database (store all runs with metadata, queryable)
- PDF report export with labeled graph, specimen photo, calculated properties
- PNG graph export with title, axis labels, specimen/material info
- Additional test types (compression, fatigue — long-term)
- Load cell calibration workflow in the GUI (currently CAL/WEIGHT commands via serial)

---

## Build & Packaging

```bash
pip install pyqt6 pyserial matplotlib numpy pyinstaller
pyinstaller --onefile --windowed main.py
```

Produces a single `UTM_Desktop.exe` in `dist/` — no Python installation required on target machine.

---

## Git Workflow

- Remote: https://github.com/ProtoRight/UTM-Desktop
- Commit at end of each completed phase minimum
- Commit message style: imperative, concise — e.g. `Add live serial graph with matplotlib`
- Push to `main` branch after each phase is stable

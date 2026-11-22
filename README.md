<div align="center">

# ICT-SCAN PRO

**PC Diagnostic & Optical Inspection Software for a Low-Cost In-Circuit PCB Tester**

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/GUI-CustomTkinter-0EA5E9?style=flat-square)
![Hardware](https://img.shields.io/badge/MCU-ESP32-E7352C?style=flat-square&logo=espressif&logoColor=white)
![Protocol](https://img.shields.io/badge/USB-JSON%20115200-10B981?style=flat-square)
![Competition](https://img.shields.io/badge/Project-E(x)plory-F59E0B?style=flat-square)

**🇬🇧 English** | [🇵🇱 Polski](README.pl.md)

</div>

---

**ICT-SCAN PRO** is the desktop diagnostic application for an open, low-cost In-Circuit Test (ICT) station built for school electronics labs, student clubs, and small-batch prototyping. Using **Golden Sample signature matching**, it detects assembly faults in ~1 second with safe microcurrents (`< 1 mA`) **before main power is ever applied**.

![ICT-SCAN PRO Preview](podglad.png)

> **Note:** The application UI is in Polish for the local E(x)plory science exhibition.

---

## Project Ecosystem

| Component | Role | Repository / Hardware |
| :--- | :--- | :--- |
| **PC Diagnostics & GUI** | Golden Sample comparison, PCB fault overlay, USB Serial Monitor, pin configurator, CSV export | **This repository** |
| **3D Jig & Pin Map Generator** | Generates 3D-printable pogo-pin cassettes (`.stl`), `wiring_guide.txt`, and `lista_elementow.json` from Gerber/Excellon files | [E-x-plory-2026-PCB-Tester/ict-jig-gen](https://github.com/E-x-plory-2026-PCB-Tester/ict-jig-gen) |
| **Base Hardware & Firmware** | `ESP32` + `2× CD74HC4067` multiplexers wired in parallel to `16` shared pogo-pins (`P75-B1`) | Custom base station |

---

## How It Works

Instead of measuring isolated components (which fails in-circuit due to parallel current paths across the PCB), the tester scans pairs of pogo-pins in **both directions (`a→b` and `b→a`)** via a `3.3 V` voltage divider (`R_ref = 3.3 kΩ`, max short-circuit current `< 1 mA`):

```text
3.3 V ──[ R_ref 3.3 kΩ ]──┬──[ MUX A ]──► Pin A ──[ DUT on PCB ]── Pin B ──[ MUX B ]── GND
                          │
                     ESP32 ADC (mV)
```

1. **Calibrate (`⚙ Kalibruj`):** Measures internal multiplexer + cable resistance (`R_cal`) across a shorted jumper pair and subtracts it like a scale tare.
2. **Record Golden Sample (`★ Zapisz wzorzec`):** Captures the reference signature of one verified working board into `wzorzec.json`.
3. **Test Boards (`▶ Testuj płytkę`):** Compares incoming scans against `wzorzec.json` within a `±10%` tolerance and highlights faults directly on the PCB top-view image.

### Fault Classification

| Status | Condition | Meaning |
| :--- | :--- | :--- |
| `OK` | Within `±10%` tolerance (or matching diode polarity) | Component / net matches Golden Sample |
| `ZWARCIE` / `ZWARCIE LINII` | Resistance dropped `< 15 Ω` (or `< 10%` of reference) | Short circuit / solder bridge (e.g. `VCC–GND` rail) |
| `PRZERWA` | Open circuit (`≥ 3050 mV` ADC ceiling) where reference conducted | Missing component, broken trace, or cold solder joint |
| `ZŁA WARTOŚĆ` | Resistance deviation exceeds `±10%` | Wrong resistor value soldered |
| `ODWRÓCONA` | Bidirectional `a→b / b→a` readings swapped vs reference | Reversed diode / LED polarity |
| `PRZEBICIE` | Reference was open, tested board conducts (`≥ 15 Ω`) | Unintended leakage path between nodes |
| `BLISKO GRANICY` | Deviation between `±5%` and `±10%` | Marginal value near tolerance limit |

---

## Key Features

* **Built-in USB Serial Monitor:** Non-blocking JSON-lines receiver (`115200` baud, `4.5 s` timeout) with live `RX/TX` console, raw JSON toggle, manual command input (`SCAN`, `PING`), and COM port refresh (`↻`).
* **Interactive Pin Mapper (`⚙ Piny`):** Click directly on the PCB image to assign `(x, y)` coordinates, needle indices `0–15`, and element type (`element` / `linia`) into `lista_elementow.json`.
* **Zoom & Pan PCB Viewport:** Mouse-wheel zoom (`55%–200%`), drag-to-pan, resizable split panel, table font scaling (`85%–130%`), and fullscreen table mode (`⛶ Pełny`).
* **Session History & CSV Export:** Clickable history pills for the last 10 scans and automatic semicolon-delimited logging to `pomiary_raport.csv` (Polish Excel compatible).
* **Offline Demo Mode:** Built-in board simulator (`dobra płytka`, `zwarcie`, `zly_rezystor`, `odwrocona_dioda`, `przerwa`) for testing without hardware.

---

## Installation & Running

### Windows / macOS
```bash
pip install -r requirements.txt
python testuj_plytke.py
```
*(Or double-click `URUCHOM_WINDOWS.bat` on Windows).*

### Linux (Fedora / Ubuntu / Debian)
System `Tkinter` and `ImageTk` packages are required before installing Python dependencies:
* **Fedora:** `sudo dnf install python3-tkinter python3-pillow-tk`
* **Ubuntu / Debian:** `sudo apt install python3-tk python3-pil.imagetk`

```bash
pip3 install -r requirements.txt
python3 testuj_plytke.py
```

---

## USB Serial Protocol & Configuration

When `SCAN\n` is sent over USB (`115200` baud), the microcontroller responds with a single JSON line:
```json
{
  "board_id": "test_01",
  "scan_ms": 850,
  "readings": [
    {"a": 0, "b": 1, "mv": 472},
    {"a": 1, "b": 0, "mv": 474}
  ]
}
```

Pin mapping schema (`lista_elementow.json`, also auto-generated by `ict-jig-gen`):
```json
{
  "elementy": [
    {"nazwa": "R1", "piny": [0, 1], "x": 168, "y": 240, "typ": "element"},
    {"nazwa": "VCC-GND", "piny": [0, 15], "x": 256, "y": 452, "typ": "linia"}
  ]
}
```

## Repository Files

| File | Description |
| :--- | :--- |
| `testuj_plytke.py` | Main standalone GUI application (`ICT-SCAN PRO`) |
| `lista_elementow.json` | Demo PCB element-to-pin & pixel coordinate map |
| `zdjecie_plytki.png` | Top-view PCB image for visual fault overlay |
| `requirements.txt` | Python dependencies (`customtkinter`, `pillow`, `pyserial`) |
| `URUCHOM_WINDOWS.bat` / `URUCHOM.sh` | One-click launcher scripts |
| `PRZECZYTAJ.txt` | Quick Polish user guide |

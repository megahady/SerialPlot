
<img width="1202" height="692" alt="image" src="https://github.com/user-attachments/assets/d3ecbc1f-09cb-4e57-bde8-738417676619" />

# Serial Plotter

A real-time multi-channel serial data plotter with a neon dark UI, built with Python, PyQtGraph, and PySerial.  
Compatible with **Windows** and **macOS**.

---

## Features

| Feature | Details |
|---|---|
| **Multi-channel display** | 6 simultaneous channels (CH1–CH6) on one graph |
| **Arduino auto-detection** | COM port combobox tags Arduino devices automatically |
| **Interactive legend** | Click a channel label → rename + change colour. Drag to reposition. |
| **Start / Stop Recording** | Buffers all active channels and saves a timestamped CSV |
| **Demo signal** | 3 synthetic channels (`sin(x)+sin(2x)+noise`, etc.) — no hardware needed |
| **Neon dark theme** | Fully styled UI with neon cyan, pink, and green accents |

---

## Requirements

```bash
pip install pyqtgraph pyserial numpy PyQt5
```

---

## Running

```bash
# Windows
python serial_plotter.py

# macOS
python3 serial_plotter.py
```

---

## Arduino Protocol

The plotter expects packets of up to **244 bytes** terminated by `0xFF 0xFF 0xFF`.

| Byte | Meaning |
|---|---|
| `[0]` | Node ID — `0x31`=CH1, `0x32`=CH2, … `0x36`=CH6 |
| `[1]` | Value to plot (unsigned byte, cast to float) |
| `[2]` | Packet counter |
| `[3..243]` | Additional payload |
| Last 3 | `0xFF 0xFF 0xFF` (terminator) |

> **Customise the value extraction** in `_parse_value()` (near the bottom of the file) to match your specific packet format.

---

## Usage Guide

### 1 — Connecting
1. Plug in your Arduino.
2. Click **Refresh** to scan ports — Arduino devices are labelled `[Arduino]` and sorted first.
3. Select the port and click **Connect**.

### 2 — Demo Signal (no hardware)
Click **Show Demo Signal** to stream 3 synthetic channels instantly.

### 3 — Recording
1. Click **Start Recording** — the buffer counter updates live.
2. Click **Stop & Save** — a `recording_<timestamp>.csv` is written next to the script.
   - Columns: `timestamp, CH1, CH2, CH3, CH4, CH5, CH6`

### 4 — Renaming / Recolouring a Channel
Click the channel's label in the **legend** (drag the legend to move it first if needed).  
A dialog lets you set a new name and pick a colour — both update live.

---

## File Output

| File | Description |
|---|---|
| `recording_<unix_timestamp>.csv` | Recorded channel data, one row per UI tick (~60 fps) |

---

## Project Structure

```
serial_plotter.py   # Main application
README.md           # This file
recording_*.csv     # Auto-generated recording files
```



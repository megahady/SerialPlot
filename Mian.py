"""
serial_plotter.py
Multi-channel serial data plotter with neon UI.
Compatible with Windows and macOS.

Legend interaction:
  - Click any channel in the legend -> dialog to rename + change colour
Channels:
  - CH1-CH6 mapped to Arduino node IDs 0x31-0x36
  - Unified Start/Stop Recording -> timestamped CSV
  - Demo signal: 3 simultaneous synthetic channels
"""
import sys
import os
import platform
import subprocess
import time
import threading
import queue as stdlib_queue
import csv

import numpy as np
import serial
import serial.tools.list_ports
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets

# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------
IS_MAC = platform.system() == "Darwin"
SYS_FONT = "-apple-system, Helvetica Neue, sans-serif" if IS_MAC else "'Segoe UI', sans-serif"

def open_file(path):
    """Open a file with the default application, cross-platform."""
    if IS_MAC:
        subprocess.call(["open", path])
    elif platform.system() == "Windows":
        os.startfile(path)
    else:
        subprocess.call(["xdg-open", path])

# ---------------------------------------------------------------------------
# Neon palette
# ---------------------------------------------------------------------------
BG_DARK   = "#0a0a12"
BG_PANEL  = "#10101e"
NEON_CYAN = "#00ffe7"
NEON_PINK = "#ff2d78"
NEON_GRN  = "#39ff14"
NEON_YLW  = "#ffe600"
TEXT_CLR  = "#c8d8f0"
BORDER    = "#1e2a3a"

CH_DEFAULTS = ["#00ffe7", "#ff2d78", "#39ff14", "#ffe600", "#bf5fff", "#ff8c00"]

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_CLR};
    font-family: {SYS_FONT};
    font-size: 12px;
}}
QLabel  {{ color: {TEXT_CLR}; }}
QDialog {{ background-color: {BG_PANEL}; }}
QLineEdit {{
    background-color: {BG_DARK};
    color: {TEXT_CLR};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 4px;
}}
QComboBox {{
    background-color: {BG_PANEL};
    color: {NEON_CYAN};
    border: 1px solid {NEON_CYAN};
    border-radius: 4px;
    padding: 3px 8px;
    min-width: 230px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    color: {NEON_CYAN};
    selection-background-color: #003344;
}}
QPushButton {{
    background-color: {BG_PANEL};
    color: {NEON_CYAN};
    border: 1px solid {NEON_CYAN};
    border-radius: 4px;
    padding: 4px 12px;
}}
QPushButton:hover   {{ background-color: #003344; color: #ffffff; }}
QPushButton:pressed {{ background-color: #004455; }}
QProgressBar {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
    text-align: center;
    height: 12px;
}}
QProgressBar::chunk {{ background-color: {NEON_CYAN}; border-radius: 2px; }}
"""

# ---------------------------------------------------------------------------
# Clickable pyqtgraph LegendItem
# ---------------------------------------------------------------------------
class ClickableLegend(pg.LegendItem):
    """
    Draggable LegendItem that opens a channel dialog on click.
    Uses pyqtgraph's own event system:
      - mouseDragEvent  -> move the legend (handled by base class)
      - mouseClickEvent -> open channel settings dialog
    """
    sigItemClicked = QtCore.Signal(int)

    def mouseClickEvent(self, event):
        """Fires only on a genuine click (pyqtgraph will NOT call this during a drag)."""
        pos = event.pos()
        for i, (sample, label) in enumerate(self.items):
            sr = sample.mapRectToParent(sample.boundingRect())
            lr = label.mapRectToParent(label.boundingRect())
            if sr.united(lr).contains(pos):
                self.sigItemClicked.emit(i)
                event.accept()
                return
        event.ignore()

    def mouseDragEvent(self, event):
        """Let the base class move the legend freely."""
        super().mouseDragEvent(event)


# ---------------------------------------------------------------------------
# Channel settings dialog
# ---------------------------------------------------------------------------
class ChannelDialog(QtWidgets.QDialog):
    """Dialog to rename a channel and pick its colour."""
    def __init__(self, ch_index, current_name, current_color, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Channel {ch_index+1} Settings")
        self.setFixedWidth(320)
        self.chosen_color = current_color

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(12)

        # Name
        lay.addWidget(QtWidgets.QLabel("Channel name:"))
        self.name_edit = QtWidgets.QLineEdit(current_name)
        lay.addWidget(self.name_edit)

        # Colour preview + picker
        color_row = QtWidgets.QHBoxLayout()
        self.color_preview = QtWidgets.QPushButton()
        self.color_preview.setFixedSize(32, 32)
        self._update_preview(current_color)
        self.color_preview.clicked.connect(self._pick_color)

        lbl = QtWidgets.QLabel("Curve colour")
        lbl.setStyleSheet(f"color:{TEXT_CLR};")
        color_row.addWidget(lbl)
        color_row.addStretch()
        color_row.addWidget(self.color_preview)
        lay.addLayout(color_row)

        # Buttons
        btn_row = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_row.accepted.connect(self.accept)
        btn_row.rejected.connect(self.reject)
        lay.addWidget(btn_row)

    def _update_preview(self, hex_color):
        self.chosen_color = hex_color
        self.color_preview.setStyleSheet(
            f"background:{hex_color}; border:2px solid {BORDER}; border-radius:4px;")

    def _pick_color(self):
        color = QtWidgets.QColorDialog.getColor(
            initial=QtGui.QColor(self.chosen_color), parent=self)
        if color.isValid():
            self._update_preview(color.name())

    @property
    def channel_name(self):
        return self.name_edit.text().strip() or f"CH{self.parent_index+1}"

# ---------------------------------------------------------------------------
# Channel state
# ---------------------------------------------------------------------------
WINDOW_W  = 500
NUM_CH    = 6
NODE_IDS  = ["31", "32", "33", "34", "35", "36"]

ch_queues = [stdlib_queue.Queue(maxsize=5000) for _ in range(NUM_CH)]
ch_vals   = [np.zeros(WINDOW_W) for _ in range(NUM_CH)]
ch_ptrs   = [-WINDOW_W] * NUM_CH
ch_colors = list(CH_DEFAULTS)
ch_names  = [f"CH{i+1}" for i in range(NUM_CH)]

_rec_rows = []
_rec_lock = threading.Lock()

ser         = None
running     = False
recording   = False
start_time  = None
_acq_thread = None

# ---------------------------------------------------------------------------
# App + window
# ---------------------------------------------------------------------------
app = pg.mkQApp()
app.setStyleSheet(STYLESHEET)

mw = QtWidgets.QMainWindow()
mw.setWindowTitle("Serial Plotter")
mw.resize(1200, 660)

cw = QtWidgets.QWidget()
mw.setCentralWidget(cw)
root_layout = QtWidgets.QVBoxLayout(cw)
root_layout.setContentsMargins(0, 0, 0, 0)
root_layout.setSpacing(0)

# ---------------------------------------------------------------------------
# Toolbar helpers
# ---------------------------------------------------------------------------
def _toolbar(height=48):
    frame = QtWidgets.QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background-color:{BG_PANEL}; border-bottom:1px solid {BORDER}; }}")
    frame.setFixedHeight(height)
    lay = QtWidgets.QHBoxLayout(frame)
    lay.setContentsMargins(10, 4, 10, 4)
    lay.setSpacing(8)
    return frame, lay

# ---------------------------------------------------------------------------
# Toolbar 1 – COM port
# ---------------------------------------------------------------------------
tb1_frame, tb1 = _toolbar()

lbl_port    = QtWidgets.QLabel("COM Port:")
lbl_port.setStyleSheet(f"color:{TEXT_CLR}; font-weight:bold;")
combo_port  = QtWidgets.QComboBox()
btn_refresh = QtWidgets.QPushButton("Refresh")
btn_connect = QtWidgets.QPushButton("Connect")
lbl_status  = QtWidgets.QLabel("  DISCONNECTED")
lbl_status.setStyleSheet(f"color:{NEON_PINK}; font-weight:bold; letter-spacing:1px;")

for w in [lbl_port, combo_port, btn_refresh, btn_connect]:
    tb1.addWidget(w)
tb1.addSpacing(16)
tb1.addWidget(lbl_status)
tb1.addStretch()
root_layout.addWidget(tb1_frame)

# ---------------------------------------------------------------------------
# Toolbar 2 – Recording + Demo
# ---------------------------------------------------------------------------
tb2_frame, tb2 = _toolbar()

btn_rec_start = QtWidgets.QPushButton("  Start Recording")
btn_rec_start.setStyleSheet(f"color:{NEON_YLW}; border:1px solid {NEON_YLW};")
btn_rec_stop  = QtWidgets.QPushButton("  Stop & Save")
btn_rec_stop.setStyleSheet(f"color:{NEON_PINK}; border:1px solid {NEON_PINK};")
btn_rec_stop.setEnabled(False)

btn_demo = QtWidgets.QPushButton("Show Demo Signal")
btn_demo.setStyleSheet(f"color:{NEON_GRN}; border:1px solid {NEON_GRN};")

lbl_buf  = QtWidgets.QLabel("Buffer: 0 rows")
bar_buf  = QtWidgets.QProgressBar()
bar_buf.setRange(0, 5000)
bar_buf.setValue(0)
bar_buf.setFixedWidth(140)
bar_buf.setTextVisible(False)

lbl_hint = QtWidgets.QLabel("  Click a legend label to rename / recolour")
lbl_hint.setStyleSheet(f"color:#3a4a5a; font-style:italic;")

lbl_rec_state = QtWidgets.QLabel("")
lbl_rec_state.setStyleSheet(f"color:{NEON_YLW}; font-weight:bold; letter-spacing:1px;")

for w in [btn_rec_start, btn_rec_stop, btn_demo]:
    tb2.addWidget(w)
tb2.addSpacing(20)
tb2.addWidget(lbl_buf)
tb2.addWidget(bar_buf)
tb2.addSpacing(8)
tb2.addWidget(lbl_rec_state)
tb2.addSpacing(16)
tb2.addWidget(lbl_hint)
tb2.addStretch()
root_layout.addWidget(tb2_frame)

# ---------------------------------------------------------------------------
# Plot + clickable legend
# ---------------------------------------------------------------------------
pg.setConfigOption('background', BG_DARK)
pg.setConfigOption('foreground', TEXT_CLR)

pw = pg.PlotWidget()
pw.setLabel('left',   'Value')
pw.setLabel('bottom', 'Samples')
pw.showGrid(x=True, y=True, alpha=0.15)
pw.getAxis('left').setPen(pg.mkPen(color=BORDER))
pw.getAxis('bottom').setPen(pg.mkPen(color=BORDER))

# Attach our custom legend
legend = ClickableLegend(offset=(10, 10))
legend.setParentItem(pw.plotItem)

ch_curves = []
for i in range(NUM_CH):
    c = pw.plot(pen=pg.mkPen(color=ch_colors[i], width=2))
    legend.addItem(c, ch_names[i])
    ch_curves.append(c)

root_layout.addWidget(pw, stretch=1)
mw.show()

# ---------------------------------------------------------------------------
# Legend click -> channel settings dialog
# ---------------------------------------------------------------------------
def on_legend_clicked(ch_idx):
    dlg = ChannelDialog(ch_idx, ch_names[ch_idx], ch_colors[ch_idx], parent=mw)
    if dlg.exec_() != QtWidgets.QDialog.Accepted:
        return

    new_name  = dlg.name_edit.text().strip() or ch_names[ch_idx]
    new_color = dlg.chosen_color

    # Apply colour
    ch_colors[ch_idx] = new_color
    ch_curves[ch_idx].setPen(pg.mkPen(color=new_color, width=2))

    # Apply name – rebuild legend entry
    ch_names[ch_idx] = new_name
    legend.removeItem(ch_curves[ch_idx])
    legend.addItem(ch_curves[ch_idx], new_name)

    # Re-order legend rows to match original channel order
    # (addItem appends; resort by channel index)
    _refresh_legend()

def _refresh_legend():
    """Rebuild the legend in channel order after a rename."""
    for c in ch_curves:
        legend.removeItem(c)
    for i, c in enumerate(ch_curves):
        legend.addItem(c, ch_names[i])

legend.sigItemClicked.connect(on_legend_clicked)

# ---------------------------------------------------------------------------
# COM port scan (cross-platform)
# ---------------------------------------------------------------------------
ARDUINO_KEYWORDS = ("arduino", "ch340", "ch341", "cp210", "ftdi",
                    "uno", "mega", "nano", "leonardo")

def scan_ports():
    ports = []
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        mfr  = (p.manufacturer or "").lower()
        tag  = " [Arduino]" if any(
            k in desc or k in mfr for k in ARDUINO_KEYWORDS) else ""
        ports.append((f"{p.device} -- {p.description}{tag}",
                      p.device, bool(tag)))
    return ports

def populate_combo():
    combo_port.clear()
    ports = scan_ports()
    if not ports:
        combo_port.addItem("No ports found", userData=None)
        btn_connect.setEnabled(False)
        return
    btn_connect.setEnabled(True)
    for lbl, dev, is_ard in sorted(ports, key=lambda x: not x[2]):
        combo_port.addItem(lbl, userData=dev)

populate_combo()

# ---------------------------------------------------------------------------
# Serial acquisition thread
# ---------------------------------------------------------------------------
baudrate = 921600

def _parse_value(raw):
    return float(raw[1]) if len(raw) > 1 else 0.0

def _serial_worker():
    while running:
        try:
            raw = ser.read_until(expected=b"\xff\xff\xff", size=244)
            if not raw:
                continue
            node_id = raw[0:1].hex()
            if node_id in NODE_IDS:
                idx = NODE_IDS.index(node_id)
                value = _parse_value(raw)
                try:
                    ch_queues[idx].put_nowait(value)
                except stdlib_queue.Full:
                    pass
        except Exception:
            break

# ---------------------------------------------------------------------------
# Connect / Disconnect
# ---------------------------------------------------------------------------
def on_connect():
    global ser, running, start_time, _acq_thread
    port_dev = combo_port.currentData()
    if not port_dev:
        QtWidgets.QMessageBox.warning(mw, "No Port", "Select a COM port.")
        return
    try:
        ser = serial.Serial(port_dev, baudrate, timeout=None)
        ser.flushInput()
    except serial.SerialException as e:
        QtWidgets.QMessageBox.critical(mw, "Connection Error", str(e))
        return

    running    = True
    start_time = time.time()
    _acq_thread = threading.Thread(target=_serial_worker, daemon=True)
    _acq_thread.start()

    lbl_status.setText(f"  CONNECTED  {port_dev}")
    lbl_status.setStyleSheet(f"color:{NEON_GRN}; font-weight:bold; letter-spacing:1px;")
    btn_connect.setText("Disconnect")
    btn_connect.setStyleSheet(f"color:{NEON_PINK}; border:1px solid {NEON_PINK};")
    btn_connect.clicked.disconnect()
    btn_connect.clicked.connect(on_disconnect)
    combo_port.setEnabled(False)
    btn_refresh.setEnabled(False)
    btn_rec_start.setEnabled(True)

def on_disconnect():
    global ser, running, recording
    running = recording = False
    if ser and ser.is_open:
        ser.close()
    ser = None
    lbl_status.setText("  DISCONNECTED")
    lbl_status.setStyleSheet(f"color:{NEON_PINK}; font-weight:bold; letter-spacing:1px;")
    btn_connect.setText("Connect")
    btn_connect.setStyleSheet("")
    btn_connect.clicked.disconnect()
    btn_connect.clicked.connect(on_connect)
    combo_port.setEnabled(True)
    btn_refresh.setEnabled(True)
    btn_rec_start.setEnabled(False)
    btn_rec_stop.setEnabled(False)
    lbl_rec_state.setText("")
    if start_time:
        print(f"Session: {time.time()-start_time:.2f}s")

btn_refresh.clicked.connect(lambda: populate_combo())
btn_connect.clicked.connect(on_connect)

# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def on_rec_start():
    global recording
    with _rec_lock:
        _rec_rows.clear()
    recording = True
    lbl_rec_state.setText("  REC")
    lbl_rec_state.setStyleSheet(f"color:{NEON_YLW}; font-weight:bold; letter-spacing:2px;")
    btn_rec_start.setEnabled(False)
    btn_rec_stop.setEnabled(True)

def on_rec_stop():
    global recording
    recording = False
    with _rec_lock:
        data = list(_rec_rows)
    if not data:
        QtWidgets.QMessageBox.information(mw, "Recording", "No data recorded.")
        _reset_rec_ui()
        return
    save_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"recording_{int(time.time())}.csv")
    with open(save_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp"] + ch_names)
        w.writerows(data)
    reply = QtWidgets.QMessageBox.information(
        mw, "Saved",
        f"Recorded {len(data)} rows.\nSaved to:\n{save_path}",
        QtWidgets.QMessageBox.Open | QtWidgets.QMessageBox.Ok,
        QtWidgets.QMessageBox.Ok)
    if reply == QtWidgets.QMessageBox.Open:
        open_file(save_path)
    _reset_rec_ui()

def _reset_rec_ui():
    lbl_rec_state.setText("")
    btn_rec_start.setEnabled(True)
    btn_rec_stop.setEnabled(False)

btn_rec_start.clicked.connect(on_rec_start)
btn_rec_stop.clicked.connect(on_rec_stop)
btn_rec_start.setEnabled(False)

# ---------------------------------------------------------------------------
# Demo signal  (3 channels)
# ---------------------------------------------------------------------------
_demo_phase  = 0.0
_demo_timer  = QtCore.QTimer()
_demo_active = False

DEMO_FN = [
    lambda x: np.sin(x) + np.sin(2*x) + 0.1*np.random.randn(),
    lambda x: np.sin(0.5*x) + 0.3*np.random.randn(),
    lambda x: np.cos(x)*0.7 + np.sin(3*x)*0.4 + 0.1*np.random.randn(),
]

def _demo_tick():
    global _demo_phase
    x = _demo_phase
    _demo_phase += 0.08
    for idx, fn in enumerate(DEMO_FN):
        try:
            ch_queues[idx].put_nowait(float(fn(x)))
        except stdlib_queue.Full:
            pass

_demo_timer.timeout.connect(_demo_tick)

def on_demo_toggle():
    global _demo_active
    if not _demo_active:
        _demo_active = True
        _demo_timer.start(20)
        btn_demo.setText("Stop Demo")
        btn_demo.setStyleSheet(f"color:{NEON_PINK}; border:1px solid {NEON_PINK};")
        btn_rec_start.setEnabled(True)
    else:
        _demo_active = False
        _demo_timer.stop()
        btn_demo.setText("Show Demo Signal")
        btn_demo.setStyleSheet(f"color:{NEON_GRN}; border:1px solid {NEON_GRN};")
        if not running:
            btn_rec_start.setEnabled(False)

btn_demo.clicked.connect(on_demo_toggle)

# ---------------------------------------------------------------------------
# Update loop (~60 fps)
# ---------------------------------------------------------------------------
def update_loop():
    current_vals = [None] * NUM_CH
    for idx in range(NUM_CH):
        last = None
        try:
            while True:
                last = ch_queues[idx].get_nowait()
        except stdlib_queue.Empty:
            pass
        if last is not None:
            ch_vals[idx][:-1] = ch_vals[idx][1:]
            ch_vals[idx][-1]  = last
            ch_ptrs[idx]     += 1
            ch_curves[idx].setData(ch_vals[idx])
            ch_curves[idx].setPos(ch_ptrs[idx] - WINDOW_W, 0)
            current_vals[idx] = last

    if recording and any(v is not None for v in current_vals):
        row = [time.time()] + [(v if v is not None else "") for v in current_vals]
        with _rec_lock:
            _rec_rows.append(row)

    n = len(_rec_rows)
    lbl_buf.setText(f"Buffer: {n} rows")
    bar_buf.setValue(min(n, 5000))

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # macOS: set process start method for multiprocessing safety
    if IS_MAC:
        import multiprocessing
        multiprocessing.set_start_method("spawn", force=True)

    timer = QtCore.QTimer()
    timer.timeout.connect(update_loop)
    timer.start(16)
    pg.exec()

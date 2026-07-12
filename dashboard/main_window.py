import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QProgressBar, QPlainTextEdit, QGroupBox, QFrame,
    QTabWidget,
)

from data_engine import config, storage
from data_engine.paths import DATA_DIR, disk_usage_bytes, SESSION_FILE, ensure_folders
from dashboard.worker import DownloadWorker
from dashboard.settings_dialog import SettingsDialog
from dashboard.backtest_tab import BacktestingTab

_BYTES_UNITS = ["B", "KB", "MB", "GB", "TB"]


def _human_bytes(n):
    size = float(n)
    for unit in _BYTES_UNITS:
        if size < 1024 or unit == _BYTES_UNITS[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SINDHU - Trading System")
        self.resize(880, 640)

        self.worker = None
        self.session_id = None
        self.session_started_at = None

        self._build_ui()
        self._refresh_static_fields()

        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self._refresh_stats)
        self.stats_timer.start(5000)
        self._refresh_stats()

    # ---------------------------------------------------------- UI setup
    def _build_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        data_engine_tab = QWidget()
        root = QVBoxLayout(data_engine_tab)

        title = QLabel("SINDHU")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        status_box = QGroupBox("Status")
        grid = QGridLayout(status_box)
        self.fields = {}
        field_names = [
            "Company Status", "Current Process", "Current Exchange",
            "Current Coin", "Current Timeframe", "Download Progress",
            "Downloaded Candles", "Database Status", "Project Status",
            "Disk Usage", "Current Session",
        ]
        for i, name in enumerate(field_names):
            row, col = divmod(i, 2)
            grid.addWidget(QLabel(f"{name}:"), row, col * 2)
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            self.fields[name] = value_label
            grid.addWidget(value_label, row, col * 2 + 1)
        root.addWidget(status_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        buttons = QHBoxLayout()
        self.btn_start = QPushButton("▶ START SINDHU")
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_resume = QPushButton("▶ Resume")
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_settings = QPushButton("⚙ Settings")
        self.btn_open_folder = QPushButton("\U0001F4C2 Open Data Folder")
        self.btn_dashboard = QPushButton("\U0001F4CA Dashboard")

        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop,
                  self.btn_settings, self.btn_open_folder, self.btn_dashboard):
            buttons.addWidget(b)
        root.addLayout(buttons)

        self.btn_start.clicked.connect(self.on_start)
        self.btn_pause.clicked.connect(self.on_pause)
        self.btn_resume.clicked.connect(self.on_resume)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_settings.clicked.connect(self.on_settings)
        self.btn_open_folder.clicked.connect(self.on_open_folder)
        self.btn_dashboard.clicked.connect(self.on_dashboard)

        self._set_running_state(False)

        log_box = QGroupBox("Latest Logs")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setStyleSheet("font-family: Consolas, monospace;")
        log_layout.addWidget(self.log_view)
        root.addWidget(log_box, stretch=1)

        tabs.addTab(data_engine_tab, "Data Engine")

        self.backtest_tab = BacktestingTab()
        tabs.addTab(self.backtest_tab, "Backtesting")

    def _set_running_state(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(running)
        self.btn_stop.setEnabled(running)

    def _refresh_static_fields(self):
        self.fields["Project Status"].setText("Phase 1 - Data System")
        self.fields["Company Status"].setText("Idle")
        self.fields["Current Process"].setText("-")
        self.fields["Current Exchange"].setText("-")
        self.fields["Current Coin"].setText("-")
        self.fields["Current Timeframe"].setText(config.BASE_INTERVAL)
        self.fields["Download Progress"].setText("0 / 0")
        self.fields["Current Session"].setText("-")

    def _refresh_stats(self):
        ensure_folders()
        try:
            total_candles = storage.count_all_rows()
        except Exception:
            total_candles = 0
        self.fields["Downloaded Candles"].setText(f"{total_candles:,}")

        db_size = _human_bytes(storage.db_file_size_bytes())
        self.fields["Database Status"].setText(f"Connected ({db_size})")

        self.fields["Disk Usage"].setText(_human_bytes(disk_usage_bytes()))

    # ---------------------------------------------------------- session log
    def _record_session(self, event):
        ensure_folders()
        entry = {
            "session_id": self.session_id,
            "event": event,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        with open(SESSION_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ---------------------------------------------------------- button handlers
    def on_start(self):
        if self.worker is not None and self.worker.isRunning():
            return

        exchanges_cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
        coins_cfg = config.load_or_seed("coins.json", config.DEFAULTS["coins.json"])
        exchange_id = exchanges_cfg["default"]
        num_coins = coins_cfg["num_coins"]
        quote_asset = coins_cfg["quote_asset"]

        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_started_at = datetime.now(timezone.utc)
        self._record_session("started")

        self.fields["Current Session"].setText(self.session_id)
        self.fields["Current Exchange"].setText(exchange_id)
        self.fields["Current Timeframe"].setText(config.BASE_INTERVAL)
        self.log_view.clear()

        self.worker = DownloadWorker(exchange_id, num_coins, quote_asset)
        self.worker.log_line.connect(self._on_log_line)
        self.worker.status_changed.connect(self._on_status_changed)
        self.worker.process_changed.connect(self._on_process_changed)
        self.worker.coin_changed.connect(self._on_coin_changed)
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.finished_run.connect(self._on_finished)
        self.worker.start()

        self._set_running_state(True)

    def on_pause(self):
        if self.worker:
            self.worker.control.pause()
            self.fields["Company Status"].setText("Paused")

    def on_resume(self):
        if self.worker:
            self.worker.control.resume()
            self.fields["Company Status"].setText("Downloading")

    def on_stop(self):
        if self.worker:
            self.worker.control.stop()
            self._record_session("stopped")

    def on_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def on_open_folder(self):
        ensure_folders()
        if sys.platform == "win32":
            os.startfile(DATA_DIR)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", DATA_DIR])
        else:
            subprocess.Popen(["xdg-open", DATA_DIR])

    def on_dashboard(self):
        self.raise_()
        self.activateWindow()

    # ---------------------------------------------------------- worker signal slots
    def _on_log_line(self, line):
        self.log_view.appendPlainText(line)

    def _on_status_changed(self, status):
        self.fields["Company Status"].setText(status)

    def _on_process_changed(self, process):
        self.fields["Current Process"].setText(process)

    def _on_coin_changed(self, symbol):
        self.fields["Current Coin"].setText(symbol)

    def _on_progress_changed(self, index, total):
        self.fields["Download Progress"].setText(f"{index} / {total}")
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index)

    def _on_finished(self):
        self._set_running_state(False)
        self._record_session("finished")
        self._refresh_stats()

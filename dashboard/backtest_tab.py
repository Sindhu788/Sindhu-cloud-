import json
import os
import time
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QProgressBar, QPlainTextEdit, QGroupBox,
    QComboBox, QListWidget, QListWidgetItem, QCheckBox, QDoubleSpinBox,
    QDateEdit, QSplitter, QTabWidget,
)

from data_engine import config, storage
from data_engine.paths import SETTINGS_DIR, REPORTS_DIR, ensure_folders
from backtest_engine.strategy_loader import discover_strategies
from dashboard.backtest_worker import BacktestWorker

_LAST_BATCH_FILE = os.path.join(SETTINGS_DIR, "last_backtest_batch.json")


def _load_last_batch_id():
    if os.path.exists(_LAST_BATCH_FILE):
        try:
            with open(_LAST_BATCH_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("batch_id")
        except (OSError, ValueError):
            return None
    return None


def _save_last_batch_id(batch_id):
    ensure_folders()
    with open(_LAST_BATCH_FILE, "w", encoding="utf-8") as f:
        json.dump({"batch_id": batch_id}, f)


class QuickBacktestTab(QWidget):
    """The original Phase 2 single-timeframe backtest UI, unchanged --
    sweeps a plain Strategy subclass from strategies/*.py across many
    coins x timeframes. Kept exactly as-is; the 2.1 professional features
    (multi-timeframe strategy builder, library, trade replay, rankings,
    queue) are added as sibling tabs in BacktestingTab below, not a
    replacement of this one."""

    def __init__(self):
        super().__init__()
        self.worker = None
        self.batch_start_time = None
        self._build_ui()
        self._reload_strategies()
        self._reload_symbols()

    # ---------------------------------------------------------- UI setup
    def _build_ui(self):
        root = QHBoxLayout(self)

        # ---- left: settings panel ----
        settings_panel = QVBoxLayout()

        form = QFormLayout()
        self.strategy_combo = QComboBox()
        refresh_row = QHBoxLayout()
        refresh_row.addWidget(self.strategy_combo, stretch=1)
        self.btn_refresh_strategies = QPushButton("↻")
        self.btn_refresh_strategies.setFixedWidth(28)
        self.btn_refresh_strategies.clicked.connect(self._reload_strategies)
        refresh_row.addWidget(self.btn_refresh_strategies)
        form.addRow("Strategy:", refresh_row)

        self.initial_balance_spin = QDoubleSpinBox()
        self.initial_balance_spin.setRange(1, 100_000_000)
        self.initial_balance_spin.setValue(1000)
        form.addRow("Initial Balance:", self.initial_balance_spin)

        self.risk_pct_spin = QDoubleSpinBox()
        self.risk_pct_spin.setRange(0.01, 100)
        self.risk_pct_spin.setValue(1.0)
        self.risk_pct_spin.setSuffix(" %")
        form.addRow("Risk %:", self.risk_pct_spin)

        self.commission_spin = QDoubleSpinBox()
        self.commission_spin.setRange(0, 10)
        self.commission_spin.setDecimals(3)
        self.commission_spin.setValue(0.1)
        self.commission_spin.setSuffix(" %")
        form.addRow("Commission:", self.commission_spin)

        self.slippage_spin = QDoubleSpinBox()
        self.slippage_spin.setRange(0, 10)
        self.slippage_spin.setDecimals(3)
        self.slippage_spin.setValue(0.05)
        self.slippage_spin.setSuffix(" %")
        form.addRow("Slippage:", self.slippage_spin)

        self.position_size_spin = QDoubleSpinBox()
        self.position_size_spin.setRange(0.1, 100)
        self.position_size_spin.setValue(10.0)
        self.position_size_spin.setSuffix(" %")
        form.addRow("Position Size:", self.position_size_spin)

        settings_panel.addLayout(form)

        self.use_full_history = QCheckBox("Use full downloaded history")
        self.use_full_history.setChecked(True)
        self.use_full_history.toggled.connect(self._on_full_history_toggled)
        settings_panel.addWidget(self.use_full_history)

        date_row = QHBoxLayout()
        self.start_date_edit = QDateEdit(QDate.currentDate().addYears(-1))
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setEnabled(False)
        self.end_date_edit = QDateEdit(QDate.currentDate())
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setEnabled(False)
        date_row.addWidget(QLabel("From:"))
        date_row.addWidget(self.start_date_edit)
        date_row.addWidget(QLabel("To:"))
        date_row.addWidget(self.end_date_edit)
        settings_panel.addLayout(date_row)

        coins_box = QGroupBox("Coins (~50)")
        coins_layout = QVBoxLayout(coins_box)
        self.coins_list = QListWidget()
        coins_layout.addWidget(self.coins_list)
        settings_panel.addWidget(coins_box, stretch=1)

        tf_box = QGroupBox("Timeframes")
        tf_grid = QGridLayout(tf_box)
        self.tf_checks = {}
        for i, tf in enumerate(config.SUPPORTED_INTERVALS):
            cb = QCheckBox(tf)
            cb.setChecked(True)
            self.tf_checks[tf] = cb
            tf_grid.addWidget(cb, i // 3, i % 3)
        settings_panel.addWidget(tf_box)

        buttons = QHBoxLayout()
        self.btn_start = QPushButton("▶ Start Backtest")
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_resume = QPushButton("▶ Resume")
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_open_reports = QPushButton("\U0001F4C2 Open Reports Folder")
        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop, self.btn_open_reports):
            buttons.addWidget(b)
        settings_panel.addLayout(buttons)

        self.btn_start.clicked.connect(self.on_start)
        self.btn_pause.clicked.connect(self.on_pause)
        self.btn_resume.clicked.connect(self.on_resume)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_open_reports.clicked.connect(self.on_open_reports)
        self._set_running_state(False)

        left_widget = QWidget()
        left_widget.setLayout(settings_panel)

        # ---- right: live status + log ----
        right_panel = QVBoxLayout()

        status_box = QGroupBox("Backtest Status")
        grid = QGridLayout(status_box)
        self.fields = {}
        field_names = [
            "Current Coin", "Current Timeframe", "Current Strategy",
            "Completed Tests", "Remaining Tests", "Current Trade",
            "Total Trades", "Winning Trades", "Losing Trades",
            "Win Rate", "Profit", "Drawdown", "Estimated Time Remaining",
        ]
        for i, name in enumerate(field_names):
            row, col = divmod(i, 2)
            grid.addWidget(QLabel(f"{name}:"), row, col * 2)
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            self.fields[name] = value_label
            grid.addWidget(value_label, row, col * 2 + 1)
        right_panel.addWidget(status_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        right_panel.addWidget(self.progress_bar)

        log_box = QGroupBox("Latest Logs")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setStyleSheet("font-family: Consolas, monospace;")
        log_layout.addWidget(self.log_view)
        right_panel.addWidget(log_box, stretch=1)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def _set_running_state(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(running)
        self.btn_stop.setEnabled(running)

    def _on_full_history_toggled(self, checked):
        self.start_date_edit.setEnabled(not checked)
        self.end_date_edit.setEnabled(not checked)

    # ---------------------------------------------------------- data loading
    def _reload_strategies(self):
        self.strategy_combo.clear()
        strategies = discover_strategies()
        if not strategies:
            self.strategy_combo.addItem("(no strategies found in strategies/)")
            self.strategy_combo.setEnabled(False)
        else:
            self.strategy_combo.setEnabled(True)
            for name in sorted(strategies):
                self.strategy_combo.addItem(name)
        self._strategies = strategies

    def _reload_symbols(self):
        exchanges_cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
        self.exchange_id = exchanges_cfg["default"]
        symbols = storage.load_symbols(self.exchange_id)
        self.coins_list.clear()
        for s in symbols:
            item = QListWidgetItem(s)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.coins_list.addItem(item)

    # ---------------------------------------------------------- button handlers
    def on_start(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if not self._strategies:
            self.log_view.appendPlainText("No strategy available. Add one under strategies/ first.")
            return

        strategy_name = self.strategy_combo.currentText()
        strategy_class = self._strategies[strategy_name]

        symbols = [
            self.coins_list.item(i).text()
            for i in range(self.coins_list.count())
            if self.coins_list.item(i).checkState() == Qt.Checked
        ]
        timeframes = [tf for tf, cb in self.tf_checks.items() if cb.isChecked()]

        if not symbols or not timeframes:
            self.log_view.appendPlainText("Select at least one coin and one timeframe.")
            return

        if self.use_full_history.isChecked():
            start_ms, end_ms = None, None
        else:
            start_ms = int(datetime(
                self.start_date_edit.date().year(), self.start_date_edit.date().month(),
                self.start_date_edit.date().day(), tzinfo=timezone.utc,
            ).timestamp() * 1000)
            end_ms = int(datetime(
                self.end_date_edit.date().year(), self.end_date_edit.date().month(),
                self.end_date_edit.date().day(), 23, 59, 59, tzinfo=timezone.utc,
            ).timestamp() * 1000)

        settings = {
            "symbols": symbols,
            "timeframes": timeframes,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "initial_balance": self.initial_balance_spin.value(),
            "risk_pct": self.risk_pct_spin.value(),
            "commission_pct": self.commission_spin.value(),
            "slippage_pct": self.slippage_spin.value(),
            "position_size_pct": self.position_size_spin.value(),
        }

        resume_batch_id = None
        last_id = _load_last_batch_id()
        if last_id:
            existing = storage.get_batch(last_id)
            if existing and existing["status"] not in ("completed",) and existing["strategy_name"] == strategy_name:
                resume_batch_id = last_id
                settings = existing["settings"]

        self.log_view.clear()
        self.fields["Current Strategy"].setText(strategy_name)
        self.batch_start_time = time.time()

        self.worker = BacktestWorker(strategy_class, self.exchange_id, settings, batch_id=resume_batch_id)
        self.worker.log_line.connect(self._on_log_line)
        self.worker.coin_changed.connect(lambda s: self.fields["Current Coin"].setText(s))
        self.worker.timeframe_changed.connect(lambda tf: self.fields["Current Timeframe"].setText(tf))
        self.worker.tests_progress.connect(self._on_tests_progress)
        self.worker.trade_update.connect(self._on_trade_update)
        self.worker.finished_run.connect(self._on_finished)
        self.worker.start()

        self._set_running_state(True)

    def on_pause(self):
        if self.worker:
            self.worker.control.pause()

    def on_resume(self):
        if self.worker:
            self.worker.control.resume()

    def on_stop(self):
        if self.worker:
            self.worker.control.stop()

    def on_open_reports(self):
        ensure_folders()
        import sys
        import subprocess
        if sys.platform == "win32":
            os.startfile(REPORTS_DIR)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", REPORTS_DIR])
        else:
            subprocess.Popen(["xdg-open", REPORTS_DIR])

    # ---------------------------------------------------------- worker signal slots
    def _on_log_line(self, line):
        self.log_view.appendPlainText(line)

    def _on_tests_progress(self, done, total):
        self.fields["Completed Tests"].setText(str(done))
        self.fields["Remaining Tests"].setText(str(total - done))
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)

        if done > 0 and self.batch_start_time:
            elapsed = time.time() - self.batch_start_time
            remaining = total - done
            eta_seconds = (elapsed / done) * remaining
            self.fields["Estimated Time Remaining"].setText(_format_duration(eta_seconds))
        else:
            self.fields["Estimated Time Remaining"].setText("-")

    def _on_trade_update(self, stats):
        self.fields["Current Trade"].setText(stats["current_trade"])
        self.fields["Total Trades"].setText(str(stats["total_trades"]))
        self.fields["Winning Trades"].setText(str(stats["wins"]))
        self.fields["Losing Trades"].setText(str(stats["losses"]))
        self.fields["Win Rate"].setText(f"{stats['win_rate']:.2f}%")
        self.fields["Profit"].setText(f"{stats['profit_pct']:.2f}%")
        self.fields["Drawdown"].setText(f"{stats['drawdown_pct']:.2f}%")

    def _on_finished(self, batch_id):
        self._set_running_state(False)
        if batch_id:
            batch = storage.get_batch(batch_id)
            if batch and batch["status"] == "completed":
                if os.path.exists(_LAST_BATCH_FILE):
                    os.remove(_LAST_BATCH_FILE)
            else:
                _save_last_batch_id(batch_id)
            self.log_view.appendPlainText(f"Report saved: data/reports/{batch_id}/report.txt")


def _format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


class BacktestingTab(QTabWidget):
    """The Backtesting page. Quick Backtest is the original Phase 2 UI,
    untouched; the other tabs are the 2.1 professional additions (bilingual
    multi-timeframe strategy builder, strategy library, trade history +
    replay, rankings/export/queue)."""

    def __init__(self):
        super().__init__()
        from dashboard.strategy_builder_tab import StrategyBuilderTab
        from dashboard.strategy_library_tab import StrategyLibraryTab
        from dashboard.trade_history_tab import TradeHistoryTab
        from dashboard.rankings_tab import RankingsTab

        self.quick_backtest_tab = QuickBacktestTab()
        self.strategy_builder_tab = StrategyBuilderTab()
        self.strategy_library_tab = StrategyLibraryTab(on_load=self.strategy_builder_tab.load_from_library)
        self.trade_history_tab = TradeHistoryTab()
        self.rankings_tab = RankingsTab()

        self.addTab(self.quick_backtest_tab, "Quick Backtest")
        self.addTab(self.strategy_builder_tab, "Strategy Builder")
        self.addTab(self.strategy_library_tab, "Strategy Library")
        self.addTab(self.trade_history_tab, "Trade History")
        self.addTab(self.rankings_tab, "Rankings && Queue")

        self.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index):
        widget = self.widget(index)
        if widget is self.strategy_library_tab:
            self.strategy_library_tab.refresh()
        elif widget is self.trade_history_tab:
            self.trade_history_tab.refresh_batches()
        elif widget is self.rankings_tab:
            self.rankings_tab.refresh_batches()
            self.rankings_tab._reload_library()

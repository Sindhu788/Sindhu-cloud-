import time
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QProgressBar, QPlainTextEdit, QGroupBox,
    QLineEdit, QListWidget, QListWidgetItem, QCheckBox, QDoubleSpinBox,
    QDateEdit, QSplitter, QMessageBox,
)

from data_engine import config, storage
from backtest_engine.strategy_parser import parse_strategy_text
from backtest_engine.validator import validate
from backtest_engine import strategy_library as lib
from dashboard.mtf_backtest_worker import MTFBacktestWorker

_PLACEHOLDER = """Bias: 1D
Trend: 4H EMA 50
Entry: 1H

Entry Rules:
BOS and FVG bullish
RSI below 40

Exit Rules:
CHoCH

SL: below order block
Risk: 1%
RR: 1:3

Session: London and NY"""


class StrategyBuilderTab(QWidget):
    """Paste a strategy in English / Roman Urdu / mixed -> Parse -> Preview
    + Validate -> Run Backtest. Nothing here guesses: if the parser can't
    confidently detect a required field, validation blocks the run and
    lists exactly what's missing."""

    def __init__(self):
        super().__init__()
        self.worker = None
        self.current_config = None
        self.batch_start_time = None
        self._build_ui()
        self._reload_symbols()

    def _build_ui(self):
        root = QHBoxLayout(self)

        # ------------------------------------------------------------ left
        left = QVBoxLayout()

        left.addWidget(QLabel("Strategy Text (English / Roman Urdu / mixed):"))
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(_PLACEHOLDER)
        self.text_edit.setMinimumHeight(220)
        left.addWidget(self.text_edit)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit("Unnamed Strategy")
        name_row.addWidget(self.name_edit)
        left.addLayout(name_row)

        tags_row = QHBoxLayout()
        tags_row.addWidget(QLabel("Tags:"))
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("ict, mtf, scalping (comma separated)")
        tags_row.addWidget(self.tags_edit)
        left.addLayout(tags_row)

        parse_row = QHBoxLayout()
        self.btn_parse = QPushButton("Parse && Validate")
        self.btn_save_library = QPushButton("Save to Library")
        parse_row.addWidget(self.btn_parse)
        parse_row.addWidget(self.btn_save_library)
        left.addLayout(parse_row)

        settings_form = QFormLayout()
        self.initial_balance_spin = QDoubleSpinBox()
        self.initial_balance_spin.setRange(1, 100_000_000)
        self.initial_balance_spin.setValue(1000)
        settings_form.addRow("Initial Balance:", self.initial_balance_spin)

        self.commission_spin = QDoubleSpinBox()
        self.commission_spin.setRange(0, 10)
        self.commission_spin.setDecimals(3)
        self.commission_spin.setValue(0.1)
        self.commission_spin.setSuffix(" %")
        settings_form.addRow("Commission:", self.commission_spin)

        self.slippage_spin = QDoubleSpinBox()
        self.slippage_spin.setRange(0, 10)
        self.slippage_spin.setDecimals(3)
        self.slippage_spin.setValue(0.05)
        self.slippage_spin.setSuffix(" %")
        settings_form.addRow("Slippage:", self.slippage_spin)

        self.position_size_spin = QDoubleSpinBox()
        self.position_size_spin.setRange(0.1, 100)
        self.position_size_spin.setValue(10.0)
        self.position_size_spin.setSuffix(" %")
        settings_form.addRow("Position Size:", self.position_size_spin)
        left.addLayout(settings_form)

        self.use_full_history = QCheckBox("Use full downloaded history")
        self.use_full_history.setChecked(True)
        self.use_full_history.toggled.connect(self._on_full_history_toggled)
        left.addWidget(self.use_full_history)

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
        left.addLayout(date_row)

        self.all_coins_check = QCheckBox("All Coins")
        self.all_coins_check.setChecked(True)
        self.all_coins_check.toggled.connect(lambda checked: self.coins_list.setDisabled(checked))
        left.addWidget(self.all_coins_check)

        coins_box = QGroupBox("Coins")
        coins_layout = QVBoxLayout(coins_box)
        self.coins_list = QListWidget()
        self.coins_list.setDisabled(True)
        coins_layout.addWidget(self.coins_list)
        left.addWidget(coins_box, stretch=1)

        self.use_multiprocessing_check = QCheckBox("Use multiprocessing (faster, less granular live updates)")
        self.use_multiprocessing_check.setChecked(True)
        left.addWidget(self.use_multiprocessing_check)

        buttons = QHBoxLayout()
        self.btn_start = QPushButton("▶ Run Backtest")
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_resume = QPushButton("▶ Resume")
        self.btn_stop = QPushButton("⏹ Stop")
        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop):
            buttons.addWidget(b)
        left.addLayout(buttons)

        self.btn_parse.clicked.connect(self.on_parse)
        self.btn_save_library.clicked.connect(self.on_save_library)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_pause.clicked.connect(self.on_pause)
        self.btn_resume.clicked.connect(self.on_resume)
        self.btn_stop.clicked.connect(self.on_stop)
        self._set_running_state(False)
        self.btn_start.setEnabled(False)

        left_widget = QWidget()
        left_widget.setLayout(left)

        # ----------------------------------------------------------- right
        right = QVBoxLayout()

        preview_box = QGroupBox("Strategy Preview")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_view = QPlainTextEdit()
        self.preview_view.setReadOnly(True)
        self.preview_view.setMaximumHeight(220)
        self.preview_view.setStyleSheet("font-family: Consolas, monospace;")
        preview_layout.addWidget(self.preview_view)
        right.addWidget(preview_box)

        status_box = QGroupBox("Backtest Status")
        grid = QGridLayout(status_box)
        self.fields = {}
        field_names = [
            "Current Strategy", "Current Rule", "Current Coin", "Current Timeframe",
            "Current Trade", "Current Progress", "Completed Coins", "Remaining Coins",
            "Estimated Time", "Trade Counter", "Validation Status",
        ]
        for i, name in enumerate(field_names):
            row, col = divmod(i, 2)
            grid.addWidget(QLabel(f"{name}:"), row, col * 2)
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            self.fields[name] = value_label
            grid.addWidget(value_label, row, col * 2 + 1)
        right.addWidget(status_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        right.addWidget(self.progress_bar)

        log_box = QGroupBox("Latest Logs")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setStyleSheet("font-family: Consolas, monospace;")
        log_layout.addWidget(self.log_view)
        right.addWidget(log_box, stretch=1)

        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def _set_running_state(self, running):
        self.btn_start.setEnabled((not running) and self.current_config is not None and not validate(self.current_config))
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(running)
        self.btn_stop.setEnabled(running)

    def _on_full_history_toggled(self, checked):
        self.start_date_edit.setEnabled(not checked)
        self.end_date_edit.setEnabled(not checked)

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

    # -------------------------------------------------------------- parsing
    def on_parse(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "SINDHU", "Paste a strategy first.")
            return

        name = self.name_edit.text().strip() or "Unnamed Strategy"
        cfg = parse_strategy_text(text, name=name)
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        cfg.tags = tags
        self.current_config = cfg

        errors = validate(cfg)
        self._render_preview(cfg, errors)
        self.fields["Validation Status"].setText("Valid" if not errors else f"{len(errors)} error(s)")
        self.fields["Validation Status"].setStyleSheet(
            "font-weight: bold; color: green;" if not errors else "font-weight: bold; color: red;"
        )
        self.fields["Current Strategy"].setText(cfg.name)
        self._set_running_state(False)

    def _render_preview(self, cfg, errors):
        def describe(conditions):
            if not conditions:
                return "-"
            parts = []
            for c in conditions:
                if c.type == "concept":
                    parts.append(f"{(c.direction + ' ') if c.direction else ''}{c.name}".strip())
                elif c.type == "indicator_compare":
                    parts.append(f"{c.indicator} {c.op} {c.value}")
                elif c.type == "price_compare":
                    parts.append(f"price {c.op} {c.indicator}")
                elif c.type == "session":
                    parts.append(f"session={c.name}")
                elif c.type == "trend":
                    parts.append(f"trend={c.direction}")
                else:
                    parts.append(f"[UNCLEAR] {c.text}")
            return " AND ".join(parts)

        indicator_labels = [
            f"{i['name']}({i['params']['period']})" if i["params"].get("period") else i["name"]
            for i in cfg.indicators
        ]

        lines = [
            f"Strategy Name: {cfg.name}",
            f"Detected Timeframes: {cfg.timeframes or '(none detected)'}",
            f"Indicators: {indicator_labels or '(none)'}",
            f"Entry Rules: {describe(cfg.entry_conditions)}",
            f"Confirmation Rules: {describe(cfg.confirmation_conditions)}",
            f"Exit Rules: {describe(cfg.exit_conditions)}",
            f"Stop Loss: {cfg.stop_loss.type} {cfg.stop_loss.value if cfg.stop_loss.value is not None else ''}",
            f"Take Profit: {cfg.take_profit.type} {cfg.take_profit.value if cfg.take_profit.value is not None else ''}",
            f"Risk %: {cfg.risk_pct}",
            f"Risk:Reward: {cfg.risk_reward}",
            f"Session Filter: {cfg.session_filter or '(none)'}",
            "",
            f"Status: {'VALID -- ready to run' if not errors else 'INVALID'}",
        ]
        for e in errors:
            lines.append(f"  - {e}")
        for w in cfg.warnings:
            lines.append(f"  (warning) {w}")
        self.preview_view.setPlainText("\n".join(lines))

    def on_save_library(self):
        if self.current_config is None:
            QMessageBox.warning(self, "SINDHU", "Parse a strategy before saving it.")
            return
        strategy_id = lib.create(self.current_config, tags=self.current_config.tags)
        self.log_view.appendPlainText(f"Saved to library: {self.current_config.name} (id={strategy_id})")

    def load_from_library(self, strategy_id):
        cfg = lib.load(strategy_id)
        self.text_edit.setPlainText(cfg.raw_text)
        self.name_edit.setText(cfg.name)
        self.tags_edit.setText(", ".join(cfg.tags))
        self.on_parse()

    # -------------------------------------------------------------- run
    def on_start(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self.current_config is None:
            return
        errors = validate(self.current_config)
        if errors:
            QMessageBox.warning(self, "SINDHU", "Cannot run: strategy is invalid. See preview for details.")
            return

        if self.all_coins_check.isChecked():
            symbols = storage.load_symbols(self.exchange_id)
        else:
            symbols = [
                self.coins_list.item(i).text()
                for i in range(self.coins_list.count())
                if self.coins_list.item(i).checkState() == Qt.Checked
            ]
        if not symbols:
            QMessageBox.warning(self, "SINDHU", "No coins selected/available.")
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
            "initial_balance": self.initial_balance_spin.value(),
            "risk_pct": self.current_config.risk_pct or 1.0,
            "commission_pct": self.commission_spin.value(),
            "slippage_pct": self.slippage_spin.value(),
            "position_size_pct": self.position_size_spin.value(),
            "start_ms": start_ms, "end_ms": end_ms,
        }

        self.log_view.clear()
        self.batch_start_time = time.time()
        self.fields["Current Strategy"].setText(self.current_config.name)

        self.worker = MTFBacktestWorker(
            self.current_config, self.exchange_id, symbols, settings,
            use_multiprocessing=self.use_multiprocessing_check.isChecked(),
        )
        self.worker.log_line.connect(self._on_log_line)
        self.worker.coin_changed.connect(lambda s: (
            self.fields["Current Coin"].setText(s),
            self.fields["Current Timeframe"].setText(self.current_config.timeframes.get("entry", "-")),
        ))
        self.worker.progress_changed.connect(self._on_progress)
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

    def _on_log_line(self, line):
        self.log_view.appendPlainText(line)

    def _on_progress(self, done, total):
        self.fields["Completed Coins"].setText(str(done))
        self.fields["Remaining Coins"].setText(str(total - done))
        self.fields["Current Progress"].setText(f"{done} / {total}")
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)
        if done > 0 and self.batch_start_time:
            elapsed = time.time() - self.batch_start_time
            eta = (elapsed / done) * (total - done)
            self.fields["Estimated Time"].setText(_format_duration(eta))
        else:
            self.fields["Estimated Time"].setText("-")

    def _on_trade_update(self, stats):
        self.fields["Current Trade"].setText(stats["current_trade"])
        self.fields["Current Rule"].setText(stats["current_rule"])
        self.fields["Trade Counter"].setText(str(stats["total_trades"]))

    def _on_finished(self, batch_id):
        self._set_running_state(False)
        if batch_id:
            self.log_view.appendPlainText(f"Report saved: data/reports/{batch_id}/report.txt")
        self.last_batch_id = batch_id


def _format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"

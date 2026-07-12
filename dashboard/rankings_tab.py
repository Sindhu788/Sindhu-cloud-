from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QSplitter,
)

from data_engine import storage, config
from backtest_engine.reports import generate_report
from backtest_engine import export, strategy_library as lib
from dashboard.queue_worker import QueueWorker


def _fill_table(table, rows, columns):
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, col in enumerate(columns):
            table.setItem(r, c, QTableWidgetItem(str(row.get(col, ""))))


class RankingsTab(QWidget):
    """Coin/timeframe/session ranking for a chosen batch, one-click
    CSV/Excel/PDF export, and a queue to run several library strategies
    back-to-back."""

    def __init__(self):
        super().__init__()
        self.worker = None
        self._build_ui()
        self.refresh_batches()
        self._reload_library()

    def _build_ui(self):
        root = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Batch:"))
        self.batch_combo = QComboBox()
        self.batch_combo.currentIndexChanged.connect(self._on_batch_changed)
        top_row.addWidget(self.batch_combo, stretch=1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_batches)
        top_row.addWidget(self.btn_refresh)
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_excel = QPushButton("Export Excel")
        self.btn_export_pdf = QPushButton("Export PDF")
        for b in (self.btn_export_csv, self.btn_export_excel, self.btn_export_pdf):
            top_row.addWidget(b)
        root.addLayout(top_row)

        self.btn_export_csv.clicked.connect(self._on_export_csv)
        self.btn_export_excel.clicked.connect(self._on_export_excel)
        self.btn_export_pdf.clicked.connect(self._on_export_pdf)

        tables_row = QHBoxLayout()
        coin_box = QGroupBox("Coin Ranking")
        coin_layout = QVBoxLayout(coin_box)
        self.coin_table = QTableWidget()
        coin_layout.addWidget(self.coin_table)
        tables_row.addWidget(coin_box)

        tf_box = QGroupBox("Timeframe Ranking")
        tf_layout = QVBoxLayout(tf_box)
        self.tf_table = QTableWidget()
        tf_layout.addWidget(self.tf_table)
        tables_row.addWidget(tf_box)

        session_box = QGroupBox("Session Analysis")
        session_layout = QVBoxLayout(session_box)
        self.session_table = QTableWidget()
        session_layout.addWidget(self.session_table)
        tables_row.addWidget(session_box)
        root.addLayout(tables_row, stretch=2)

        # ---------------------------------------------------------- queue
        queue_box = QGroupBox("Backtest Queue")
        queue_layout = QHBoxLayout(queue_box)

        left = QVBoxLayout()
        left.addWidget(QLabel("Library strategies (check to queue):"))
        self.library_list = QListWidget()
        left.addWidget(self.library_list)
        queue_buttons = QHBoxLayout()
        self.btn_reload_library = QPushButton("Reload Library")
        self.btn_run_queue = QPushButton("▶ Run Queue")
        self.btn_stop_queue = QPushButton("⏹ Stop Queue")
        queue_buttons.addWidget(self.btn_reload_library)
        queue_buttons.addWidget(self.btn_run_queue)
        queue_buttons.addWidget(self.btn_stop_queue)
        left.addLayout(queue_buttons)
        left_widget = QWidget()
        left_widget.setLayout(left)

        right = QVBoxLayout()
        self.queue_status_label = QLabel("Idle")
        right.addWidget(self.queue_status_label)
        self.queue_log = QPlainTextEdit()
        self.queue_log.setReadOnly(True)
        self.queue_log.setMaximumBlockCount(1000)
        right.addWidget(self.queue_log)
        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        queue_layout.addWidget(splitter)
        root.addWidget(queue_box, stretch=1)

        self.btn_reload_library.clicked.connect(self._reload_library)
        self.btn_run_queue.clicked.connect(self._on_run_queue)
        self.btn_stop_queue.clicked.connect(self._on_stop_queue)

    # -------------------------------------------------------------- rankings
    def refresh_batches(self):
        self.batch_combo.blockSignals(True)
        self.batch_combo.clear()
        self._batches = storage.list_recent_batches()
        for b in self._batches:
            self.batch_combo.addItem(f"{b['created_at'][:19]}  {b['strategy_name']}  ({b['status']})", b["batch_id"])
        self.batch_combo.blockSignals(False)
        if self._batches:
            self._load_batch(self._batches[0]["batch_id"])

    def _on_batch_changed(self, index):
        if 0 <= index < len(self._batches):
            self._load_batch(self._batches[index]["batch_id"])

    def _load_batch(self, batch_id):
        self.current_batch_id = batch_id
        summary = generate_report(batch_id)
        _fill_table(self.coin_table, summary["coin_ranking"],
                    ["symbol", "avg_profit_pct", "win_rate", "total_trades", "max_drawdown_pct", "avg_profit_factor"])
        _fill_table(self.tf_table, summary["timeframe_ranking"],
                    ["timeframe", "avg_profit_pct", "win_rate", "total_trades", "max_drawdown_pct", "avg_profit_factor"])
        _fill_table(self.session_table, summary["session_analysis"],
                    ["session", "trades", "win_rate", "total_pnl"])

    def _on_export_csv(self):
        if not getattr(self, "current_batch_id", None):
            return
        paths = export.export_csv(self.current_batch_id)
        QMessageBox.information(self, "Export CSV", f"Saved:\n{paths['results_summary']}\n{paths['trades']}")

    def _on_export_excel(self):
        if not getattr(self, "current_batch_id", None):
            return
        path = export.export_excel(self.current_batch_id)
        QMessageBox.information(self, "Export Excel", f"Saved:\n{path}")

    def _on_export_pdf(self):
        if not getattr(self, "current_batch_id", None):
            return
        path = export.export_pdf(self.current_batch_id)
        QMessageBox.information(self, "Export PDF", f"Saved:\n{path}")

    # -------------------------------------------------------------- queue
    def _reload_library(self):
        self.library_list.clear()
        for meta in lib.list_all():
            item = QListWidgetItem(meta["name"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, meta["id"])
            self.library_list.addItem(item)

    def _on_run_queue(self):
        if self.worker is not None and self.worker.isRunning():
            return
        selected_ids = [
            self.library_list.item(i).data(Qt.UserRole)
            for i in range(self.library_list.count())
            if self.library_list.item(i).checkState() == Qt.Checked
        ]
        if not selected_ids:
            QMessageBox.warning(self, "SINDHU", "Check at least one strategy to queue.")
            return

        exchanges_cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
        exchange_id = exchanges_cfg["default"]
        symbols = storage.load_symbols(exchange_id)

        items = []
        for sid in selected_ids:
            cfg = lib.load(sid)
            settings = {
                "initial_balance": 1000.0,
                "risk_pct": cfg.risk_pct or 1.0,
                "commission_pct": 0.1,
                "slippage_pct": 0.05,
                "position_size_pct": 10.0,
            }
            items.append({"config": cfg, "symbols": symbols, "settings": settings})

        self.queue_log.clear()
        self.worker = QueueWorker(items, exchange_id)
        self.worker.log_line.connect(self.queue_log.appendPlainText)
        self.worker.queue_progress.connect(
            lambda i, total, name: self.queue_status_label.setText(f"Running {i}/{total}: {name}")
        )
        self.worker.finished_run.connect(self._on_queue_finished)
        self.worker.start()

    def _on_stop_queue(self):
        if self.worker:
            self.worker.control.stop()

    def _on_queue_finished(self, results):
        self.queue_status_label.setText(f"Done -- {len(results)} batch(es) completed")
        self.refresh_batches()

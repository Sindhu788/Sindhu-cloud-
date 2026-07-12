from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel,
)

from data_engine import storage
from dashboard.trade_replay_dialog import TradeReplayDialog

_COLUMNS = [
    "symbol", "timeframe", "side", "entry_time", "exit_time", "entry_price", "exit_price",
    "stop_loss", "take_profit", "risk_amount", "reward_amount", "pnl", "pnl_pct",
    "entry_reason", "exit_reason",
]


class TradeHistoryTab(QWidget):
    """Every trade from a batch, in one sortable table. Double-click a row
    to replay it: entry/exit candles, SL/TP, and why it opened/closed."""

    def __init__(self):
        super().__init__()
        self._trades = []
        self._build_ui()
        self.refresh_batches()

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
        root.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setColumnCount(len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        root.addWidget(self.table, stretch=1)

    def refresh_batches(self):
        self.batch_combo.blockSignals(True)
        self.batch_combo.clear()
        self._batches = storage.list_recent_batches()
        for b in self._batches:
            self.batch_combo.addItem(f"{b['created_at'][:19]}  {b['strategy_name']}  ({b['status']})", b["batch_id"])
        self.batch_combo.blockSignals(False)
        if self._batches:
            self._load_batch(self._batches[0]["batch_id"])
        else:
            self.table.setRowCount(0)

    def _on_batch_changed(self, index):
        if 0 <= index < len(self._batches):
            self._load_batch(self._batches[index]["batch_id"])

    def _load_batch(self, batch_id):
        self.current_batch_id = batch_id
        batch = storage.get_batch(batch_id)
        self.current_exchange = batch["exchange"] if batch else "binance"
        self._trades = storage.get_trades(batch_id)
        self.table.setRowCount(len(self._trades))
        for row, t in enumerate(self._trades):
            for col, key in enumerate(_COLUMNS):
                value = t.get(key)
                self.table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))

    def _on_row_double_clicked(self, index):
        row = index.row()
        if row < 0 or row >= len(self._trades):
            return
        trade = self._trades[row]
        dialog = TradeReplayDialog(self.current_exchange, trade["symbol"], trade["timeframe"], trade, parent=self)
        dialog.exec()

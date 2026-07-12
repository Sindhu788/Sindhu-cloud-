from datetime import datetime, timezone

import pyqtgraph as pg
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit

from data_engine.resample import get_ohlcv
from dashboard.candlestick_item import CandlestickItem

_BARS_BEFORE = 40
_BARS_AFTER = 15


class TradeReplayDialog(QDialog):
    """Shows the entry/exit candles around one trade with SL/TP levels and
    a plain-English explanation of why it opened and why it closed."""

    def __init__(self, exchange, symbol, timeframe, trade, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Trade Replay -- {symbol} {timeframe} #{trade.get('trade_num')}")
        self.resize(900, 600)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{symbol}  {timeframe}  {trade['side'].upper()}  "
                                 f"entry={trade['entry_price']:.6g}  exit={trade.get('exit_price', '-')}"))

        plot = pg.PlotWidget()
        plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(plot, stretch=1)

        df = get_ohlcv(exchange, symbol, timeframe)
        if not df.empty and trade.get("entry_time"):
            entry_ts = datetime.fromtimestamp(trade["entry_time"] / 1000, tz=timezone.utc)
            exit_ts = (datetime.fromtimestamp(trade["exit_time"] / 1000, tz=timezone.utc)
                       if trade.get("exit_time") else entry_ts)

            entry_pos = df.index.searchsorted(entry_ts)
            exit_pos = df.index.searchsorted(exit_ts)
            start = max(0, entry_pos - _BARS_BEFORE)
            end = min(len(df), exit_pos + _BARS_AFTER)
            window = df.iloc[start:end]

            candles = [
                (i, row.open, row.high, row.low, row.close)
                for i, (_, row) in enumerate(window.iterrows())
            ]
            plot.addItem(CandlestickItem(candles))

            entry_x = entry_pos - start
            exit_x = exit_pos - start
            plot.addItem(pg.InfiniteLine(pos=entry_x, angle=90, pen=pg.mkPen("#3498db", width=2),
                                          label="Entry", labelOpts={"position": 0.95}))
            if trade.get("exit_time"):
                plot.addItem(pg.InfiniteLine(pos=exit_x, angle=90, pen=pg.mkPen("#9b59b6", width=2),
                                              label="Exit", labelOpts={"position": 0.85}))
            if trade.get("stop_loss") is not None:
                plot.addItem(pg.InfiniteLine(pos=trade["stop_loss"], angle=0, pen=pg.mkPen("#e74c3c", style=pg.QtCore.Qt.DashLine),
                                              label="SL"))
            if trade.get("take_profit") is not None:
                plot.addItem(pg.InfiniteLine(pos=trade["take_profit"], angle=0, pen=pg.mkPen("#2ecc71", style=pg.QtCore.Qt.DashLine),
                                              label="TP"))
        else:
            layout.addWidget(QLabel("No candle data available for this trade's window."))

        explain = QPlainTextEdit()
        explain.setReadOnly(True)
        explain.setMaximumHeight(120)
        explain.setPlainText(
            f"Why opened: {trade.get('entry_reason', '-')}\n"
            f"Why closed: {trade.get('exit_reason', '-')}\n"
            f"Stop Loss: {trade.get('stop_loss', '-')}   Take Profit: {trade.get('take_profit', '-')}\n"
            f"Risk: {trade.get('risk_amount', '-')}   Reward: {trade.get('reward_amount', '-')}\n"
            f"PnL: {trade.get('pnl', '-')}  ({trade.get('pnl_pct', '-')}%)"
        )
        layout.addWidget(explain)

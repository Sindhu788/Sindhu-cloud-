from PySide6.QtCore import QThread, Signal

from data_engine.control import DownloadControl
from data_engine.logging_setup import log as file_log
from backtest_engine import runner
from backtest_engine.reports import generate_report


class BacktestWorker(QThread):
    """Runs a full backtest batch (every selected coin x timeframe) off the
    GUI thread. `settings` carries both the numeric backtest settings
    (initial_balance, risk_pct, ...) and the batch scope (symbols,
    timeframes, start_ms, end_ms) so the whole thing round-trips through
    storage for resuming later."""

    log_line = Signal(str)
    coin_changed = Signal(str)
    timeframe_changed = Signal(str)
    tests_progress = Signal(int, int)
    trade_update = Signal(dict)
    finished_run = Signal(str)

    def __init__(self, strategy_class, exchange, settings, batch_id=None, parent=None):
        super().__init__(parent)
        self.strategy_class = strategy_class
        self.exchange = exchange
        self.settings = settings
        self.batch_id = batch_id
        self.control = DownloadControl()
        self._combo_stats = {}

    def _log(self, message):
        file_log(message)
        self.log_line.emit(message)

    def _progress_cb(self, done, total, symbol, timeframe):
        self._combo_stats = {
            "total_trades": 0, "wins": 0, "losses": 0,
            "current_trade": "-", "win_rate": 0.0,
            "profit_pct": 0.0, "drawdown_pct": 0.0,
            "_balance": self.settings["initial_balance"],
            "_peak": self.settings["initial_balance"],
        }
        self.coin_changed.emit(symbol)
        self.timeframe_changed.emit(timeframe)
        self.tests_progress.emit(done, total)

    def _trade_cb(self, symbol, timeframe, trade):
        s = self._combo_stats
        s["total_trades"] += 1
        if trade["pnl"] > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1
        s["win_rate"] = (s["wins"] / s["total_trades"] * 100) if s["total_trades"] else 0.0
        s["_balance"] += trade["pnl"]
        s["_peak"] = max(s["_peak"], s["_balance"])
        dd = ((s["_peak"] - s["_balance"]) / s["_peak"] * 100) if s["_peak"] else 0.0
        s["drawdown_pct"] = max(s["drawdown_pct"], dd)
        s["profit_pct"] = (s["_balance"] - self.settings["initial_balance"]) / self.settings["initial_balance"] * 100
        s["current_trade"] = f"#{trade['trade_num']} {trade['side']} {symbol} {timeframe} pnl={trade['pnl']:.2f}"
        self.trade_update.emit(dict(s))

    def run(self):
        batch_id = self.batch_id
        try:
            self._log("Backtesting Started...")
            batch_id = runner.run_batch(
                self.strategy_class, self.exchange,
                self.settings["symbols"], self.settings["timeframes"], self.settings,
                start_ms=self.settings.get("start_ms"), end_ms=self.settings.get("end_ms"),
                batch_id=self.batch_id, log=self._log, control=self.control,
                progress_cb=self._progress_cb, trade_cb=self._trade_cb,
            )
            self._log("Saving Results...")
            generate_report(batch_id)
        except Exception as e:
            self._log(f"FATAL ERROR: {e!r}")
        self.finished_run.emit(batch_id or "")

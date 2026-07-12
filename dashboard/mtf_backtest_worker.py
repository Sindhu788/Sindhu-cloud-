from PySide6.QtCore import QThread, Signal

from data_engine.control import DownloadControl
from data_engine.logging_setup import log as file_log
from backtest_engine import runner
from backtest_engine.reports import generate_report


class MTFBacktestWorker(QThread):
    """Runs a parsed multi-timeframe StrategyConfig across one or more
    coins (backtest_engine.runner.run_mtf_batch) off the GUI thread."""

    log_line = Signal(str)
    coin_changed = Signal(str)
    progress_changed = Signal(int, int)
    trade_update = Signal(dict)
    finished_run = Signal(str)

    def __init__(self, config, exchange, symbols, settings, batch_id=None,
                 use_multiprocessing=True, parent=None):
        super().__init__(parent)
        self.config = config
        self.exchange = exchange
        self.symbols = symbols
        self.settings = settings
        self.batch_id = batch_id
        self.use_multiprocessing = use_multiprocessing
        self.control = DownloadControl()
        self._stats = {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "profit_pct": 0.0, "drawdown_pct": 0.0, "current_trade": "-", "current_rule": "-",
            "_balance": settings["initial_balance"], "_peak": settings["initial_balance"],
        }

    def _log(self, message):
        file_log(message)
        self.log_line.emit(message)

    def _progress_cb(self, done, total, symbol, timeframe):
        self.coin_changed.emit(symbol)
        self.progress_changed.emit(done, total)

    def _trade_cb(self, symbol, timeframe, trade):
        s = self._stats
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
        s["current_trade"] = f"#{trade['trade_num']} {trade['side']} {symbol} pnl={trade['pnl']:.2f}"
        s["current_rule"] = f"entry: {trade.get('entry_reason', '-')} | exit: {trade.get('exit_reason', '-')}"
        self.trade_update.emit(dict(s))

    def run(self):
        batch_id = self.batch_id
        try:
            self._log("Backtesting Started...")
            batch_id = runner.run_mtf_batch(
                self.config, self.exchange, self.symbols, self.settings,
                start_ms=self.settings.get("start_ms"), end_ms=self.settings.get("end_ms"),
                batch_id=self.batch_id, log=self._log, control=self.control,
                progress_cb=self._progress_cb, trade_cb=self._trade_cb,
                use_multiprocessing=self.use_multiprocessing,
            )
            self._log("Saving Results...")
            generate_report(batch_id)
        except Exception as e:
            self._log(f"FATAL ERROR: {e!r}")
        self.finished_run.emit(batch_id or "")

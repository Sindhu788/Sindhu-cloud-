from PySide6.QtCore import QThread, Signal

from data_engine import storage
from data_engine.paths import migrate_legacy_files
from data_engine.control import DownloadControl
from data_engine.symbols import pick_top_symbols
from data_engine.downloader import download_all
from data_engine.exchanges.registry import get_exchange_client
from data_engine.logging_setup import log as file_log


class DownloadWorker(QThread):
    """Runs the whole startup + download sequence off the GUI thread so the
    dashboard stays responsive, reporting back to it purely through Qt
    signals (Qt marshals these across the thread boundary automatically)."""

    log_line = Signal(str)
    status_changed = Signal(str)
    process_changed = Signal(str)
    coin_changed = Signal(str)
    progress_changed = Signal(int, int)
    finished_run = Signal()

    def __init__(self, exchange_id, num_coins, quote_asset, parent=None):
        super().__init__(parent)
        self.exchange_id = exchange_id
        self.num_coins = num_coins
        self.quote_asset = quote_asset
        self.control = DownloadControl()

    def _log(self, message):
        file_log(message)
        self.log_line.emit(message)

    def run(self):
        try:
            self.status_changed.emit("Initializing")
            self.process_changed.emit("Starting SINDHU")
            self._log("Starting SINDHU...")

            self.process_changed.emit("Loading Settings")
            self._log("Loading Settings...")
            migrate_legacy_files()

            self.process_changed.emit("Connecting Database")
            storage.init_db()
            self._log("Database Connected...")

            self.process_changed.emit(f"Connecting {self.exchange_id}")
            self._log(f"Connecting {self.exchange_id}...")
            exchange_client = get_exchange_client(self.exchange_id)

            existing = storage.load_symbols(self.exchange_id)
            if existing:
                symbols = existing
                self._log(f"Using previously selected {len(symbols)} symbols for {self.exchange_id}.")
            else:
                self._log(f"Selecting top {self.num_coins} {self.quote_asset} pairs by market cap...")
                symbols = pick_top_symbols(exchange_client, self.num_coins, self.quote_asset)
                self._log("Symbols: " + ", ".join(symbols))

            self.status_changed.emit("Downloading")

            def progress_cb(i, total, symbol):
                self.process_changed.emit(f"Downloading {symbol}")
                self.coin_changed.emit(symbol)
                self.progress_changed.emit(i, total)

            download_all(
                exchange_client, symbols,
                log=self._log, control=self.control, progress_cb=progress_cb,
            )

            if self.control.should_stop():
                self.status_changed.emit("Stopped")
                self.process_changed.emit("Stopped")
            else:
                self.status_changed.emit("Idle")
                self.process_changed.emit("Finished")
        except Exception as e:
            self._log(f"FATAL ERROR: {e!r}")
            self.status_changed.emit("Error")
        finally:
            self.finished_run.emit()

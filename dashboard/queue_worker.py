from PySide6.QtCore import QThread, Signal

from data_engine.control import DownloadControl
from data_engine.logging_setup import log as file_log
from backtest_engine import queue_runner
from backtest_engine.reports import generate_report


class QueueWorker(QThread):
    """Runs several strategies one after another (backtest_engine.queue_runner)."""

    log_line = Signal(str)
    queue_progress = Signal(int, int, str)
    finished_run = Signal(list)

    def __init__(self, items, exchange, use_multiprocessing=True, parent=None):
        super().__init__(parent)
        self.items = items
        self.exchange = exchange
        self.use_multiprocessing = use_multiprocessing
        self.control = DownloadControl()

    def _log(self, message):
        file_log(message)
        self.log_line.emit(message)

    def _queue_progress_cb(self, i, total, name):
        self.queue_progress.emit(i, total, name)

    def run(self):
        results = []
        try:
            results = queue_runner.run_queue(
                self.items, self.exchange, log=self._log, control=self.control,
                queue_progress_cb=self._queue_progress_cb,
                use_multiprocessing=self.use_multiprocessing,
            )
            for r in results:
                if r["batch_id"]:
                    generate_report(r["batch_id"])
        except Exception as e:
            self._log(f"FATAL ERROR: {e!r}")
        self.finished_run.emit(results)

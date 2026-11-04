"""Adapter used by data_engine.resample.get_ohlcv when SINDHU_BACKTEST_SOURCE=dataplatform. One shared loader per process."""
import threading

from data_platform.loader import CandleLoader

_lock = threading.Lock()
_loader = None
_final_exam = {"on": False, "who": "backtest"}


def loader():
    global _loader
    with _lock:
        if _loader is None:
            _loader = CandleLoader()
        return _loader


def set_final_exam(on, who="final-exam"):
    """Only the audited final-exam script calls this (it also needs SINDHU_FINAL_EXAM in the environment)."""
    _final_exam.update(on=bool(on), who=who)


def get_ohlcv_dp(symbol, interval, start_ms, end_ms):
    return loader().load(symbol.replace("/", ""), interval, start=start_ms, end=end_ms,
                         allow_final_exam=_final_exam["on"], who=_final_exam["who"])

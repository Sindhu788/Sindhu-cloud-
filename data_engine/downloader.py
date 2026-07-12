import time
from datetime import datetime, timezone, timedelta

from data_engine import storage
from data_engine.logging_setup import log as default_log
from data_engine.config import (
    BASE_INTERVAL, HISTORY_DAYS, KLINES_LIMIT, REQUEST_DELAY_SECONDS,
)

ONE_MIN_MS = 60_000


def _now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _history_start_ms():
    start = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
    return int(start.timestamp() * 1000)


def download_symbol(exchange_client, symbol, log=default_log, control=None):
    """Fetch all missing 1m klines for `symbol` from the 1-year cutoff up to
    now, resuming from wherever the last run left off. `control` (a
    DownloadControl), if given, is checked between batches so the dashboard
    can pause/resume/stop cleanly mid-download."""
    exchange = exchange_client.id
    last_open_time, _status = storage.get_progress(exchange, symbol)
    history_start = _history_start_ms()
    cursor = max(last_open_time + ONE_MIN_MS, history_start) if last_open_time else history_start
    end = _now_ms()

    if cursor >= end:
        storage.set_progress(exchange, symbol, last_open_time, "up_to_date", datetime.now(timezone.utc).isoformat())
        return 0

    total_saved = 0
    while cursor < end:
        if control:
            control.wait_if_paused()
            if control.should_stop():
                storage.set_progress(exchange, symbol, last_open_time, "paused", datetime.now(timezone.utc).isoformat())
                return total_saved

        rows = exchange_client.get_ohlcv(symbol, BASE_INTERVAL, since_ms=cursor, limit=KLINES_LIMIT)
        time.sleep(REQUEST_DELAY_SECONDS)

        if not rows:
            break

        storage.insert_klines(exchange, symbol, rows)
        total_saved += len(rows)

        last_open_time = rows[-1][0]
        storage.set_progress(exchange, symbol, last_open_time, "in_progress", datetime.now(timezone.utc).isoformat())

        cursor = last_open_time + ONE_MIN_MS

        if len(rows) < KLINES_LIMIT:
            break

    storage.set_progress(exchange, symbol, last_open_time, "up_to_date", datetime.now(timezone.utc).isoformat())
    log(f"  {symbol}: +{total_saved} candles (total stored: {storage.count_rows(exchange, symbol)})")
    return total_saved


def download_all(exchange_client, symbols, log=default_log, control=None, progress_cb=None):
    """progress_cb(index, total, symbol), if given, is called before each
    symbol starts downloading -- used by the dashboard to show
    'Current Coin' / 'Download Progress'."""
    storage.init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    storage.save_symbols(exchange_client.id, symbols, now_iso)

    log(f"Starting download for {len(symbols)} symbols on {exchange_client.id}, "
        f"{HISTORY_DAYS} days of {BASE_INTERVAL} history each.")
    for i, symbol in enumerate(symbols, start=1):
        if control and control.should_stop():
            log("Stopped by user.")
            return
        if control:
            control.wait_if_paused()

        if progress_cb:
            progress_cb(i, len(symbols), symbol)
        log(f"[{i}/{len(symbols)}] {symbol}")
        try:
            download_symbol(exchange_client, symbol, log=log, control=control)
        except Exception as e:
            log(f"  {symbol}: ERROR {e!r} (will resume from last saved candle on next run)")
    log("Download pass complete.")

import sys
import time
from datetime import datetime, timezone

from data_engine import storage
from data_engine.paths import migrate_legacy_files
from data_engine.symbols import pick_top_symbols
from data_engine.downloader import download_all
from data_engine.config import NUM_COINS, HISTORY_DAYS, SUPPORTED_INTERVALS, DEFAULT_EXCHANGE
from data_engine.exchanges.registry import get_exchange_client, ALL_EXCHANGE_IDS


def _exchange_arg(argv):
    for i, a in enumerate(argv):
        if a == "--exchange" and i + 1 < len(argv):
            return argv[i + 1]
    return DEFAULT_EXCHANGE


def cmd_download(exchange_id):
    migrate_legacy_files()
    storage.init_db()
    exchange_client = get_exchange_client(exchange_id)

    existing = storage.load_symbols(exchange_id)
    if existing:
        symbols = existing
        print(f"Using previously selected {len(symbols)} symbols for {exchange_id} (from database).")
    else:
        print(f"Selecting top {NUM_COINS} USDT pairs by market cap on {exchange_id}...")
        symbols = pick_top_symbols(exchange_client, NUM_COINS)
        print("Symbols:", ", ".join(symbols))

    download_all(exchange_client, symbols)


def cmd_status(exchange_id):
    migrate_legacy_files()
    storage.init_db()
    symbols = storage.load_symbols(exchange_id)
    if not symbols:
        print(f"No symbols selected yet for {exchange_id}. Run: python run.py download --exchange {exchange_id}")
        return

    print(f"{'SYMBOL':<14}{'ROWS':>10}  STATUS       LAST CANDLE (UTC)")
    for s in symbols:
        rows = storage.count_rows(exchange_id, s)
        last_open_time, status = storage.get_progress(exchange_id, s)
        last_dt = (
            datetime.fromtimestamp(last_open_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            if last_open_time else "-"
        )
        print(f"{s:<14}{rows:>10}  {status:<12} {last_dt}")


def cmd_watch(exchange_id):
    """Keep downloading in a loop, sleeping between passes, so the dataset
    stays current (useful once the initial 1-year backfill is done)."""
    interval_sec = 300
    while True:
        cmd_download(exchange_id)
        print(f"Sleeping {interval_sec}s before next incremental pass...\n")
        time.sleep(interval_sec)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "download"
    exchange_id = _exchange_arg(sys.argv)
    if exchange_id not in ALL_EXCHANGE_IDS:
        print(f"Unknown exchange {exchange_id!r}. Choose from: {ALL_EXCHANGE_IDS}")
        sys.exit(1)

    if cmd == "download":
        cmd_download(exchange_id)
    elif cmd == "status":
        cmd_status(exchange_id)
    elif cmd == "watch":
        cmd_watch(exchange_id)
    else:
        print(f"Unknown command {cmd!r}. Use: download | status | watch  [--exchange binance|okx|bybit|bitget|gate]")

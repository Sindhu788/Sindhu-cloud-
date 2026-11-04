"""Parquet storage for 1-minute candles (pyarrow + numpy only: no pandas needed, so it also runs where pandas is blocked).

Layout (root = SINDHU_DATA_ROOT, default D:\\sindhu_data):
  candles/<exchange>/<SYMBOL>/1m/YYYY-MM.parquet        one finished calendar month (from the exchange's monthly archive)
  candles/<exchange>/<SYMBOL>/1m_daily/YYYY-MM-DD.parquet   one closed day of the CURRENT month (immutable; the month file replaces them
                                                            for loading once it exists - the daily files are kept, never deleted)
  manifest/manifest.json, manifest/progress.json, universe/universe_<date>.json, logs/
"""
import hashlib
import os
import stat

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

DEFAULT_ROOT = r"D:\sindhu_data"
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"]
SCHEMA = pa.schema([
    ("open_time", pa.int64()), ("open", pa.float64()), ("high", pa.float64()), ("low", pa.float64()), ("close", pa.float64()),
    ("volume", pa.float64()), ("quote_volume", pa.float64()), ("trades", pa.int32()),
    ("taker_buy_base", pa.float64()), ("taker_buy_quote", pa.float64()),
])
MINUTE_MS = 60_000


def root():
    return os.environ.get("SINDHU_DATA_ROOT", DEFAULT_ROOT)


def month_path(exchange, symbol, month, base=None):
    return os.path.join(base or root(), "candles", exchange, symbol, "1m", f"{month}.parquet")


def day_path(exchange, symbol, day, base=None):
    return os.path.join(base or root(), "candles", exchange, symbol, "1m_daily", f"{day}.parquet")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_atomic(path, table):
    """Write `table` to `path` via a temporary name + atomic rename, then mark it read-only. REFUSES to replace an existing file
    (finished data is never overwritten). Returns (rows, sha256)."""
    if os.path.exists(path):
        raise FileExistsError(f"refusing to overwrite finished data file: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)                    # leftover of a crashed write: a temporary file, never finished data
    pq.write_table(table, tmp, compression="zstd")
    with open(tmp, "r+b") as f:             # fsync needs a writable handle on Windows
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, stat.S_IREAD)
    return table.num_rows, sha256_file(path)


def table_from_arrays(arrs):
    cols = []
    for name in COLUMNS:
        a = np.asarray(arrs[name])
        cols.append(pa.array(a.astype("int64") if name == "open_time" else (a.astype("int32") if name == "trades" else a.astype("float64"))))
    return pa.Table.from_arrays(cols, schema=SCHEMA)


def read_table(path, columns=None):
    return pq.read_table(path, columns=columns)


def to_arrays(table):
    return {c: table.column(c).to_numpy(zero_copy_only=False) for c in table.column_names}

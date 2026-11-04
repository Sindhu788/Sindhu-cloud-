"""Experiment tracker (Step 16): every backtest run is stored with everything that determines its result, so runs can be compared side by side and
re-run to the same answer. SQLite file under the data root (stdlib only)."""
import hashlib
import json
import os
import sqlite3
import subprocess
import threading
import time



def _root():
    return os.environ.get("SINDHU_DATA_ROOT", r"D:\sindhu_data")      # not imported from store: store needs pyarrow, the tracker must work without it

_lock = threading.Lock()
DDL = """CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, strategy_id TEXT NOT NULL, strategy_name TEXT,
  config_hash TEXT NOT NULL, code_commit TEXT, data_version TEXT NOT NULL, universe TEXT, symbol TEXT NOT NULL,
  window_start INTEGER, window_end INTEGER, cost_json TEXT, n_trades INTEGER, metrics_json TEXT, trades_path TEXT, result_hash TEXT)"""


def db_path(root=None):
    d = os.path.join(root or _root(), "experiments")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "experiments.db")


def connect(root=None):
    c = sqlite3.connect(db_path(root), timeout=60)
    c.execute(DDL)
    return c


def config_hash(cfg_dict):
    return hashlib.sha256(json.dumps(cfg_dict, sort_keys=True, default=str).encode()).hexdigest()[:16]


def code_commit(repo=None):
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return os.environ.get("RENDER_GIT_COMMIT", "")[:7] or None


def result_hash(trades):
    """Hash of the trade list (entry/exit time, side, prices, pnl rounded to 6 digits): equal hashes = identical results."""
    h = hashlib.sha256()
    for t in trades:
        h.update(f"{t['entry_time']}|{t['exit_time']}|{t['side']}|{t['entry_price']:.8g}|{t['exit_price']:.8g}|{t['pnl']:.6f};".encode())
    return h.hexdigest()[:16]


def record(row, root=None):
    cols = ["kind", "strategy_id", "strategy_name", "config_hash", "code_commit", "data_version", "universe", "symbol", "window_start", "window_end",
            "cost_json", "n_trades", "metrics_json", "trades_path", "result_hash"]
    with _lock:
        c = connect(root)
        try:
            cur = c.execute(f"INSERT INTO runs (ts,{','.join(cols)}) VALUES (?,{','.join('?' * len(cols))})",
                            [time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())] + [row.get(k) if not isinstance(row.get(k), (dict, list)) else json.dumps(row[k]) for k in cols])
            c.commit()
            return cur.lastrowid
        finally:
            c.close()


def compare(strategy_ids=None, root=None):
    """Side-by-side view: latest run per (strategy, symbol, window) with its key numbers."""
    c = connect(root)
    try:
        q = "SELECT strategy_id, strategy_name, symbol, window_start, window_end, n_trades, data_version, config_hash, code_commit, result_hash, metrics_json FROM runs"
        args = []
        if strategy_ids:
            q += " WHERE strategy_id IN (%s)" % ",".join("?" * len(strategy_ids))
            args = list(strategy_ids)
        return c.execute(q + " ORDER BY strategy_id, symbol, window_start, id", args).fetchall()
    finally:
        c.close()

"""Master Plan B2 (job BT-DATA): native Binance spot DAILY klines for the V2 benchmark universe.

Public market-data endpoint only (GET /api/v3/klines, no API key). Resumable: each symbol writes D:\\sindhu_data\\daily\\<SYM>_1d.parquet
(atomic tmp + rename, then read-only) and a marker <job_dir>\\<SYM>.done holding the file's SHA-256; a rerun skips symbols whose
marker matches the file. A heartbeat file is touched every unit (and by a timer thread every 60 s).

Universe rule (frozen in docs/BENCHMARK_PREREGISTRATION_V2.md section 0): walk universe_2026-11-04_v2.json in rank order, keep the first
20 symbols whose first daily candle is on or before 2023-01-01. Data kept from 2018-01-01 to the last CLOSED day.

Usage (bt venv):  python -m data_platform.daily_download [--job-dir D:\\sindhu_runtime\\bt_jobs\\BT-DATA] [--data-dir D:\\sindhu_data\\daily]
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import stat
import threading
import time

import requests

API = os.environ.get("SINDHU_DATA_API", "https://api.binance.com")
HEADERS = {"User-Agent": "sindhu-data-platform/1.0 (public market data)"}
UNIVERSE_FILE = r"D:\sindhu_data\universe\universe_2026-11-04_v2.json"
START = dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc)
LISTED_BY = dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc)
UNIVERSE_SIZE = 20
DAY_MS = 86_400_000
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades"]


def _ms(t):
    return int(t.timestamp() * 1000)


def _get(params, tries=6):
    last = None
    for i in range(tries):
        try:
            r = requests.get(API + "/api/v3/klines", params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            time.sleep(float(r.headers.get("Retry-After", 3 * (i + 1))) if r.status_code in (418, 429) else 2 * (i + 1))
        except requests.RequestException as e:
            last = type(e).__name__
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"klines {params.get('symbol')}: {last}")


def first_candle_ms(symbol):
    rows = _get({"symbol": symbol, "interval": "1d", "startTime": 0, "limit": 1})
    return int(rows[0][0]) if rows else None


def last_closed_day_open_ms(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    today0 = dt.datetime(now.year, now.month, now.day, tzinfo=dt.timezone.utc)
    return _ms(today0) - DAY_MS            # yesterday's candle is the last one that has closed


def fetch_daily(symbol, start_ms, end_open_ms):
    out, cur = [], start_ms
    while cur <= end_open_ms:
        rows = _get({"symbol": symbol, "interval": "1d", "startTime": cur, "endTime": end_open_ms + DAY_MS - 1, "limit": 1000})
        if not rows:
            break
        out.extend(rows)
        nxt = int(rows[-1][0]) + DAY_MS
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.25)
    seen, clean = set(), []
    for r in out:
        t = int(r[0])
        if t in seen or t > end_open_ms:
            continue
        seen.add(t)
        clean.append([t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[6]), float(r[7]), int(r[8])])
    clean.sort(key=lambda x: x[0])
    return clean


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_parquet_atomic(rows, path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    cols = list(zip(*rows)) if rows else [[] for _ in COLUMNS]
    table = pa.table({name: list(col) for name, col in zip(COLUMNS, cols)})
    tmp = path + ".tmp"
    pq.write_table(table, tmp)
    if os.path.exists(path):                # never overwrite a finished file silently
        os.chmod(path, stat.S_IWRITE)
        os.replace(path, path + f".superseded_{int(time.time())}")
    os.replace(tmp, path)
    os.chmod(path, stat.S_IREAD)


class Job:
    def __init__(self, job_dir, data_dir):
        self.job_dir, self.data_dir = job_dir, data_dir
        os.makedirs(job_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)
        self.log_path = os.path.join(job_dir, "job.log")
        self.hb = os.path.join(job_dir, "heartbeat.txt")
        self._stop = threading.Event()

    def log(self, msg):
        line = f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def beat(self, note=""):
        with open(self.hb, "w", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat()} {note}\n")

    def _beater(self):
        while not self._stop.wait(60):
            self.beat("alive")

    def marker(self, sym):
        return os.path.join(self.job_dir, f"{sym}.done")

    def is_done(self, sym, path):
        m = self.marker(sym)
        return os.path.exists(m) and os.path.exists(path) and open(m, encoding="utf-8").read().strip() == sha256(path)

    def resolve_universe(self):
        cache = os.path.join(self.job_dir, "listing_dates.json")
        listing = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else {}
        ranking = json.load(open(UNIVERSE_FILE, encoding="utf-8"))["ranking"]
        kept, skipped = [], []
        for row in sorted(ranking, key=lambda r: r["rank"]):
            sym = row["symbol"]
            if sym not in listing:
                listing[sym] = first_candle_ms(sym)
                json.dump(listing, open(cache, "w", encoding="utf-8"), indent=1)
                self.beat(f"listing {sym}")
            first = listing[sym]
            if first is not None and first <= _ms(LISTED_BY):
                kept.append({"symbol": sym, "rank": row["rank"], "first_daily_candle_utc": dt.datetime.fromtimestamp(first / 1000, dt.timezone.utc).date().isoformat()})
            else:
                skipped.append({"symbol": sym, "rank": row["rank"], "first_daily_candle_utc": None if first is None else dt.datetime.fromtimestamp(first / 1000, dt.timezone.utc).date().isoformat()})
            if len(kept) == UNIVERSE_SIZE:
                break
        return kept, skipped

    def run(self):
        threading.Thread(target=self._beater, daemon=True).start()
        try:
            kept, skipped = self.resolve_universe()
            uni_path = os.path.join(self.data_dir, "universe_v2.json")
            uni = {"rule": "first 20 by rank in universe_2026-11-04_v2.json with first daily candle <= 2023-01-01 (BENCHMARK_PREREGISTRATION_V2 section 0)",
                   "resolved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "symbols": kept, "skipped_listed_too_late": skipped}
            if not os.path.exists(uni_path):
                json.dump(uni, open(uni_path + ".tmp", "w", encoding="utf-8"), indent=1)
                os.replace(uni_path + ".tmp", uni_path)
                os.chmod(uni_path, stat.S_IREAD)
            else:
                old = [s["symbol"] for s in json.load(open(uni_path, encoding="utf-8"))["symbols"]]
                if old != [s["symbol"] for s in kept]:
                    self.log(f"WARNING universe differs from the frozen file; keeping the frozen file. frozen={old}")
                    kept = json.load(open(uni_path, encoding="utf-8"))["symbols"]
            self.log(f"universe: {len(kept)} symbols, {len(skipped)} skipped as listed after 2023-01-01")
            end_open = last_closed_day_open_ms()
            manifest = {}
            for i, s in enumerate(kept, 1):
                sym = s["symbol"]
                path = os.path.join(self.data_dir, f"{sym}_1d.parquet")
                if self.is_done(sym, path):
                    manifest[sym] = {"sha256": open(self.marker(sym), encoding="utf-8").read().strip(), "file": os.path.basename(path)}
                    self.log(f"[{i}/{len(kept)}] {sym} already done, hash verified")
                    continue
                rows = fetch_daily(sym, _ms(START), end_open)
                write_parquet_atomic(rows, path)
                digest = sha256(path)
                with open(self.marker(sym), "w", encoding="utf-8") as f:
                    f.write(digest)
                manifest[sym] = {"sha256": digest, "file": os.path.basename(path), "rows": len(rows),
                                 "first": dt.datetime.fromtimestamp(rows[0][0] / 1000, dt.timezone.utc).date().isoformat() if rows else None,
                                 "last": dt.datetime.fromtimestamp(rows[-1][0] / 1000, dt.timezone.utc).date().isoformat() if rows else None}
                self.log(f"[{i}/{len(kept)}] {sym}: {len(rows)} daily candles {manifest[sym]['first']} .. {manifest[sym]['last']}")
                self.beat(f"{sym} done {i}/{len(kept)}")
            mpath = os.path.join(self.data_dir, "manifest_daily.json")
            json.dump({"built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "last_closed_day_open_ms": end_open, "files": manifest},
                      open(mpath + ".tmp", "w", encoding="utf-8"), indent=1)
            os.replace(mpath + ".tmp", mpath)
            self.log(f"ALL-DONE {len(manifest)}/{len(kept)}")
            open(os.path.join(self.job_dir, "ALL.done"), "w").write(str(len(manifest)))
        finally:
            self._stop.set()
            self.beat("stopped")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", default=r"D:\sindhu_runtime\bt_jobs\BT-DATA")
    ap.add_argument("--data-dir", default=r"D:\sindhu_data\daily")
    a = ap.parse_args()
    Job(a.job_dir, a.data_dir).run()

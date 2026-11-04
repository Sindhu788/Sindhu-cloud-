"""Resumable, rate-limit-aware 1-minute candle downloader (public Binance market-data archive, no API key).

Source: https://data.binance.vision/data/spot/{monthly|daily}/klines/<SYMBOL>/1m/<SYMBOL>-1m-<period>.zip (+ .CHECKSUM). This is the exchange's own
bulk archive: 1 request per coin-month instead of ~44 REST pages, so it is also the polite way to fetch 50 coins x 12 months.
Facts handled: spot archives from 2025-01-01 on use MICROSECOND timestamps (converted to ms); a coin that was not listed yet has no file
(HTTP 404 -> status "absent", not an error); every zip is verified against the published sha256 before it is parsed.
Safety: temp file + atomic rename, finished files read-only and never overwritten, manifest written atomically, progress.json every 30 s,
stops when free disk < 5 GB, below-normal CPU priority, keep-awake only while this process runs (no system setting is changed).
"""
import datetime as dt
import io
import json
import logging
import logging.handlers
import os
import random
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import requests

from data_platform import store

BASE_URL = os.environ.get("SINDHU_DATA_ARCHIVE", "https://data.binance.vision")
EXCHANGE = "binance"
HEADERS = {"User-Agent": "sindhu-data-platform/1.0 (public market data)"}
MIN_FREE_BYTES = int(float(os.environ.get("SINDHU_MIN_FREE_GB", "5")) * (1 << 30))
CSV_NAMES = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
log = logging.getLogger("sindhu.download")


def setup_logging(root):
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(root, "logs", "download.log"), maxBytes=5 << 20, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


# ---------------------------------------------------------------- periods
def month_list(end_month, count):
    y, m = int(end_month[:4]), int(end_month[5:7])
    out = []
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def days_of_month_until(month, last_day):
    y, m = int(month[:4]), int(month[5:7])
    d = dt.date(y, m, 1)
    out = []
    while d.month == m and d <= last_day:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def expected_minutes_month(month):
    y, m = int(month[:4]), int(month[5:7])
    nxt = dt.date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return (nxt - dt.date(y, m, 1)).days * 1440


# ---------------------------------------------------------------- manifest
def replace_with_retry(tmp, path, tries=20):
    """os.replace can fail on Windows while another process (a reader, antivirus) has the target open: retry briefly."""
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.1 * (i + 1))
    os.replace(tmp, path)


class Manifest:
    """One JSON file with one WRITER process. A second process must use its own file (name=...), otherwise each would overwrite the
    other's entries (found on 4 Nov when a validation job and the main download shared manifest.json)."""

    def __init__(self, root, name="manifest.json"):
        self.path = os.path.join(root, "manifest", name)
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.data = {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        self._n = 0

    def get(self, key):
        with self.lock:
            return dict(self.data.get(key) or {}) or None

    def put(self, key, entry):
        with self.lock:
            self.data[key] = entry
            self._n += 1
            self._flush_locked()

    def _flush_locked(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
            f.flush()
            os.fsync(f.fileno())
        replace_with_retry(tmp, self.path)
        if self._n % 100 == 0:                      # rolling backup copy
            try:
                import shutil
                shutil.copyfile(self.path, self.path + ".bak")
            except OSError:
                pass

    def snapshot(self):
        with self.lock:
            return dict(self.data)


# ---------------------------------------------------------------- parsing
def parse_zip_bytes(blob):
    """CSV inside the zip -> dict of numpy arrays with open_time in MILLISECONDS. Raises ValueError on a bad file."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected zip content {names}")
        raw = z.read(names[0])
    t = pacsv.read_csv(io.BytesIO(raw), read_options=pacsv.ReadOptions(column_names=CSV_NAMES),
                       convert_options=pacsv.ConvertOptions(column_types={n: pa.float64() for n in CSV_NAMES} | {"open_time": pa.int64(), "trades": pa.int64(), "close_time": pa.int64()}))
    arrs = {n: t.column(n).to_numpy() for n in CSV_NAMES}
    ot = arrs["open_time"].astype("int64")
    if len(ot) and ot.max() > 10 ** 14:              # microseconds (spot archives since 2025-01-01)
        ot = ot // 1000
    arrs["open_time"] = ot
    return arrs


def clean_and_check(arrs):
    """Sort, drop exact duplicate timestamps (keep first), and reject files that are not minute-aligned. Returns (arrays, n_duplicates)."""
    ot = arrs["open_time"]
    if len(ot) == 0:
        raise ValueError("empty file")
    if np.any(ot % store.MINUTE_MS != 0):
        raise ValueError("timestamps are not aligned to whole minutes")
    order = np.argsort(ot, kind="stable")
    out = {k: v[order] for k, v in arrs.items()}
    keep = np.ones(len(ot), bool)
    keep[1:] = out["open_time"][1:] != out["open_time"][:-1]
    dups = int((~keep).sum())
    if dups:
        out = {k: v[keep] for k, v in out.items()}
    return out, dups


# ---------------------------------------------------------------- downloader
class Downloader:
    def __init__(self, root=None, workers=4, base_url=None, exchange=EXCHANGE, sleep=time.sleep, manifest_name="manifest.json"):
        self.root = root or store.root()
        self.workers = workers
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.exchange = exchange
        self.manifest = Manifest(self.root, manifest_name)
        self.sleep = sleep
        self.stop = threading.Event()
        self.stop_reason = None
        self.lock = threading.Lock()
        self.stats = {"tasks_total": 0, "done": 0, "absent": 0, "failed": 0, "skipped_done": 0, "rows": 0, "bytes": 0, "last_error": None, "phase": "idle"}
        self._t0 = time.time()
        self._local = threading.local()

    # ---- http
    def _session(self):
        s = getattr(self._local, "s", None)
        if s is None:
            s = self._local.s = requests.Session()
            s.headers.update(HEADERS)
        return s

    def _fetch(self, url, tries=6):
        """GET with exponential backoff + jitter. Returns (status, bytes). 404 is a normal answer (status 404, b'')."""
        last = None
        for i in range(tries):
            if self.stop.is_set():
                raise InterruptedError("stopped")
            try:
                r = self._session().get(url, timeout=(10, 60))
                if r.status_code == 200:
                    return 200, r.content
                if r.status_code == 404:
                    return 404, b""
                last = f"HTTP {r.status_code}"
                wait = float(r.headers.get("Retry-After", 0) or 0) or min(60, 2 ** (i + 1))
            except requests.RequestException as e:
                last = repr(e)[:120]
                wait = min(60, 2 ** (i + 1))
            self.sleep(wait * (1 + random.uniform(0, 0.25)))
        raise RuntimeError(f"{url}: gave up after {tries} tries ({last})")

    # ---- one task
    def run_task(self, kind, symbol, period):
        """kind: "month" | "day" (1-minute files) or "month:5m" etc. (NATIVE candles of another interval, used only to validate the resampler)."""
        iv = "1m"
        if ":" in kind:
            kind, iv = kind.split(":")
        key = f"{symbol}/{period}" if iv == "1m" else f"{symbol}/{iv}/{period}"
        ent = self.manifest.get(key)
        if ent and ent.get("status") in ("ok", "absent"):
            with self.lock:
                self.stats["skipped_done"] += 1
            return ent["status"]
        free = _free_bytes(self.root)
        if free < MIN_FREE_BYTES:
            self.stop_reason = f"disk free {free / (1 << 30):.1f} GB < {MIN_FREE_BYTES / (1 << 30):.0f} GB"
            self.stop.set()
            raise InterruptedError(self.stop_reason)
        folder = "monthly" if kind == "month" else "daily"
        name = f"{symbol}-{iv}-{period}.zip"
        url = f"{self.base_url}/data/spot/{folder}/klines/{symbol}/{iv}/{name}"
        path = (store.month_path if kind == "month" else store.day_path)(self.exchange, symbol, period, self.root)
        if iv != "1m":
            path = store.native_path(self.exchange, symbol, iv, period, self.root)
        if os.path.exists(path):                       # finished file from an earlier run whose manifest line was lost: re-verify, never overwrite
            rows, sha = _verify_existing(path)
            self.manifest.put(key, {"status": "ok", "rows": rows, "sha256": sha, "note": "adopted existing file", "checked_at": _now()})
            return "ok"
        st, blob = self._fetch(url)
        if st == 404:
            self.manifest.put(key, {"status": "absent", "checked_at": _now()})
            with self.lock:
                self.stats["absent"] += 1
            return "absent"
        st2, chk = self._fetch(url + ".CHECKSUM")
        want = chk.decode("ascii", "replace").split()[0].lower() if st2 == 200 and chk else None
        import hashlib
        got = hashlib.sha256(blob).hexdigest()
        if want and want != got:
            raise RuntimeError(f"{name}: checksum mismatch (download corrupted)")
        arrs, dups = clean_and_check(parse_zip_bytes(blob))
        table = store.table_from_arrays(arrs)
        rows, sha = store.write_atomic(path, table)
        ot = arrs["open_time"]
        self.manifest.put(key, {"status": "ok", "kind": kind, "rows": rows, "sha256": sha, "zip_sha256": got, "zip_verified": bool(want),
                                "duplicates_dropped": dups, "first_ts": int(ot[0]), "last_ts": int(ot[-1]), "source": url, "downloaded_at": _now()})
        with self.lock:
            self.stats["done"] += 1
            self.stats["rows"] += rows
            self.stats["bytes"] += len(blob)
        return "ok"

    # ---- plan + run
    def run(self, tasks, phase, progress_cb=None):
        """tasks: list of (kind, symbol, period). Blocks until all done / stopped. Failed tasks are retried once at the end."""
        self.stats["phase"] = phase
        with self.lock:
            self.stats["tasks_total"] += len(tasks)
        failed = []

        def work(t):
            if self.stop.is_set():
                return
            try:
                self.run_task(*t)
            except InterruptedError:
                return
            except Exception as e:
                with self.lock:
                    self.stats["last_error"] = f"{t[1]} {t[2]}: {e}"[:200]
                log.warning("task failed %s: %s", t, e)
                failed.append(t)

        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="dl") as pool:
            list(pool.map(work, tasks))
        retry, failed[:] = list(failed), []
        if retry and not self.stop.is_set():
            self.sleep(20)
            with ThreadPoolExecutor(max_workers=max(1, self.workers // 2)) as pool:
                list(pool.map(work, retry))
        with self.lock:
            self.stats["failed"] += len(failed)
        return failed

    def progress(self):
        s = dict(self.stats)
        el = max(1.0, time.time() - self._t0)
        finished = s["done"] + s["absent"] + s["skipped_done"] + s["failed"]
        s["finished"] = finished
        s["percent"] = round(100.0 * finished / s["tasks_total"], 1) if s["tasks_total"] else 0.0
        rate = finished / el
        s["eta_minutes"] = round((s["tasks_total"] - finished) / rate / 60, 1) if rate > 0 and s["tasks_total"] > finished else 0.0
        s["elapsed_minutes"] = round(el / 60, 1)
        s["stop_reason"] = self.stop_reason
        s["updated_at"] = _now()
        s["disk_free_gb"] = round(_free_bytes(self.root) / (1 << 30), 1)
        s["pid"] = os.getpid()
        return s

    def write_progress(self, extra=None):
        p = self.progress()
        if extra:
            p.update(extra)
        path = os.path.join(self.root, "manifest", "progress.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=1)
        replace_with_retry(tmp, path)
        return p


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _free_bytes(path):
    import shutil
    p = path
    while not os.path.exists(p):
        p = os.path.dirname(p) or "."
    return shutil.disk_usage(p).free


def _verify_existing(path):
    t = store.read_table(path)
    return t.num_rows, store.sha256_file(path)

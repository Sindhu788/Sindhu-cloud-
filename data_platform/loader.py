"""Backtest data loader (Step 12). Serves CLOSED candles only, from the protected dataset, with three guarantees:
1. LOOKAHEAD: a candle is visible only after it has closed (open_time + timeframe <= as_of); resampled candles need all their minutes.
2. SEALED HOLDOUT: the final HOLDOUT_MONTHS complete months are never served. A request that reaches into them raises HoldoutAccessError, unless the
   explicit audited "final exam" is used (allow_final_exam=True AND the environment variable SINDHU_FINAL_EXAM=I_ACCEPT_ONE_LOOK). Every such
   access is appended to manifest/holdout_access.log and counted. The holdout boundary is written ONCE to manifest/protocol.json and never changes.
3. REPRODUCIBILITY: every frame carries attrs["data_version"], a hash of the manifest entries (file sha256) of the files that were read.
Returns pandas frames shaped like the existing backtest engine's: UTC DatetimeIndex, columns open, high, low, close, volume, quote_volume, trades."""
import datetime as dt
import hashlib
import json
import os
import threading
import time

import numpy as np

from data_platform import resample, store
from data_platform.downloader import Manifest

HOLDOUT_MONTHS = 2
FINAL_EXAM_PHRASE = "I_ACCEPT_ONE_LOOK"
OUT_COLUMNS = ["open", "high", "low", "close", "volume", "quote_volume", "trades"]
TF_MS = {"1m": 60_000, **{k: v * 60_000 for k, v in resample.TIMEFRAMES_MIN.items()}}


class HoldoutAccessError(RuntimeError):
    pass


def _month_start_ms(month):
    return int(dt.datetime(int(month[:4]), int(month[5:7]), 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _shift_month(month, n):
    y, m = int(month[:4]), int(month[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


class CandleLoader:
    def __init__(self, root=None, exchange="binance"):
        self.root = root or store.root()
        self.exchange = exchange
        self.manifest = Manifest(self.root)
        self._lock = threading.Lock()
        self._cache = {}
        self.protocol = self._protocol()

    # ---- protocol file (the holdout boundary is fixed once)
    def _protocol(self):
        path = os.path.join(self.root, "manifest", "protocol.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        months = sorted({k.split("/")[1] for k, v in self.manifest.snapshot().items() if v.get("status") == "ok" and len(k.split("/")) == 2 and len(k.split("/")[1]) == 7})
        if not months:
            return {"holdout_start": None}
        last = months[-1]
        first_holdout = _shift_month(last, -(HOLDOUT_MONTHS - 1))
        proto = {"created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "holdout_months": HOLDOUT_MONTHS,
                 "holdout_first_month": first_holdout, "holdout_last_month": last, "holdout_start_ms": _month_start_ms(first_holdout),
                 "holdout_start": f"{first_holdout}-01", "note": "sealed final exam window; fixed when the dataset was first loaded; never edited"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(proto, f, indent=1)
        os.replace(tmp, path)
        return proto

    @property
    def holdout_start_ms(self):
        return self.protocol.get("holdout_start_ms")

    def holdout_access_count(self):
        p = os.path.join(self.root, "manifest", "holdout_access.log")
        return sum(1 for _ in open(p, encoding="utf-8")) if os.path.exists(p) else 0

    def _log_holdout(self, who, symbol, tf, start, end):
        p = os.path.join(self.root, "manifest", "holdout_access.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "who": who, "symbol": symbol, "tf": tf, "start": start, "end": end}) + "\n")

    # ---- files
    def _months_for(self, symbol, start_ms, end_ms):
        out = []
        for k, v in self.manifest.snapshot().items():
            parts = k.split("/")
            if parts[0] != symbol or len(parts) != 2 or v.get("status") != "ok":
                continue
            p = parts[1]
            if len(p) == 7:
                s = _month_start_ms(p)
                e = _month_start_ms(_shift_month(p, 1))
            else:
                s = int(dt.datetime.fromisoformat(p).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                e = s + 86_400_000
            if e > start_ms and s < end_ms:
                out.append((p, s, e, v.get("sha256")))
        monthly = {p for p, *_ in out if len(p) == 7}
        # a daily file is used only for days of months that have no finished monthly file
        return sorted((x for x in out if len(x[0]) == 7 or x[0][:7] not in monthly), key=lambda x: x[1])

    def _load_1m(self, symbol, start_ms, end_ms):
        parts, shas = [], []
        for p, s, e, sha in self._months_for(symbol, start_ms, end_ms):
            path = store.month_path(self.exchange, symbol, p, self.root) if len(p) == 7 else store.day_path(self.exchange, symbol, p, self.root)
            parts.append(store.to_arrays(store.read_table(path)))
            shas.append(f"{symbol}/{p}:{sha}")
        if not parts:
            return {c: np.array([], dtype="float64") for c in store.COLUMNS}, shas
        a = {c: np.concatenate([x[c] for x in parts]) for c in store.COLUMNS}
        keep = (a["open_time"] >= start_ms) & (a["open_time"] < end_ms)
        return {c: v[keep] for c, v in a.items()}, shas

    # ---- public API
    def load(self, symbol, tf="1m", start=None, end=None, as_of_ms=None, allow_final_exam=False, who="backtest"):
        """start/end: UTC datetimes or ms (end exclusive). Default end = the holdout boundary. Returns a pandas DataFrame (closed candles only)."""
        import pandas as pd
        if tf not in TF_MS:
            raise ValueError(f"unknown timeframe {tf}")
        h = self.holdout_start_ms
        s_ms = self._ms(start, 0)
        e_ms = self._ms(end, h if h is not None else int(time.time() * 1000))
        exam = False
        if h is not None and e_ms > h:
            if allow_final_exam and os.environ.get("SINDHU_FINAL_EXAM") == FINAL_EXAM_PHRASE:
                exam = True
                self._log_holdout(who, symbol, tf, s_ms, e_ms)
            else:
                raise HoldoutAccessError(f"the window reaches into the sealed holdout (from {self.protocol.get('holdout_start')}); "
                                         "use the audited final exam (allow_final_exam=True and SINDHU_FINAL_EXAM) only once, at the very end")
        as_of = as_of_ms if as_of_ms is not None else int(time.time() * 1000)
        # candles that have not closed by `as_of` are invisible: cut the window so that open_time + tf <= as_of
        e_eff = min(e_ms, as_of - TF_MS[tf] + 1)
        key = (symbol, tf, s_ms, e_eff, exam)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit.copy()
        a, shas = self._load_1m(symbol, s_ms - (TF_MS[tf] if tf != "1m" else 0), e_eff + TF_MS[tf])
        if tf != "1m":
            a = resample.resample(a, tf)
        ot = a["open_time"]
        keep = (ot >= s_ms) & (ot + TF_MS[tf] <= as_of) & (ot < e_ms)
        df = pd.DataFrame({c: a[c][keep] for c in OUT_COLUMNS}, index=pd.to_datetime(ot[keep], unit="ms", utc=True))
        df.index.name = None
        df.attrs["data_version"] = hashlib.sha256("|".join(shas).encode()).hexdigest()[:16]
        df.attrs.update(symbol=symbol, timeframe=tf, holdout_touched=exam)
        with self._lock:
            if len(self._cache) > 16:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = df
        return df.copy()

    def data_version(self, symbols=None):
        items = sorted((k, v.get("sha256")) for k, v in self.manifest.snapshot().items() if v.get("status") == "ok" and (not symbols or k.split("/")[0] in symbols))
        return hashlib.sha256(json.dumps(items).encode()).hexdigest()[:16]

    @staticmethod
    def _ms(v, default):
        if v is None:
            return int(default)
        if isinstance(v, (int, np.integer)):
            return int(v)
        if isinstance(v, str):
            v = dt.datetime.fromisoformat(v)
        if v.tzinfo is None:
            v = v.replace(tzinfo=dt.timezone.utc)
        return int(v.timestamp() * 1000)

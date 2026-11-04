"""Data quality checks (Step 10). Policy: NEVER fabricate or forward-fill candles; incomplete windows are only flagged.
Per coin and month: expected vs actual minutes, gaps (listed), duplicates removed at download, monotonic/aligned timestamps, zero-volume
candles, OHLC sanity (low <= open,close <= high, prices > 0) and extreme-spike candles (1-minute close/open move above SPIKE_PCT or
high/low range above RANGE_PCT) for review."""
import datetime as dt
import json
import os

import numpy as np

from data_platform import store
from data_platform.downloader import expected_minutes_month

SPIKE_PCT = 10.0       # |close/open - 1| above 10 % inside ONE minute
RANGE_PCT = 15.0       # (high/low - 1) above 15 % inside ONE minute
MAX_MISSING_PCT = 0.5  # a coin-month with more than 0.5 % missing minutes does not pass


def check_arrays(a, expected_rows=None):
    ot = a["open_time"]
    n = int(len(ot))
    res = {"rows": n}
    res["monotonic"] = bool(np.all(np.diff(ot) > 0)) if n > 1 else True
    res["aligned_utc_minute"] = bool(np.all(ot % store.MINUTE_MS == 0))
    if expected_rows is not None:
        res["expected_rows"] = expected_rows
        res["missing_minutes"] = max(0, expected_rows - n)
        res["missing_pct"] = round(100.0 * res["missing_minutes"] / expected_rows, 3) if expected_rows else 0.0
    d = np.diff(ot) // store.MINUTE_MS
    gaps = np.where(d > 1)[0]
    res["gap_count"] = int(len(gaps))
    res["largest_gap_minutes"] = int(d[gaps].max() - 1) if len(gaps) else 0
    res["gaps_first"] = [[int(ot[i]), int(d[i] - 1)] for i in gaps[:5]]
    o, h, l, c, v = (a[k] for k in ("open", "high", "low", "close", "volume"))
    bad = (l > np.minimum(o, c) + 1e-12) | (h < np.maximum(o, c) - 1e-12) | (l > h) | (np.minimum.reduce([o, h, l, c]) <= 0) | ~np.isfinite(o + h + l + c)
    res["ohlc_violations"] = int(bad.sum())
    res["zero_volume"] = int((v <= 0).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        spike = (np.abs(c / o - 1) * 100 > SPIKE_PCT) | ((h / l - 1) * 100 > RANGE_PCT)
    res["spikes"] = int(np.nansum(spike))
    res["spike_examples"] = [int(ot[i]) for i in np.where(spike)[0][:3]]
    return res


def month_ok(r):
    return r["monotonic"] and r["aligned_utc_minute"] and r["ohlc_violations"] == 0 and r.get("missing_pct", 0.0) <= MAX_MISSING_PCT


def check_dataset(symbols, months, exchange="binance", base=None):
    """Checks every present monthly file. Returns {"coins": {sym: {month: result|'absent'|'missing'}}, "summary": {...}}."""
    base = base or store.root()
    from data_platform.downloader import Manifest
    man = Manifest(base).snapshot()
    out, total, ok, present = {}, 0, 0, 0
    for s in symbols:
        out[s] = {}
        for m in months:
            ent = man.get(f"{s}/{m}")
            if not ent:
                out[s][m] = "missing"
                continue
            if ent["status"] == "absent":
                out[s][m] = "absent"
                continue
            path = store.month_path(exchange, s, m, base)
            t = store.read_table(path)
            r = check_arrays(store.to_arrays(t), expected_minutes_month(m))
            r["ok"] = month_ok(r)
            out[s][m] = r
            total += 1
            present += 1
            ok += r["ok"]
    full = sum(1 for s in symbols if sum(1 for m in months if isinstance(out[s][m], dict)) >= len(months) - 1)
    summary = {"symbols": len(symbols), "months": len(months), "files_checked": present, "files_ok": ok,
               "share_ok": round(ok / present, 4) if present else 0.0,
               "coins_with_nearly_full_history": full, "share_coins_full": round(full / len(symbols), 3) if symbols else 0.0,
               "total_rows": int(sum(r["rows"] for s in out.values() for r in s.values() if isinstance(r, dict))),
               "total_missing_minutes": int(sum(r.get("missing_minutes", 0) for s in out.values() for r in s.values() if isinstance(r, dict))),
               "total_ohlc_violations": int(sum(r["ohlc_violations"] for s in out.values() for r in s.values() if isinstance(r, dict))),
               "total_spikes": int(sum(r["spikes"] for s in out.values() for r in s.values() if isinstance(r, dict)))}
    summary["verdict"] = "PASS" if (summary["share_ok"] >= 0.9 and summary["share_coins_full"] >= 0.8) else "FAIL"
    summary["rule"] = "PASS = at least 90 % of present coin-month files have <= 0.5 % missing minutes, no OHLC violations, monotonic UTC-aligned time, and at least 80 % of coins have all but at most one month"
    return {"coins": out, "summary": summary, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def save_report(report, name, base=None):
    d = os.path.join(base or store.root(), "manifest")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f)
    os.replace(tmp, path)
    return path

"""Master plan B2 quality checks for the native daily klines in D:\\sindhu_data\\daily (bt venv).

Per symbol: rows, first/last day, gaps (missing days), duplicates, zero-volume days, OHLC sanity (low <= open,close <= high, prices > 0),
UTC alignment (every open_time at 00:00 UTC), last candle closed (open_time + 1 day <= now), SHA-256 vs the job markers.
Cross-check: daily bars resampled from the existing Binance 1m dataset (loader, closed candles only, stops at the sealed holdout boundary
by default) vs the native daily bars on overlapping days; any open/high/low/close difference > 0.1 % is listed.
Usage: python tools/daily_quality.py [--write]   (--write appends the section to docs/DATA_QUALITY.md)"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pyarrow.parquet as pq

DATA = r"D:\sindhu_data\daily"
JOB = r"D:\sindhu_runtime\bt_jobs\BT-DATA"
DAY = 86_400_000


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check(sym):
    path = os.path.join(DATA, f"{sym}_1d.parquet")
    t = pq.read_table(path).to_pydict()
    ot = np.array(t["open_time"], dtype="int64")
    o, h, l, c, v = (np.array(t[k], dtype="float64") for k in ("open", "high", "low", "close", "volume"))
    d = np.diff(ot)
    marker = os.path.join(JOB, f"{sym}.done")
    return {
        "symbol": sym, "rows": int(len(ot)),
        "first": dt.datetime.fromtimestamp(ot[0] / 1000, dt.timezone.utc).date().isoformat(),
        "last": dt.datetime.fromtimestamp(ot[-1] / 1000, dt.timezone.utc).date().isoformat(),
        "missing_days": int(((d // DAY) - 1)[d > DAY].sum()), "duplicates": int((d == 0).sum()), "unsorted": int((d < 0).sum()),
        "zero_volume_days": int((v == 0).sum()),
        "ohlc_bad": int(((l > np.minimum(o, c)) | (h < np.maximum(o, c)) | (l <= 0) | (h < l)).sum()),
        "not_utc_midnight": int((ot % DAY != 0).sum()),
        "last_closed": bool(ot[-1] + DAY <= int(time.time() * 1000)),
        "hash_ok": os.path.exists(marker) and open(marker, encoding="utf-8").read().strip() == sha(path),
        "_arrays": (ot, o, h, l, c),
    }


def cross_check(sym, arrays, tol=0.001):
    """Overlap with daily bars resampled from the 1m dataset (pre-holdout only)."""
    try:
        from data_platform.loader import CandleLoader as Loader
    except Exception as e:
        return {"status": f"NOT RUN ({type(e).__name__})"}
    try:
        df = Loader().load(sym, "1d", who="daily_quality_crosscheck")
    except Exception as e:
        return {"status": f"NOT RUN ({type(e).__name__}: {str(e)[:80]})"}
    if df is None or len(df) == 0:
        return {"status": "no 1m overlap"}
    ot, o, h, l, c = arrays
    idx = {int(t): i for i, t in enumerate(ot)}
    diffs, n = [], 0
    for ts, row in df.iterrows():
        k = int(ts.value // 1_000_000) if hasattr(ts, "value") else int(ts)
        i = idx.get(k)
        if i is None:
            continue
        n += 1
        for name, nat in (("open", o[i]), ("high", h[i]), ("low", l[i]), ("close", c[i])):
            rv = float(row[name])
            if nat > 0 and abs(rv - nat) / nat > tol:
                diffs.append({"day": dt.datetime.fromtimestamp(k / 1000, dt.timezone.utc).date().isoformat(), "field": name,
                              "native": nat, "from_1m": rv, "diff_pct": round(abs(rv - nat) / nat * 100, 3)})
    return {"status": "ok", "overlap_days": n, "differences_over_0.1pct": len(diffs), "examples": diffs[:5]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    uni = json.load(open(os.path.join(DATA, "universe_v2.json"), encoding="utf-8"))
    rows = []
    for s in uni["symbols"]:
        r = check(s["symbol"])
        r["cross"] = cross_check(s["symbol"], r.pop("_arrays"))
        rows.append(r)
    lines = [f"\n## Daily klines for the V2 benchmark (master plan B2), checked {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC",
             "Source: native Binance spot 1d klines (public REST), `D:\\sindhu_data\\daily`, 20 symbols from the frozen rule in "
             "docs/BENCHMARK_PREREGISTRATION_V2.md. Command: `python tools/daily_quality.py --write` (bt venv).", "",
             "| Symbol | Rows | First | Last | Missing days | Dupes | Zero-vol days | OHLC bad | Not 00:00 UTC | Last closed | Hash | 1m overlap days | >0.1 % diffs |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cr = r["cross"]
        lines.append(f"| {r['symbol']} | {r['rows']} | {r['first']} | {r['last']} | {r['missing_days']} | {r['duplicates']} | {r['zero_volume_days']} | "
                     f"{r['ohlc_bad']} | {r['not_utc_midnight']} | {'yes' if r['last_closed'] else 'NO'} | {'OK' if r['hash_ok'] else 'MISMATCH'} | "
                     f"{cr.get('overlap_days', cr['status'])} | {cr.get('differences_over_0.1pct', '-')} |")
    ex = [(r["symbol"], e) for r in rows for e in r["cross"].get("examples", [])]
    if ex:
        lines.append("\nExamples of differences > 0.1 % (native vs resampled from 1m):")
        lines += [f"- {s} {e['day']} {e['field']}: native {e['native']}, from 1m {e['from_1m']} ({e['diff_pct']} %)" for s, e in ex[:20]]
    total_bad = sum(r["missing_days"] + r["duplicates"] + r["ohlc_bad"] + r["not_utc_midnight"] + (0 if r["hash_ok"] else 1) + (0 if r["last_closed"] else 1) for r in rows)
    lines.append(f"\nResult: {'PASS' if total_bad == 0 else 'ISSUES FOUND (see table)'}; zero-volume days are listed, not removed.")
    text = "\n".join(lines) + "\n"
    print(text)
    if a.write:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "DATA_QUALITY.md"), "a", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()

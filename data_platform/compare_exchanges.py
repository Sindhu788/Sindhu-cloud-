"""Step 13: how different are Binance candles (our dataset) from another exchange's candles? OKX (the venue Cloud trades on) is not reachable from this PC,
so Bybit's public spot klines are used as a stand-in for 'another venue'. 1h candles, last 30 days of October 2026, top 10 coins.
Usage: python -m data_platform.compare_exchanges"""
import json
import sys
import time

import numpy as np
import requests

from data_platform import resample, store, universe

H = {"User-Agent": "sindhu-data-platform/1.0 (public market data)"}


def bybit_1h(symbol, start_ms, end_ms):
    out, cur = {}, start_ms
    while cur < end_ms:
        r = requests.get("https://api.bybit.com/v5/market/kline", params={"category": "spot", "symbol": symbol, "interval": "60", "start": cur, "end": end_ms, "limit": 1000},
                         headers=H, timeout=20)
        r.raise_for_status()
        rows = r.json()["result"]["list"]
        if not rows:
            break
        for t, o, h, l, c, v, _ in rows:
            out[int(t)] = (float(o), float(h), float(l), float(c), float(v))
        newest = max(int(x[0]) for x in rows)
        if newest + 3_600_000 <= cur:
            break
        cur = max(newest, cur) + 3_600_000
        time.sleep(0.2)
    return out


def main():
    root = store.root()
    uni = universe.load_latest(root)
    syms = uni["symbols"][:10]
    start_ms, end_ms = 1_790_812_800_000 - 0, 0
    import datetime as dt
    start_ms = int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    end_ms = int(dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    rows = []
    for s in syms:
        a = store.to_arrays(store.read_table(store.month_path("binance", s, "2026-10", root)))
        h1 = resample.resample(a, "1h")
        try:
            by = bybit_1h(s, start_ms, end_ms)
        except Exception as e:
            rows.append({"symbol": s, "error": str(e)[:80]})
            continue
        ts = [int(t) for t in h1["open_time"] if int(t) in by]
        if len(ts) < 100:
            rows.append({"symbol": s, "error": f"only {len(ts)} common candles"})
            continue
        ix = {int(t): i for i, t in enumerate(h1["open_time"])}
        bc = np.array([h1["close"][ix[t]] for t in ts]); yc = np.array([by[t][3] for t in ts])
        bh = np.array([h1["high"][ix[t]] for t in ts]); yh = np.array([by[t][1] for t in ts])
        bl = np.array([h1["low"][ix[t]] for t in ts]); yl = np.array([by[t][2] for t in ts])
        bv = np.array([h1["volume"][ix[t]] for t in ts]); yv = np.array([by[t][4] for t in ts])
        rb, ry = np.diff(np.log(bc)), np.diff(np.log(yc))
        rows.append({"symbol": s, "candles": len(ts), "close_mean_abs_diff_bps": round(float(np.mean(np.abs(bc / yc - 1)) * 1e4), 2),
                     "close_max_abs_diff_bps": round(float(np.max(np.abs(bc / yc - 1)) * 1e4), 1),
                     "range_diff_mean_bps": round(float(np.mean(np.abs((bh - bl) / bc - (yh - yl) / yc)) * 1e4), 2),
                     "return_corr": round(float(np.corrcoef(rb, ry)[0, 1]), 5), "volume_ratio_median": round(float(np.median(bv / np.maximum(yv, 1e-12))), 2)})
    json.dump(rows, open(f"{root}/manifest/exchange_comparison.json", "w"), indent=1)
    print("| Coin | common 1h candles | mean |close diff| (bps) | max (bps) | mean range diff (bps) | return correlation | median volume ratio Binance/Bybit |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        if "error" in r:
            print(f"| {r['symbol']} | - | {r['error']} | | | | |")
        else:
            print(f"| {r['symbol']} | {r['candles']} | {r['close_mean_abs_diff_bps']} | {r['close_max_abs_diff_bps']} | {r['range_diff_mean_bps']} | {r['return_corr']} | {r['volume_ratio_median']} |")


if __name__ == "__main__":
    main()

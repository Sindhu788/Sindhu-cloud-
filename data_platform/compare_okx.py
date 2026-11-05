"""Day 6 Step 15: Binance (our dataset) vs OKX US public 1h candles, August 2026 (inside the development window; the sealed holdout is not read).
IMPORTANT: Cloud trades on OKX GLOBAL (www.okx.com), which is not reachable from this PC; us.okx.com is a different OKX site and may be a separate order
book, so this is a stand-in, NOT the Cloud venue. Public endpoint only, 0.3 s between requests, no credentials.
Usage: python -m data_platform.compare_okx"""
import datetime as dt
import json
import time

import numpy as np
import requests

from data_platform import resample, store, universe

H = {"User-Agent": "sindhu-data-platform/1.0 (public market data)"}
URL = "https://us.okx.com/api/v5/market/history-candles"


def okx_1h(inst, start_ms, end_ms):
    out, after = {}, end_ms
    for _ in range(20):
        r = requests.get(URL, params={"instId": inst, "bar": "1H", "limit": 100, "after": after}, headers=H, timeout=20)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "0":
            raise RuntimeError(f"okx code {j.get('code')} {str(j.get('msg'))[:60]}")
        rows = j["data"]
        if not rows:
            break
        for x in rows:
            t = int(x[0])
            if start_ms <= t < end_ms:
                out[t] = tuple(float(v) for v in x[1:6])      # open, high, low, close, volume(base)
        oldest = min(int(x[0]) for x in rows)
        if oldest <= start_ms:
            break
        after = oldest
        time.sleep(0.3)
    return out


def main():
    root = store.root()
    syms = universe.load_latest(root)["symbols"][:10]
    start_ms = int(dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    end_ms = int(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    rows = []
    for s in syms:
        inst = s[:-4] + "-" + s[-4:]
        try:
            ok = okx_1h(inst, start_ms, end_ms)
        except Exception as e:
            rows.append({"symbol": s, "error": str(e)[:80]}); continue
        a = store.to_arrays(store.read_table(store.month_path("binance", s, "2026-08", root)))
        h1 = resample.resample(a, "1h")
        ix = {int(t): i for i, t in enumerate(h1["open_time"])}
        ts = [t for t in sorted(ok) if t in ix]
        if len(ts) < 100:
            rows.append({"symbol": s, "error": f"only {len(ts)} common candles"}); continue
        g = lambda k: np.array([h1[k][ix[t]] for t in ts])
        bc, bh, bl, bv = g("close"), g("high"), g("low"), g("volume")
        yo = np.array([ok[t] for t in ts]); yc, yh, yl, yv = yo[:, 3], yo[:, 1], yo[:, 2], yo[:, 4]
        rows.append({"symbol": s, "candles": len(ts), "close_mean_abs_diff_bps": round(float(np.mean(np.abs(bc / yc - 1)) * 1e4), 2),
                     "close_max_abs_diff_bps": round(float(np.max(np.abs(bc / yc - 1)) * 1e4), 1),
                     "range_diff_mean_bps": round(float(np.mean(np.abs((bh - bl) / bc - (yh - yl) / yc)) * 1e4), 2),
                     "return_corr": round(float(np.corrcoef(np.diff(np.log(bc)), np.diff(np.log(yc)))[0, 1]), 5),
                     "volume_ratio_median": round(float(np.median(bv / np.maximum(yv, 1e-12))), 2)})
    json.dump(rows, open(f"{root}/manifest/okx_us_comparison.json", "w"), indent=1)
    print("| Coin | common 1h candles | mean abs close diff (bps) | max (bps) | mean range diff (bps) | return corr | median volume ratio Binance/OKX-US |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['symbol']} | - | {r['error']} | | | | |" if "error" in r else
              f"| {r['symbol']} | {r['candles']} | {r['close_mean_abs_diff_bps']} | {r['close_max_abs_diff_bps']} | {r['range_diff_mean_bps']} | {r['return_corr']} | {r['volume_ratio_median']} |")


if __name__ == "__main__":
    main()

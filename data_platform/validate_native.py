"""Step 11: compare candles resampled from our 1-minute data with the exchange's NATIVE candles of the same interval.
Usage: python -m data_platform.validate_native [coins=5] [months=3]   (runs where pandas is blocked: numpy + pyarrow only)"""
import json
import os
import sys

import numpy as np

from data_platform import downloader, resample, store, universe

TFS = ["5m", "15m", "1h", "4h", "1d"]


def compare(res, nat):
    """res/nat: dicts of arrays for one coin-month-timeframe. Returns counts and differences."""
    r_t, n_t = res["open_time"], nat["open_time"]
    common, ri, ni = np.intersect1d(r_t, n_t, return_indices=True)
    out = {"native_windows": int(len(n_t)), "resampled_windows": int(len(r_t)), "common": int(len(common)),
           "only_native": int(len(n_t) - len(common)), "only_resampled": int(len(r_t) - len(common))}
    if not len(common):
        return out
    exact = np.ones(len(common), bool)
    maxrel = 0.0
    for k in ("open", "high", "low", "close"):
        a, b = res[k][ri], nat[k][ni]
        exact &= (a == b)
        maxrel = max(maxrel, float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-12))))
    out["ohlc_identical"] = int(exact.sum())
    out["ohlc_identical_share"] = round(float(exact.mean()), 6)
    out["ohlc_max_rel_diff"] = maxrel
    v1, v2 = res["volume"][ri], nat["volume"][ni]
    out["volume_max_rel_diff"] = float(np.max(np.abs(v1 - v2) / np.maximum(np.abs(v2), 1e-12)))
    out["volume_identical_share"] = round(float(np.mean(np.isclose(v1, v2, rtol=1e-9, atol=1e-9))), 6)
    out["trades_identical_share"] = round(float(np.mean(res["trades"][ri] == nat["trades"][ni])), 6)
    return out


def main(argv):
    n_coins = int(argv[0]) if argv else 5
    n_months = int(argv[1]) if len(argv) > 1 else 3
    root = store.root()
    uni = universe.load_latest(root)
    import datetime as dt
    today = dt.datetime.now(dt.timezone.utc).date()
    end_month = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    months = downloader.month_list(end_month, n_months)
    syms = uni["symbols"][:n_coins]
    d = downloader.Downloader(root=root, workers=3)
    d.run([(f"month:{tf}", s, m) for s in syms for m in months for tf in TFS], "native")
    rows = {}
    for tf in TFS:
        agg = {"native_windows": 0, "resampled_windows": 0, "common": 0, "only_native": 0, "only_resampled": 0, "identical": 0,
               "max_rel": 0.0, "vol_max_rel": 0.0, "vol_identical": 0, "files": 0}
        for s in syms:
            for m in months:
                p1, pn = store.month_path("binance", s, m, root), store.native_path("binance", s, tf, m, root)
                if not (os.path.exists(p1) and os.path.exists(pn)):
                    continue
                one = store.to_arrays(store.read_table(p1))
                nat = store.to_arrays(store.read_table(pn))
                c = compare(resample.resample(one, tf), nat)
                agg["files"] += 1
                for k in ("native_windows", "resampled_windows", "common", "only_native", "only_resampled"):
                    agg[k] += c[k]
                if c["common"]:
                    agg["identical"] += c["ohlc_identical"]
                    agg["vol_identical"] += int(round(c["volume_identical_share"] * c["common"]))
                    agg["max_rel"] = max(agg["max_rel"], c["ohlc_max_rel_diff"])
                    agg["vol_max_rel"] = max(agg["vol_max_rel"], c["volume_max_rel_diff"])
        rows[tf] = agg
    path = os.path.join(root, "manifest", "native_validation.json")
    json.dump({"coins": syms, "months": months, "by_timeframe": rows}, open(path, "w"), indent=1)
    print("| Timeframe | coin-months | native windows | common | only native | only resampled | OHLC identical | volume identical | max OHLC rel diff | max volume rel diff |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for tf, a in rows.items():
        c = max(a["common"], 1)
        print(f"| {tf} | {a['files']} | {a['native_windows']} | {a['common']} | {a['only_native']} | {a['only_resampled']} | "
              f"{100 * a['identical'] / c:.3f} % | {100 * a['vol_identical'] / c:.3f} % | {a['max_rel']:.2e} | {a['vol_max_rel']:.2e} |")
    print("written", path)


if __name__ == "__main__":
    main(sys.argv[1:])

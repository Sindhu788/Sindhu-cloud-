"""Compare '[candle-fp]' lines copied from the Render logs (what Cloud saw on OKX) with the Binance dataset. Price-fidelity check only (no strategy
performance is computed); every read of a sealed-window month is recorded in manifest/holdout_access.log through the loader.
Usage: python tools/compare_fingerprints.py render_log.txt     (run with the venv that has pyarrow)"""
import re, sys
import numpy as np

LINE = re.compile(r"\[candle-fp\] (\S+) (\S+) (\S+) t=(\d+) o=(\S+) h=(\S+) l=(\S+) c=(\S+) v=(\S+) fp=(\w+)")


def parse(text):
    out = []
    for m in LINE.finditer(text):
        ex, sym, tf, t, o, h, l, c, v, fp = m.groups()
        out.append({"exchange": ex, "symbol": sym.replace("/", ""), "tf": tf, "t": int(t), "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": float(v), "fp": fp})
    return out


def compare(rows, candle_lookup):
    """candle_lookup(symbol, tf, t) -> (o, h, l, c, v) from the dataset or None. Returns per-row difference in basis points of the close."""
    res = []
    for r in rows:
        ref = candle_lookup(r["symbol"], r["tf"], r["t"])
        if ref is None:
            res.append({**r, "status": "no reference"}); continue
        res.append({**r, "status": "ok", "close_bps": (r["c"] / ref[3] - 1) * 1e4, "range_bps": ((r["h"] - r["l"]) / r["c"] - (ref[1] - ref[2]) / ref[3]) * 1e4})
    return res


if __name__ == "__main__":
    from data_platform import resample
    from data_platform.loader import CandleLoader
    rows = parse(open(sys.argv[1], encoding="utf-8", errors="replace").read())
    L = CandleLoader(); cache = {}

    def lookup(sym, tf, t):
        if (sym, tf) not in cache:
            lo, hi = min(r["t"] for r in rows if r["symbol"] == sym) - 3_600_000, max(r["t"] for r in rows if r["symbol"] == sym) + 86_400_000
            L._log_holdout("fingerprint-compare", sym, tf, lo, hi)
            a, _ = L._load_1m(sym, lo, hi)
            cache[(sym, tf)] = resample.resample(a, tf) if tf != "1m" else a
        h = cache[(sym, tf)]
        i = np.searchsorted(h["open_time"], t)
        if i < len(h["open_time"]) and h["open_time"][i] == t:
            return (h["open"][i], h["high"][i], h["low"][i], h["close"][i], h["volume"][i])
        return None

    out = compare(rows, lookup); ok = [r for r in out if r["status"] == "ok"]
    print(f"{len(rows)} fingerprint lines, {len(ok)} matched to the dataset")
    if ok:
        d = np.abs([r["close_bps"] for r in ok]); print(f"close difference: mean {d.mean():.2f} bps, median {np.median(d):.2f}, max {d.max():.1f}")

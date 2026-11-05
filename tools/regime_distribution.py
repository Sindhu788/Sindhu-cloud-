"""Day 6 Step 13: how often would the confluence 'regime' factor see each regime? Uses the REAL paper_trading.regime.classify_regime on 72-hour windows of
1h Binance candles (stand-in for OKX) from the development window, every 4th hour, 10 coins. Read-only."""
import collections, json, sys
from paper_trading import regime
from data_platform.loader import CandleLoader
L = CandleLoader()
syms = json.load(open(r"D:\sindhu_data\universe\universe_v2.json"))["symbols"][:10] if False else None
from data_platform import universe
syms = universe.load_latest(L.root)["symbols"][:10]
start, end = 1761955200000, L.holdout_start_ms
out = {}
tot = collections.Counter()
for s in syms:
    df = L.load(s, "1h", start=start, end=end)
    cnt = collections.Counter()
    for i in range(80, len(df), 4):
        w = df.iloc[i - 72:i]
        regime.get_ohlcv = lambda *a, _w=w, **k: _w
        r = regime.classify_regime("x", s)
        cnt[r["regime"] if r else "none"] += 1
    out[s] = dict(cnt); tot.update(cnt)
n = sum(tot.values())
print({k: f"{100*v/n:.1f}%" for k, v in tot.items()}, "windows:", n)
json.dump({"per_coin": out, "total": dict(tot)}, open(r"D:\sindhu_data\experiments\regime_distribution.json", "w"))

"""Coin universe: the N most liquid USDT spot pairs by 30-day quote volume at the build date (public Binance market-data endpoints only,
no API key). Excludes stablecoins, fiat and leveraged tokens. The result is written to universe/universe_<date>.json with the ranking
numbers and the caveats (survivorship: coins delisted before the build date are absent)."""
import datetime as dt
import json
import os
import time

import requests

from data_platform import store

API = os.environ.get("SINDHU_DATA_API", "https://api.binance.com")
STABLE = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USDD", "PYUSD", "EUR", "EURI", "AEUR", "GBP", "TRY", "BRL", "ARS", "UAH", "RUB",
          "USD1", "XUSD", "BFUSD", "UST", "USTC", "USDS", "USDE", "RLUSD"}
LEVERAGED_SUFFIX = ("UP", "DOWN", "BULL", "BEAR")
# Not crypto price series: tokenized US stocks/ETFs (trade like equities) and gold-backed tokens. Found in the first build on 4 Nov 2026
# (SNDKB, SPCXB, SOXLB, CRCLB, MSTRB, MUB, INTCB, GOOGLB, NVDAB, SKHYB, XAUT, PAXG): excluded because their behaviour (and the cost of
# trading them) is unlike the crypto coins the strategies are meant for.
NON_CRYPTO = {"SNDKB", "SPCXB", "SOXLB", "CRCLB", "MSTRB", "MUB", "INTCB", "GOOGLB", "NVDAB", "SKHYB", "XAUT", "PAXG", "TSLAB", "AAPLB",
              "AMZNB", "METAB", "COINB", "QQQB", "SPYB", "MSFTB", "XAGT"}
HEADERS = {"User-Agent": "sindhu-data-platform/1.0 (public market data)"}


def _get(path, params=None, tries=5):
    last = None
    for i in range(tries):
        try:
            r = requests.get(API + path, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code in (418, 429):
                time.sleep(float(r.headers.get("Retry-After", 5 * (i + 1))))
            else:
                time.sleep(1.5 * (i + 1))
        except requests.RequestException as e:
            last = repr(e)
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{path}: {last}")


def eligible(symbol):
    if not symbol.endswith("USDT"):
        return False
    base = symbol[:-4]
    if base in STABLE or base in NON_CRYPTO or not base.isalnum() or len(base) < 2:
        return False
    if any(base.endswith(s) and len(base) > len(s) + 1 for s in LEVERAGED_SUFFIX):
        return False
    return True


def build(n=50, candidates=120, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    t24 = _get("/api/v3/ticker/24hr")
    cand = sorted((t for t in t24 if eligible(t["symbol"])), key=lambda t: -float(t["quoteVolume"]))[:candidates]
    ranked = []
    for t in cand:
        k = _get("/api/v3/klines", {"symbol": t["symbol"], "interval": "1d", "limit": 30})
        ranked.append({"symbol": t["symbol"], "quote_volume_30d": round(sum(float(x[7]) for x in k), 0), "days_with_data": len(k),
                       "quote_volume_24h": round(float(t["quoteVolume"]), 0)})
        time.sleep(0.05)
    ranked = [r for r in ranked if r["days_with_data"] >= 25]
    ranked.sort(key=lambda r: -r["quote_volume_30d"])
    top = ranked[:n]
    for i, r in enumerate(top, 1):
        r["rank"] = i
    doc = {
        "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "date": str(today), "source": "binance spot (public)",
        "rule": f"top {n} USDT spot pairs by 30-day quote volume (sum of 30 daily candles), from the {candidates} largest by 24h volume; "
                "stablecoins, fiat and leveraged tokens excluded; at least 25 days of data",
        "caveats": ["survivorship: pairs delisted before the build date are not in the list", "ranking is at the build date, not at each historical date",
                    "volume ranking favours coins that were hot in the last 30 days"],
        "symbols": [r["symbol"] for r in top], "ranking": top,
    }
    return doc


def save(doc, base=None, tag=""):
    d = os.path.join(base or store.root(), "universe")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"universe_{doc['date']}{tag}.json")
    if os.path.exists(path):
        raise FileExistsError(path)           # a universe file is never replaced
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, path)
    return path


def load_latest(base=None):
    d = os.path.join(base or store.root(), "universe")
    files = sorted(f for f in os.listdir(d) if f.startswith("universe_") and f.endswith(".json"))
    with open(os.path.join(d, files[-1]), encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import sys
    doc = build()
    doc["supersedes"] = "universe_2026-11-04.json (first build contained tokenized stocks and gold tokens)" if (len(sys.argv) > 1 and sys.argv[1] == "v2") else None
    print(save(doc, tag="_v2" if (len(sys.argv) > 1 and sys.argv[1] == "v2") else ""))
    print(len(doc["symbols"]), doc["symbols"][:12])

"""Local cold-scan profiler (no network). A mock exchange serves deterministic synthetic candles with 300-row pages, so call counts and
CPU time are real while network time is modelled as pages x latency. Usage:
  python scripts/profile_scan.py [--workers N] [--latency S] [--cprofile] [--throttle S] [--ticks 2] [--out file.json]
Isolated data dir (D:/sindhu_runtime/prof_data); strategies/groups copied READ-ONLY from the real local DB. Never touches Telegram."""
import argparse, json, math, os, sqlite3, sys, threading, time

ap = argparse.ArgumentParser()
ap.add_argument("--workers", type=int, default=0); ap.add_argument("--latency", type=float, default=0.0)
ap.add_argument("--cprofile", action="store_true"); ap.add_argument("--throttle", type=float, default=None)
ap.add_argument("--ticks", type=int, default=2); ap.add_argument("--out", default=None); ap.add_argument("--page", type=int, default=300)
ap.add_argument("--ro-golden", type=int, default=0, help="research-only proof: N coins, candidates with SINDHU_RESEARCH_ONLY_TIMEFRAMES=1m must equal the full list minus the 1m ones"); ap.add_argument("--fresh", action="store_true"); ap.add_argument("--nomemo", action="store_true"); ap.add_argument("--golden", type=int, default=0, help="golden check: N coins, memo off vs on must give identical candidates"); ap.add_argument("--delay", type=float, default=0.0, help="fixed pause between pages (config default is 0.25)")
a = ap.parse_args()
DATA = "D:/sindhu_runtime/prof_data"
if a.fresh:
    import shutil; shutil.rmtree(DATA, ignore_errors=True)
os.environ.update(SINDHU_DATA_DIR=DATA, SINDHU_LIVE_CANDLES="1", SINDHU_CLOUD_MODE="1", SINDHU_TELEGRAM_DRY_RUN="1",
                  SINDHU_PUBLIC_SIGNAL_OWNER="disabled", SINDHU_STRATEGY_LIBRARY_DIR="D:/sindhu_runtime/strategy_library",
                  SINDHU_PREFETCH_WORKERS=str(a.workers))
os.environ.pop("SINDHU_SAFE_START", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import psutil
from data_engine import storage
storage.init_db()
with storage.get_conn() as c:
    n = c.execute("SELECT COUNT(*) FROM paper_strategy_config").fetchone()[0]
if n == 0:
    src = sqlite3.connect("file:D:/sindhu/data/database/sindhu.db?mode=ro", uri=True, timeout=60)
    with storage.get_conn() as c:
        for t in ("paper_strategy_config", "paper_strategy_groups"):
            cols = [r[1] for r in src.execute(f"PRAGMA table_info({t})")]
            rows = src.execute(f"SELECT {','.join(cols)} FROM {t}").fetchall()
            c.executemany(f"INSERT OR REPLACE INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", rows)
from paper_trading import config as pt
pt.update(coin_filter_top_n=10, coin_filter_mode="liquidity", dry_run=True, engine_enabled=False)

COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "PEPE", "HYPE", "ZEC", "UNI", "LIT"] + [f"C{i:02d}" for i in range(40)]
SYMS = {c: f"{c}/USDT" for c in COINS}
IV = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
      "6h": 21_600_000, "12h": 43_200_000, "1d": 86_400_000, "1w": 604_800_000}
STAT = {"pages": 0, "net_model_s": 0.0, "by_iv": {}, "rows": 0}
LOCK = threading.Lock()


_SEED = {}


def price(sym, k):
    s = _SEED.get(sym)
    if s is None:
        s = _SEED[sym] = sum(map(ord, sym)) % 97
    return 100 * (1 + 0.04 * math.sin(k / (900 + s)) + 0.015 * math.sin(k / 41 + s) + 0.004 * math.sin(k * 1.7 + s))


class Fake:
    id = "okx"

    def get_tradeable_symbols(self, quote): return dict(SYMS)

    def get_tickers(self, quote): return {v: {"price": 100.0, "change_pct": 1.0, "volume": 1e6 - i} for i, v in enumerate(SYMS.values())}

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        if a.latency:
            time.sleep(a.latency)
        _g0 = time.perf_counter()
        ms = IV[interval]; now = int(time.time() * 1000); lim = min(limit, a.page)
        k0 = -(-(since_ms or now - 86_400_000) // ms)
        rows = []
        for k in range(k0, k0 + lim):
            t = k * ms
            if t > now: break
            p0, p1 = price(symbol, k), price(symbol, k + 1)
            rows.append((t, p0, max(p0, p1) * 1.001, min(p0, p1) * 0.999, p1, 10.0 + (k % 7), t + ms - 1, 1000.0, 0))
        with LOCK:
            STAT["gen_s"] = STAT.get("gen_s", 0.0) + (time.perf_counter() - _g0)
            STAT["pages"] += 1; STAT["rows"] += len(rows); STAT["by_iv"][interval] = STAT["by_iv"].get(interval, 0) + 1
        return rows


FAKE = Fake()
from data_engine import live_candles as lc
lc.get_exchange_client = lambda ex: FAKE
lc.REQUEST_DELAY_SECONDS = a.delay
if a.throttle is not None:
    lc._REFRESH_MIN_SECONDS = a.throttle
import data_engine.symbols as sy
sy.pick_top_symbols = lambda client, n=50, quote="USDT", tradeable=None: list(SYMS.values())
from paper_trading import engine as eng
eng.get_working_exchange_client = lambda cands, quote, log=None: ("okx", FAKE, dict(SYMS))
eng.last_known_working_exchange = lambda: "okx"
E = eng.engine

TIM = {}


def wrap(obj, name, label):
    f = getattr(obj, name)

    def w(*x, **k):
        t0 = time.perf_counter(); c0 = time.process_time()
        try: return f(*x, **k)
        finally:
            with LOCK:
                d = TIM.setdefault(label, [0, 0.0, 0.0]); d[0] += 1; d[1] += time.perf_counter() - t0; d[2] += time.process_time() - c0
    setattr(obj, name, w)


from backtest_engine import concepts as _cn
if a.nomemo:
    _cn.memo_enable = lambda on=True: None
import hashlib
DIGEST = {}
from paper_trading import signal_generator as _sg
_orig_gc = _sg.generate_candidates


def _gc(exchange, symbol, strategies, lessons, settings):
    out = _orig_gc(exchange, symbol, strategies, lessons, settings)
    DIGEST[symbol] = hashlib.sha1(json.dumps(out, sort_keys=True, default=str).encode()).hexdigest()[:12] + f":{len(out)}"
    return out


_sg.generate_candidates = _gc
from paper_trading import market_state, strategy_matcher, signal_generator, coin_filter, telegram_bot
wrap(market_state, "classify", "market_state.classify"); wrap(strategy_matcher, "relevant_strategies", "relevant_strategies")
wrap(signal_generator, "generate_candidates", "generate_candidates (all strategies, one coin)"); wrap(coin_filter, "shortlist", "coin_filter.shortlist (50 coins)")
wrap(E, "_process_coin", "engine._process_coin"); wrap(E, "_prefetch_candles", "engine._prefetch_candles"); wrap(E, "_flush_decisions", "engine._flush_decisions")
wrap(E, "_housekeeping", "engine._housekeeping"); wrap(telegram_bot, "sweep_unsent_qualifying_signals", "telegram sweep")
eng.market_state = market_state

proc = psutil.Process(); PEAK = [proc.memory_info().rss]; STOP = threading.Event(); CURVE = []


def sampler():
    t0 = time.time()
    while not STOP.is_set():
        r = proc.memory_info().rss; PEAK[0] = max(PEAK[0], r); CURVE.append((round(time.time() - t0, 1), round(r / 1e6)))
        time.sleep(0.5)


threading.Thread(target=sampler, daemon=True).start()
def golden(n_coins):
    """Frozen clock + warm cache: candidates with the memo OFF must equal candidates with the memo ON (first call = miss, second = hit)."""
    FIXED = int(time.time() // 900 * 900) + 5
    real_time = time.time
    time.time = lambda: FIXED
    lc._now_ms = lambda: FIXED * 1000
    settings = dict(pt.load())
    bad = 0; total = 0; states = ("ranging", "trending_up", "trending_down", "volatile", "breakout")
    for sym in list(SYMS.values())[:n_coins]:
        strategies = []
        seen = set()
        for st in states:
            for s_ in strategy_matcher.relevant_strategies(sym, st):
                if s_["strategy_id"] not in seen:
                    seen.add(s_["strategy_id"]); strategies.append(s_)
        _cn.memo_enable(False); off = _orig_gc("okx", sym, strategies, [], dict(settings))
        _cn.memo_enable(True); on1 = _orig_gc("okx", sym, strategies, [], dict(settings)); on2 = _orig_gc("okx", sym, strategies, [], dict(settings)); _cn.memo_enable(False)
        j = lambda x: json.dumps(x, sort_keys=True, default=str)
        ok = j(off) == j(on1) == j(on2)
        total += 1; bad += (not ok)
        print(f"GOLDEN {sym}: {len(strategies)} strategies, {len(off)} candidates, identical={ok}, memo={_cn.memo_stats()}", flush=True)
    time.time = real_time
    print("GOLDEN RESULT:", "PASS" if bad == 0 else f"FAIL ({bad}/{total})", flush=True)


def ro_golden(n_coins):
    """Frozen clock + warm cache. For each coin: full candidate list (flag OFF) vs list with SINDHU_RESEARCH_ONLY_TIMEFRAMES=1m.
    The second must equal the first with the 1m-timeframe candidates removed, byte for byte."""
    FIXED = int(time.time() // 900 * 900) + 5
    real_time = time.time
    time.time = lambda: FIXED
    lc._now_ms = lambda: FIXED * 1000
    settings = dict(pt.load())
    states = ("ranging", "trending_up", "trending_down", "volatile", "breakout")
    bad = 0; removed_total = 0; kept_total = 0; strategies_1m = set()
    for sym in list(SYMS.values())[:n_coins]:
        strategies, seen = [], set()
        for st in states:
            for s_ in strategy_matcher.relevant_strategies(sym, st):
                if s_["strategy_id"] not in seen:
                    seen.add(s_["strategy_id"]); strategies.append(s_)
        _cn.memo_enable(False)
        os.environ.pop("SINDHU_RESEARCH_ONLY_TIMEFRAMES", None)
        full = _orig_gc("okx", sym, strategies, [], dict(settings))
        os.environ["SINDHU_RESEARCH_ONLY_TIMEFRAMES"] = "1m"
        ro = _orig_gc("okx", sym, strategies, [], dict(settings))
        os.environ.pop("SINDHU_RESEARCH_ONLY_TIMEFRAMES", None)
        j = lambda x: json.dumps(x, sort_keys=True, default=str)
        expect = [c for c in full if c.get("timeframe") != "1m"]
        removed = [c for c in full if c.get("timeframe") == "1m"]
        ok = j(ro) == j(expect)
        bad += (not ok); removed_total += len(removed); kept_total += len(ro)
        strategies_1m |= {c.get("strategy_id") for c in removed}
        print(f"RO-GOLDEN {sym}: {len(strategies)} strategies, full={len(full)} candidates, 1m removed={len(removed)}, with flag={len(ro)}, non-1m identical={ok}", flush=True)
    time.time = real_time
    print(f"RO-GOLDEN RESULT: {'PASS' if bad == 0 else f'FAIL ({bad})'} | candidates kept {kept_total}, removed (1m) {removed_total}, distinct 1m strategies with candidates {len(strategies_1m)}", flush=True)


if a.ro_golden:
    ro_golden(a.ro_golden); sys.exit(0)
if a.golden:
    golden(a.golden); sys.exit(0 if True else 1)
res = {"args": vars(a)}
pr = None
if a.cprofile:
    import cProfile, pstats; pr = cProfile.Profile()
for i in range(a.ticks):
    STAT0 = (STAT["pages"], STAT["rows"]); t0 = time.perf_counter(); c0 = time.process_time()
    if pr and i == 0: pr.enable()
    E.run_single_tick_now()
    if pr and i == 0: pr.disable()
    res[f"tick{i + 1}"] = {"wall_s": round(time.perf_counter() - t0, 1), "cpu_s": round(time.process_time() - c0, 1),
                           "pages": STAT["pages"] - STAT0[0], "rows": STAT["rows"] - STAT0[1]}
STOP.set()
res["peak_rss_mb"] = round(PEAK[0] / 1e6); res["timings"] = {k: [v[0], round(v[1], 1), round(v[2], 1)] for k, v in TIM.items()}
res["pages_by_interval"] = STAT["by_iv"]; res["mock_exchange_generation_s"] = round(STAT.get("gen_s", 0.0), 1); res["rss_curve_mb"] = CURVE[::max(1, len(CURVE) // 40)]
res["summary"] = E._last_summary; res["candidate_digests"] = DIGEST; res["memo"] = _cn.memo_stats()
print(json.dumps(res, indent=1))
if a.out: json.dump(res, open(a.out, "w"), indent=1)
if pr:
    import pstats; s = pstats.Stats(pr); pr.dump_stats(os.path.join(DATA, "last_profile.prof"))
    print("=== project functions by cumulative time"); s.sort_stats("cumulative").print_stats("sindhu_clean", 45)
    print("=== all functions by own time"); s.sort_stats("tottime").print_stats(25)

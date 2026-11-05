"""Master plan B3: the two pre-registered daily strategies (docs/BENCHMARK_PREREGISTRATION_V2.md, incl. Amendment 1) as plug-ins of one
small daily portfolio simulator, plus the metrics, benchmarks, bootstrap and verdict rules fixed there. Pure functions on arrays; no
network, no database, no strategy library changes. Local research only (master plan Part B).

Conventions (from the pre-registration):
- signals use data up to the close of day t; trades execute at the OPEN of day t+1 (no lookahead)
- long-only, no leverage, N = 20 fixed, weight = signal * min(1, target_vol / vol30) / N, cash earns 0
- costs per side on traded notional: fee 0.10 % + slippage 0.05 % (x1.5 stress = 0.225 %)
- a coin whose series ends is sold at the close of its last full day; partial candles are dropped
- one position = weight 0 -> > 0 -> 0 for one coin
"""
import math
import os

import numpy as np

DAY_MS = 86_400_000
FEE, SLIP = 0.0010, 0.0005
COST = FEE + SLIP
N_FIXED = 20
TARGET_VOL = 0.02
IS_START, IS_END = "2018-01-01", "2023-12-31"
OOS_START, OOS_END = "2024-01-01", "2026-10-31"
WF_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
SEED = 20261105


# ------------------------------------------------------------------ data
class Panel:
    """Aligned daily arrays [day, coin] (NaN where a coin has no candle). days = open_time ms of each UTC day."""

    def __init__(self, days, symbols, o, h, l, c):
        self.days, self.symbols, self.o, self.h, self.l, self.c = days, symbols, o, h, l, c
        self.last_idx = np.array([int(np.max(np.where(~np.isnan(c[:, j]))[0])) if (~np.isnan(c[:, j])).any() else -1
                                  for j in range(len(symbols))])

    @staticmethod
    def from_parquet(data_dir=r"D:\sindhu_data\daily", symbols=None, start="2018-01-01", end=OOS_END):
        import json
        import pyarrow.parquet as pq
        if symbols is None:
            symbols = [s["symbol"] for s in json.load(open(os.path.join(data_dir, "universe_v2.json"), encoding="utf-8"))["symbols"]]
        s_ms, e_ms = _ms(start), _ms(end)
        days = np.arange(s_ms, e_ms + 1, DAY_MS, dtype="int64")
        pos = {int(d): i for i, d in enumerate(days)}
        arrs = [np.full((len(days), len(symbols)), np.nan) for _ in range(4)]
        for j, sym in enumerate(symbols):
            t = pq.read_table(os.path.join(data_dir, f"{sym}_1d.parquet")).to_pydict()
            for k in range(len(t["open_time"])):
                ot = int(t["open_time"][k])
                if int(t["close_time"][k]) - ot < DAY_MS - 1:      # Amendment 1: drop partial candles
                    continue
                i = pos.get(ot)
                if i is None:
                    continue
                for a, name in zip(arrs, ("open", "high", "low", "close")):
                    a[i, j] = float(t[name][k])
        return Panel(days, list(symbols), *arrs)


def _ms(date_str):
    import datetime as dt
    y, m, d = map(int, date_str.split("-"))
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _year(ms):
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).year


def _weekday(ms):            # Monday = 0 ... Sunday = 6
    return int(((ms // DAY_MS) + 3) % 7)


# ------------------------------------------------------------------ signals (each returns [day, coin] in [0, 1], known at the close of day t)
def vol30(c):
    lr = np.log(c[1:] / c[:-1])
    out = np.full(c.shape, np.nan)
    for t in range(30, c.shape[0]):
        w = lr[t - 30:t]                         # the 30 returns ending at close t
        ok = ~np.isnan(w).any(axis=0)
        sd = np.nanstd(w, axis=0, ddof=1)
        out[t] = np.where(ok, sd, np.nan)
    return out


def donchian_signal(p, lookbacks=(20, 55, 100)):
    T, J = p.c.shape
    total = np.zeros((T, J))
    for L in lookbacks:
        x = L // 2
        s = np.zeros((T, J))
        state = np.zeros(J)
        for t in range(T):
            if t >= L:
                hh = np.max(p.h[t - L:t], axis=0)
                ll = np.min(p.l[t - x:t], axis=0)
                ct = p.c[t]
                valid = ~(np.isnan(hh) | np.isnan(ll) | np.isnan(ct))
                up = valid & (ct > hh)
                dn = valid & (ct < ll)
                state = np.where(up, 1.0, np.where(dn, 0.0, state))
                state = np.where(np.isnan(ct), 0.0, state)
            s[t] = state
        total += s
    return total / len(lookbacks)


def tsmom_signal(p, window=28):
    T, J = p.c.shape
    s = np.full((T, J), np.nan)                  # NaN = "not a rebalance day" (weights untouched)
    for t in range(window, T):
        if _weekday(int(p.days[t])) != 6:        # only the Sunday candle (closes Monday 00:00 UTC)
            continue
        r = p.c[t] / p.c[t - window] - 1
        s[t] = np.where(np.isnan(r), 0.0, (r > 0).astype(float))
    return s


def target_weights(sig, vol, target_vol=TARGET_VOL):
    scale = np.where(np.isnan(vol) | (vol <= 0), 0.0, np.minimum(1.0, target_vol / np.where(vol > 0, vol, 1.0)))
    w = np.where(np.isnan(sig), np.nan, np.nan_to_num(sig) * scale / N_FIXED)
    return w


# ------------------------------------------------------------------ simulator
def simulate(p, targets, band=None, cost=COST, start_cash=100.0):
    """targets[t] = weights decided at close t (NaN row/entry = keep current holdings). Executed at open t+1.
    Returns dict with daily equity (at close), gross weight, positions list and turnover."""
    T, J = p.c.shape
    units = np.zeros(J)
    cash = start_cash
    equity = np.full(T, np.nan)
    gross = np.zeros(T)
    turnover = 0.0
    costs_paid = 0.0
    open_pos = {}                                 # j -> {"entry_day", "cash_out", "cash_in", "entry_notional"}
    positions = []
    pending = None

    def trade(j, new_units, price, day):
        nonlocal cash, turnover, costs_paid
        delta = new_units - units[j]
        if delta == 0:
            return
        notional = abs(delta) * price
        fee = notional * cost
        cash -= delta * price + fee
        costs_paid += fee
        turnover += notional
        rec = open_pos.get(j)
        if units[j] == 0 and new_units > 0:
            rec = open_pos[j] = {"coin": p.symbols[j], "entry_day": int(p.days[day]), "out": 0.0, "in": 0.0, "entry_notional": notional}
        if rec is not None:
            if delta > 0:
                rec["out"] += delta * price + fee
            else:
                rec["in"] += -delta * price - fee
        units[j] = new_units
        if new_units == 0 and rec is not None:
            rec["exit_day"] = int(p.days[day])
            rec["pnl"] = rec["in"] - rec["out"]
            rec["ret"] = rec["pnl"] / rec["entry_notional"] if rec["entry_notional"] else 0.0
            positions.append(rec)
            del open_pos[j]

    for t in range(T):
        # 1) execute yesterday's decision at today's open
        if pending is not None:
            o = p.o[t]
            px = np.where(np.isnan(o), 0.0, o)
            value = cash + float(np.sum(units * px))
            for j in range(J):
                w = pending[j]
                if np.isnan(w) or np.isnan(o[j]):
                    continue
                cur_w = units[j] * o[j] / value if value > 0 else 0.0
                tgt = max(0.0, w)
                if band is not None and cur_w > 0 and tgt > 0 and abs(tgt - cur_w) <= band * cur_w:
                    continue
                trade(j, tgt * value / o[j], o[j], t)
            pending = None
        # 2) a series that ends today is sold at today's close (Amendment 1)
        for j in np.where(p.last_idx == t)[0]:
            if units[j] > 0 and t < T - 1:
                trade(j, 0.0, p.c[t, j], t)
        # 3) mark to market at the close
        c = np.where(np.isnan(p.c[t]), 0.0, p.c[t])
        held = units * c
        equity[t] = cash + float(np.sum(held))
        gross[t] = float(np.sum(held)) / equity[t] if equity[t] > 0 else 0.0
        # 4) decide (executes at the next open)
        if t < T - 1:
            row = targets[t].copy()
            row[p.last_idx <= t] = np.where(np.isnan(row[p.last_idx <= t]), np.nan, 0.0)
            pending = row
    for j, rec in list(open_pos.items()):        # still open at the end: valued at the last close (marked, not a closed trade)
        rec["exit_day"] = None
        rec["pnl"] = rec["in"] + units[j] * np.nan_to_num(p.c[-1, j]) * (1 - cost) - rec["out"]
        rec["ret"] = rec["pnl"] / rec["entry_notional"] if rec["entry_notional"] else 0.0
        rec["open_at_end"] = True
        positions.append(rec)
    return {"equity": equity, "gross": gross, "positions": positions, "turnover": turnover, "costs": costs_paid, "days": p.days}


# ------------------------------------------------------------------ benchmarks
def btc_buy_hold(p):
    j = p.symbols.index("BTCUSDT")
    tg = np.full(p.c.shape, np.nan)
    tg[0, :] = 0.0
    tg[0, j] = 1.0
    return simulate(p, tg)


def equal_weight_buy_hold(p):
    T, J = p.c.shape
    tg = np.full((T, J), np.nan)
    import datetime as dt
    for t in range(T - 1):
        m_now = dt.datetime.fromtimestamp(p.days[t] / 1000, dt.timezone.utc).month
        m_next = dt.datetime.fromtimestamp(p.days[t + 1] / 1000, dt.timezone.utc).month
        if t == 0 or m_now != m_next:            # last day of a month -> rebalance at the 1st's open
            listed = ~np.isnan(p.c[t]) & (p.last_idx > t)
            n = int(listed.sum())
            tg[t] = np.where(listed, 1.0 / n if n else 0.0, 0.0)
    return simulate(p, tg)


# ------------------------------------------------------------------ metrics
def _slice(res, start, end):
    d = res["days"]
    a, b = _ms(start), _ms(end)
    idx = np.where((d >= a) & (d <= b))[0]
    return idx


def metrics(res, start, end):
    idx = _slice(res, start, end)
    eq = res["equity"][idx]
    if len(eq) < 2:
        return None
    prev = res["equity"][idx[0] - 1] if idx[0] > 0 else eq[0]
    series = np.concatenate([[prev], eq])
    r = series[1:] / series[:-1] - 1
    years = len(r) / 365.0
    total = series[-1] / series[0] - 1
    cagr = (series[-1] / series[0]) ** (1 / years) - 1 if series[0] > 0 and years > 0 else float("nan")
    sd = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
    down = math.sqrt(float(np.mean(np.minimum(r, 0) ** 2)))
    peak = np.maximum.accumulate(series)
    mdd = float(np.min(series / peak - 1))
    a, b = _ms(start), _ms(end)
    pos = [x for x in res["positions"] if a <= x["entry_day"] <= b]
    wins = [x["pnl"] for x in pos if x["pnl"] > 0]
    losses = [x["pnl"] for x in pos if x["pnl"] <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (float("inf") if wins else float("nan"))
    return {
        "start": start, "end": end, "days": int(len(r)), "total_return_pct": round(total * 100, 2), "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(float(np.mean(r)) / sd * math.sqrt(365), 3) if sd > 0 else 0.0,
        "sortino": round(float(np.mean(r)) / down * math.sqrt(365), 3) if down > 0 else 0.0,
        "max_drawdown_pct": round(mdd * 100, 2), "profit_factor": round(pf, 3) if pf == pf and pf != float("inf") else pf,
        "positions": len(pos), "coins_with_positions": len({x["coin"] for x in pos}),
        "win_rate_pct": round(len(wins) / len(pos) * 100, 1) if pos else None,
        "exposure_pct": round(float(np.mean(res["gross"][idx])) * 100, 1),
        "t_stat": round(float(np.mean(r)) / (sd / math.sqrt(len(r))), 2) if sd > 0 else 0.0,
        "_returns": r,
    }


def pooled_pf(res, start=IS_START, end=OOS_END):
    a, b = _ms(start), _ms(end)
    pnl = [x["pnl"] for x in res["positions"] if a <= x["entry_day"] <= b]
    w, l = sum(x for x in pnl if x > 0), sum(x for x in pnl if x <= 0)
    return (w / abs(l)) if l else float("inf")


def block_bootstrap_p(r, block=20, n=1000, seed=SEED):
    """One-sided p-value for H0 mean daily return <= 0 (centred circular block bootstrap)."""
    rng = np.random.default_rng(seed)
    r = np.asarray(r, dtype=float)
    obs = float(np.mean(r))
    c = r - obs
    T = len(c)
    nb = int(math.ceil(T / block))
    means = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, T, nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:T] % T
        means[i] = c[idx].mean()
    return float((np.sum(means >= obs) + 1) / (n + 1))


def position_bootstrap_ci(rets, n=1000, seed=SEED):
    rng = np.random.default_rng(seed)
    rets = np.asarray(rets, dtype=float)
    if len(rets) == 0:
        return (None, None)
    m = np.array([rng.choice(rets, len(rets)).mean() for _ in range(n)])
    return (round(float(np.percentile(m, 2.5)) * 100, 3), round(float(np.percentile(m, 97.5)) * 100, 3))


def benjamini_hochberg(pvals, q=0.05):
    """Return the set of indices that pass BH at level q."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    k_max = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            k_max = rank
    return set(order[:k_max])


# ------------------------------------------------------------------ the two strategies with their parameters
def run_strategy(p, name, params=None, cost=COST):
    params = params or {}
    vol = vol30(p.c)
    if name == "donchian":
        lbs = params.get("lookbacks", (20, 55, 100))
        sig = donchian_signal(p, lbs)
        tg = target_weights(sig, vol, params.get("target_vol", TARGET_VOL))
        return simulate(p, tg, band=0.10, cost=cost)
    if name == "tsmom":
        sig = tsmom_signal(p, params.get("window", 28))
        tg = target_weights(sig, vol, params.get("target_vol", TARGET_VOL))
        return simulate(p, tg, band=None, cost=cost)
    raise ValueError(name)


def neighbours(name):
    out = []
    for f in (0.8, 0.9, 1.1, 1.2):
        if name == "donchian":
            out.append((f"lookbacks x{f}", {"lookbacks": tuple(int(round(L * f)) for L in (20, 55, 100))}))
        else:
            out.append((f"window x{f}", {"window": int(round(28 * f))}))
        out.append((f"target_vol x{f}", {"target_vol": round(TARGET_VOL * f, 4)}))
    return out

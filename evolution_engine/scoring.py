"""A.6 -- Evolution Score, and A.8's time-decay weighting. Pure arithmetic
over stats already aggregated from real backtest/paper-trading data -- no
AI, no ML, nothing learned. Every weight below is a fixed constant declared
here, not tuned by any optimizer, so the formula is fully auditable.

EVOLUTION SCORE FORMULA (0-100, higher is better)
--------------------------------------------------
    score = 100 * sum(WEIGHTS[k] * component_k for k in WEIGHTS)

Components (each normalized to 0-100 before weighting):
    win_rate              wins / trades * 100, 0 if no trades
    profit_factor         gross_profit / gross_loss, saturating at 3.0x -> 100
    net_profit            tanh-saturated around a $500 scale, 50 = breakeven
    avg_rr                average realized risk:reward, saturating at 3.0 -> 100
    drawdown (inverted)   100 - max_drawdown_pct (lower drawdown -> higher score)
    trade_count           sample-size confidence, saturating at 30 trades -> 100
    stability             inverse coefficient-of-variation of per-period pnl
    consistency           fraction of profitable periods (days/weeks)
    session_performance   mean of per-session scores already computed elsewhere
    coin_performance       mean of per-coin scores already computed elsewhere
    market_condition_perf  mean of per-regime scores already computed elsewhere

WEIGHTS (sum to 1.0):
    win_rate 0.15, profit_factor 0.15, net_profit 0.10, avg_rr 0.10,
    drawdown 0.10, trade_count 0.05, stability 0.10, consistency 0.10,
    session_performance 0.05, coin_performance 0.05, market_condition_performance 0.05

Any component whose inputs aren't available defaults to 50 (neutral) rather
than 0, so a brand-new strategy with only a handful of trades isn't unfairly
crushed on dimensions it has no data for yet -- trade_count itself is what
keeps such a strategy's score from being trusted too early.
"""

import math

WEIGHTS = {
    "win_rate": 0.15,
    "profit_factor": 0.15,
    "net_profit": 0.10,
    "avg_rr": 0.10,
    "drawdown": 0.10,
    "trade_count": 0.05,
    "stability": 0.10,
    "consistency": 0.10,
    "session_performance": 0.05,
    "coin_performance": 0.05,
    "market_condition_performance": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

NET_PROFIT_SCALE = 500.0     # $ scale for the tanh saturation
PROFIT_FACTOR_CAP = 3.0
AVG_RR_CAP = 3.0
TRADE_COUNT_CAP = 30


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def compute_evolution_score(stats):
    """stats: dict, every key optional --
      trades, wins, gross_profit, gross_loss (positive number), total_pnl,
      avg_rr, max_drawdown_pct, pnl_by_period (list, most-recent-first),
      session_scores / coin_scores / market_condition_scores (dict of 0-100),
      confidence (0-100, unused in the weighted sum but returned for display).
    Returns (score: float 0-100, breakdown: dict of component -> value) --
    the breakdown is what makes the score traceable/explainable rather than
    a black box."""
    trades = stats.get("trades", 0) or 0
    wins = stats.get("wins", 0) or 0
    gross_profit = stats.get("gross_profit", 0.0) or 0.0
    gross_loss = stats.get("gross_loss", 0.0) or 0.0
    total_pnl = stats.get("total_pnl", 0.0) or 0.0
    avg_rr = stats.get("avg_rr")
    max_dd = stats.get("max_drawdown_pct")
    pnl_by_period = stats.get("pnl_by_period") or []

    win_rate = (wins / trades * 100.0) if trades else 0.0

    # A precomputed profit_factor (e.g. backtest_engine.reports.generate_report's
    # avg_profit_factor) takes precedence over deriving one from gross_profit/
    # gross_loss -- callers that already have a reliable profit factor from
    # elsewhere shouldn't have to reverse-engineer gross_profit/gross_loss to
    # match this formula's shape.
    if stats.get("profit_factor") is not None:
        pf = stats["profit_factor"]
    elif gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = PROFIT_FACTOR_CAP
    else:
        pf = 0.0
    profit_factor_component = _clamp(100.0 * min(pf, PROFIT_FACTOR_CAP) / PROFIT_FACTOR_CAP)

    net_profit_component = _clamp(50.0 + 50.0 * math.tanh(total_pnl / NET_PROFIT_SCALE))

    avg_rr_component = _clamp(100.0 * min(max(avg_rr or 0.0, 0.0), AVG_RR_CAP) / AVG_RR_CAP)

    drawdown_component = _clamp(100.0 - min(max(max_dd if max_dd is not None else 0.0, 0.0), 100.0))

    trade_count_component = _clamp(100.0 * min(trades, TRADE_COUNT_CAP) / TRADE_COUNT_CAP)

    stability_component = _stability(pnl_by_period)
    consistency_component = _consistency(pnl_by_period, fallback=win_rate)

    session_performance = _mean_or_neutral(stats.get("session_scores"))
    coin_performance = _mean_or_neutral(stats.get("coin_scores"))
    market_condition_performance = _mean_or_neutral(stats.get("market_condition_scores"))

    components = {
        "win_rate": _clamp(win_rate),
        "profit_factor": profit_factor_component,
        "net_profit": net_profit_component,
        "avg_rr": avg_rr_component,
        "drawdown": drawdown_component,
        "trade_count": trade_count_component,
        "stability": stability_component,
        "consistency": consistency_component,
        "session_performance": session_performance,
        "coin_performance": coin_performance,
        "market_condition_performance": market_condition_performance,
    }
    score = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)
    breakdown = dict(components)
    breakdown["_weights"] = dict(WEIGHTS)
    breakdown["_final_score"] = round(score, 2)
    return round(score, 2), breakdown


def _mean_or_neutral(d):
    if not d:
        return 50.0
    vals = list(d.values())
    return _clamp(sum(vals) / len(vals))


def _stability(pnl_by_period):
    """100 = perfectly steady returns, lower = more erratic. Needs at least
    3 periods to say anything meaningful; fewer than that returns a neutral
    50 rather than pretending to measure volatility from 1-2 points."""
    if len(pnl_by_period) < 3:
        return 50.0
    mean = sum(pnl_by_period) / len(pnl_by_period)
    variance = sum((x - mean) ** 2 for x in pnl_by_period) / len(pnl_by_period)
    stdev = math.sqrt(variance)
    denom = abs(mean) if abs(mean) > 1e-9 else (stdev if stdev > 1e-9 else 1.0)
    cv = stdev / denom
    return _clamp(100.0 / (1.0 + cv))


def _consistency(pnl_by_period, fallback):
    if not pnl_by_period:
        return _clamp(fallback)
    profitable = sum(1 for x in pnl_by_period if x > 0)
    return _clamp(100.0 * profitable / len(pnl_by_period))


def time_decay_weights(n, half_life=20):
    """A.8 -- recent performance must be weighted more heavily than old
    performance, but old data is never deleted, only down-weighted. Index 0
    is assumed to be the OLDEST item and index n-1 the MOST RECENT (matches
    how storage.list_closed_paper_positions returns rows -- callers should
    reverse to oldest-first before zipping with these weights). Exponential
    decay: weight halves every `half_life` items back from the most recent."""
    if n <= 0:
        return []
    return [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]


def weighted_average(values, weights):
    if not values or not weights or len(values) != len(weights):
        return None
    total_w = sum(weights)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in zip(values, weights)) / total_w

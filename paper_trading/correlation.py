"""Correlation Warning System (Risk & Safety Group, item 5): informational
only -- surfaces when two or more currently-open positions (across
DIFFERENT strategies) are in the same direction on symbols whose recent
price moves are actually correlated, so combined exposure isn't hidden
just because it's split across several strategies' independent books.
Never blocks a trade; nothing here is called from the trading loop.

Correlation is computed from real price history already in the system
(get_ohlcv 1h closes, 72h lookback) via the standard Pearson correlation
coefficient of returns -- not a hardcoded "these coins move together" list,
since that would silently go stale as the market changes. Bounded to
symbols that currently have an open position (not all 50 tracked symbols),
so the pairwise comparison stays cheap even as trade volume grows.
"""

from data_engine.resample import get_ohlcv
from data_engine import storage

_LOOKBACK_HOURS = 72
_MIN_ALIGNED_POINTS = 20
_CORRELATION_THRESHOLD = 0.7
_MAX_SYMBOLS_CONSIDERED = 25  # degrade gracefully rather than an O(n^2) blowup


def _returns(exchange, symbol):
    import time
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - _LOOKBACK_HOURS * 3600 * 1000
    df = get_ohlcv(exchange, symbol, interval="1h", start_ms=start_ms, end_ms=end_ms)
    if len(df) < _MIN_ALIGNED_POINTS:
        return None
    return df["close"].pct_change().dropna()


def _correlation(exchange, symbol_a, symbol_b, _cache):
    for sym in (symbol_a, symbol_b):
        if sym not in _cache:
            _cache[sym] = _returns(exchange, sym)
    ra, rb = _cache[symbol_a], _cache[symbol_b]
    if ra is None or rb is None:
        return None
    aligned = ra.align(rb, join="inner")
    if len(aligned[0]) < _MIN_ALIGNED_POINTS:
        return None
    corr = aligned[0].corr(aligned[1])
    return float(corr) if corr == corr else None  # NaN check (e.g. zero-variance series)


def detect_warnings(exchange):
    """Returns a list of plain-language warning dicts. Degrades gracefully:
    fewer than 2 open positions, or no correlated pairs found, returns []."""
    positions = storage.get_open_paper_positions(exchange)
    if len(positions) < 2:
        return []

    by_direction = {"long": {}, "short": {}}
    for p in positions:
        direction = p["direction"]
        if direction not in by_direction:
            continue
        by_direction[direction].setdefault(p["symbol"], set()).add(p.get("strategy_id") or "lessons")

    warnings = []
    seen_pairs = set()
    returns_cache = {}
    for direction, symbols_map in by_direction.items():
        symbols = list(symbols_map.keys())[:_MAX_SYMBOLS_CONSIDERED]
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                sym_a, sym_b = symbols[i], symbols[j]
                strategies_a, strategies_b = symbols_map[sym_a], symbols_map[sym_b]
                total_strategies = strategies_a | strategies_b
                if len(total_strategies) < 2:
                    continue  # same single strategy on both -- not a hidden-exposure situation
                pair_key = (direction, tuple(sorted([sym_a, sym_b])))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                try:
                    corr = _correlation(exchange, sym_a, sym_b, returns_cache)
                except Exception:
                    continue
                if corr is None or corr < _CORRELATION_THRESHOLD:
                    continue

                verb = "long" if direction == "long" else "short"
                warnings.append({
                    "direction": direction,
                    "symbols": [sym_a, sym_b],
                    "strategy_count": len(total_strategies),
                    "correlation": round(corr, 2),
                    "message": (
                        f"{len(total_strategies)} strategies are currently {verb} on {sym_a} and {sym_b} "
                        f"at the same time -- these two tend to move together (correlation {corr:.2f}), "
                        f"so the real combined exposure may be higher than it looks at a glance."
                    ),
                })
    return warnings


# ------------------------------------------------------ Grand Feature Expansion, Phase 3 Feature 4
# Strategy-vs-Strategy Correlation Matrix -- distinct from detect_warnings()
# above (which correlates SYMBOL PRICE RETURNS for currently-open
# positions). This correlates each strategy's own DAILY REALIZED PnL time
# series -- the real "do these two strategies win and lose on the same
# days" question, the one that actually answers whether running both gives
# genuine diversification or is a hidden, doubled-up bet.

CORRELATION_LOOKBACK_DAYS = 30
MIN_ALIGNED_DAYS = 10


def _pearson(xs, ys):
    """Plain-Python Pearson correlation coefficient -- same manual-formula
    style as paper_trading.insights (no pandas dependency needed for two
    short, already-aligned lists)."""
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = (var_x * var_y) ** 0.5
    return cov / denom if denom > 0 else None


def strategy_correlation_matrix(strategy_ids, lookback_days=CORRELATION_LOOKBACK_DAYS):
    """Returns {"strategies": [id, ...], "matrix": [[float|None, ...], ...],
    "min_aligned_days": int}. matrix[i][j] is the correlation between
    strategy_ids[i] and strategy_ids[j] (1.0 on the diagonal); None when
    fewer than MIN_ALIGNED_DAYS days overlap between the two, or either
    strategy has zero variance in its own daily PnL (a flat/no-data
    series correlates with nothing meaningfully)."""
    from datetime import datetime, timezone, timedelta
    from data_engine import storage

    since_iso = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    daily_series = {sid: storage.list_paper_daily_pnl_by_strategy(sid, since_iso) for sid in strategy_ids}

    n = len(strategy_ids)
    matrix = [[None] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0 if daily_series[strategy_ids[i]] else None
        for j in range(i + 1, n):
            a, b = daily_series[strategy_ids[i]], daily_series[strategy_ids[j]]
            common_days = sorted(set(a) & set(b))
            if len(common_days) < MIN_ALIGNED_DAYS:
                continue
            corr = _pearson([a[d] for d in common_days], [b[d] for d in common_days])
            if corr is not None:
                corr = round(corr, 3)
            matrix[i][j] = matrix[j][i] = corr

    return {"strategies": strategy_ids, "matrix": matrix, "min_aligned_days": MIN_ALIGNED_DAYS}

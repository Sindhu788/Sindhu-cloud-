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

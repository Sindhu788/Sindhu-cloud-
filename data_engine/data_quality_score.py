"""Data Quality Engine, surfacing layer (Additional Features, B3): turns
the existing deep per-DataFrame checks (data_engine.data_quality --
missing candles, duplicates, invalid timestamps, corrupted OHLC) into a
simple, live, per-symbol health score, kept entirely separate from
strategy performance -- a data problem must never be mistaken for (or
hidden behind) a strategy problem, or vice versa.

Nothing here re-implements the underlying checks; it only runs them on
each tracked symbol's recent data and aggregates the result into one 0-100
score plus a staleness reading (how old the most recent candle is)."""

import time

from data_engine import storage, data_quality
from data_engine.resample import get_ohlcv

_INTERVAL = "1h"
_LOOKBACK_HOURS = 72
_STALE_THRESHOLD_MINUTES = 180  # 3x a normal 1h bar -- generous, avoids false alarms on a quiet coin


def score_symbol(exchange, symbol):
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - _LOOKBACK_HOURS * 3600 * 1000
    df = get_ohlcv(exchange, symbol, interval=_INTERVAL, start_ms=start_ms, end_ms=end_ms)

    if df is None or len(df) == 0:
        return {"symbol": symbol, "score": 0, "stale": True, "last_bar_age_minutes": None,
                "issues": ["no data available at all"]}

    report = data_quality.run_data_quality_report(df, _INTERVAL)

    last_bar_ms = int(df.index[-1].timestamp() * 1000)
    age_minutes = round((end_ms - last_bar_ms) / 60000, 1)
    stale = age_minutes > _STALE_THRESHOLD_MINUTES

    score = 100
    issues = []
    if report["missing_candles"]:
        n = len(report["missing_candles"])
        score -= min(40, n * 5)
        issues.append(f"{n} gap(s) in candle history")
    if report["duplicate_candles"]:
        score -= 10
        issues.append(f"{len(report['duplicate_candles'])} duplicate candle(s)")
    if report["invalid_timestamps"]:
        score -= 20
        issues.extend(report["invalid_timestamps"])
    if report["corrupted_ohlc"]:
        n = len(report["corrupted_ohlc"])
        score -= min(30, n * 3)
        issues.append(f"{n} candle(s) with impossible OHLC values")
    if stale:
        score -= 20
        issues.append(f"most recent candle is {age_minutes:.0f} minutes old (expected under {_STALE_THRESHOLD_MINUTES})")

    return {
        "symbol": symbol, "score": max(0, score), "stale": stale,
        "last_bar_age_minutes": age_minutes, "issues": issues,
    }


def score_all_tracked_symbols(exchange):
    symbols = storage.load_symbols(exchange)
    results = []
    for symbol in symbols:
        try:
            results.append(score_symbol(exchange, symbol))
        except Exception as e:
            results.append({"symbol": symbol, "score": 0, "stale": True,
                             "last_bar_age_minutes": None, "issues": [f"check failed: {e!r}"]})
    overall = round(sum(r["score"] for r in results) / len(results), 1) if results else None
    return {
        "overall_score": overall,
        "symbols_checked": len(results),
        "symbols_with_issues": sum(1 for r in results if r["issues"]),
        "per_symbol": sorted(results, key=lambda r: r["score"]),
    }

"""A.1 -- Self-generated lessons from closed paper-trading positions. Every
time a position closes (win or loss), the Evolution Engine looks at THIS
strategy's aggregated trade history (already stored in paper_positions,
nothing new to collect) grouped by coin / session / market regime, and
turns any statistically meaningful pattern into a BOT lesson -- never a
narrative invention, always a direct readout of win-rate/RR numbers that
already exist. Every generated lesson's `derived_from` records the exact
bucket stats it came from, so it's traceable back to real trades on demand
(see bot_lesson.derived_from / storage.get_bot_lesson).

Pure aggregation + arithmetic. No AI, no ML, no randomness.
"""

from data_engine import storage
from evolution_engine import generation_manager

MIN_SAMPLE_SIZE = 10          # a bucket needs at least this many trades before its stats are trusted
HISTORY_LOOKBACK = 500        # how many of this strategy's most recent closed trades to analyze
SIGNIFICANT_WIN_RATE_GAP = 15.0   # percentage points vs overall win rate to be lesson-worthy
SIGNIFICANT_RR_GAP = 0.3          # average-RR difference vs overall to be lesson-worthy


def _book_key(position):
    """Same rule as paper_trading.guards.book_key, inlined rather than
    imported -- evolution_engine must not depend on paper_trading (or vice
    versa via a cycle); both independently encode the one-line "no
    strategy_id -> shared lessons book" convention."""
    return position.get("strategy_id") or "__lessons__"


def _lineage_key(book_key, dimension, value, metric):
    return f"{book_key}|{dimension}|{value}|{metric}"


def _find_existing_lineage(lineage_key):
    for lesson in storage.list_bot_lessons(status="active", limit=5000):
        if lesson.get("derived_from", {}).get("lineage_key") == lineage_key:
            return lesson["base_id"]
    return None


def _overall_stats(history):
    trades = len(history)
    wins = sum(1 for p in history if p.get("is_win"))
    rrs = [p["rr"] for p in history if p.get("rr") is not None]
    return {
        "trades": trades,
        "win_rate": (wins / trades * 100.0) if trades else 0.0,
        "avg_rr": (sum(rrs) / len(rrs)) if rrs else None,
    }


def _bucket_by(history, key_fn):
    buckets = {}
    for pos in history:
        key = key_fn(pos)
        if not key:
            continue
        b = buckets.setdefault(key, {"trades": 0, "wins": 0, "rr_sum": 0.0, "rr_n": 0, "position_ids": []})
        b["trades"] += 1
        if pos.get("is_win"):
            b["wins"] += 1
        if pos.get("rr") is not None:
            b["rr_sum"] += pos["rr"]
            b["rr_n"] += 1
        b["position_ids"].append(pos["id"])
    return buckets


def _emit_or_refine(now_iso, book_key, strategy_name, dimension, value, metric,
                     bucket_stat, overall_stat, sample_size, overall_sample_size, position_ids, title, description):
    key = _lineage_key(book_key, dimension, value, metric)
    derived_from = {
        "lineage_key": key,
        "strategy_id": book_key, "strategy_name": strategy_name,
        "dimension": dimension, "value": value, "metric": metric,
        "bucket_stat": round(bucket_stat, 2), "overall_stat": round(overall_stat, 2),
        "sample_size": sample_size, "overall_sample_size": overall_sample_size,
        "position_ids": position_ids[-50:],  # most recent contributing trades, capped
    }
    confidence = min(95.0, 40.0 + sample_size)  # more trades behind it -> higher confidence, capped
    base_id = _find_existing_lineage(key)
    if base_id:
        return generation_manager.create_next_lesson_generation(
            base_id, title, dimension + "_performance", description, derived_from, [], confidence, now_iso,
        )
    return generation_manager.create_new_lesson_lineage(
        title, dimension + "_performance", description, derived_from, [], confidence, now_iso,
    )


def analyze_and_generate_lessons(closed_position, now_iso):
    """Called once per closed position (paper_trading.position_manager._close,
    right after evolution.record_outcome). Returns the list of bot_lesson
    ids created or refined-to-a-new-generation this call -- empty if there
    isn't yet enough data, which is the common case for a young strategy."""
    book_key = _book_key(closed_position)
    strategy_name = closed_position.get("strategy_name") or "Unnamed strategy"
    history = storage.list_closed_paper_positions(limit=HISTORY_LOOKBACK, strategy_id=book_key)
    if len(history) < MIN_SAMPLE_SIZE:
        return []

    overall = _overall_stats(history)
    created = []

    # -- Coin performance: "Strategy X underperforms/outperforms on coin Y" --
    for symbol, b in _bucket_by(history, lambda p: p.get("symbol")).items():
        if b["trades"] < MIN_SAMPLE_SIZE:
            continue
        win_rate = b["wins"] / b["trades"] * 100.0
        gap = win_rate - overall["win_rate"]
        if abs(gap) < SIGNIFICANT_WIN_RATE_GAP:
            continue
        verb = "outperforms" if gap > 0 else "underperforms"
        title = f"{strategy_name} {verb} on {symbol}"
        description = (
            f"Win rate on {symbol} is {win_rate:.1f}% over {b['trades']} trades, vs {overall['win_rate']:.1f}% "
            f"overall across {overall['trades']} trades ({gap:+.1f} points)."
        )
        lesson_id = _emit_or_refine(now_iso, book_key, strategy_name, "coin", symbol, "win_rate",
                                     win_rate, overall["win_rate"], b["trades"], overall["trades"],
                                     b["position_ids"], title, description)
        if lesson_id:
            created.append(lesson_id)

    # -- Session performance: "Strategy X has a higher/lower win rate during session Z" --
    for session, b in _bucket_by(history, lambda p: p.get("session")).items():
        if b["trades"] < MIN_SAMPLE_SIZE:
            continue
        win_rate = b["wins"] / b["trades"] * 100.0
        gap = win_rate - overall["win_rate"]
        if abs(gap) < SIGNIFICANT_WIN_RATE_GAP:
            continue
        comp = "higher" if gap > 0 else "lower"
        title = f"{strategy_name} has a {comp} win rate during the {session} session"
        description = (
            f"Win rate during {session} is {win_rate:.1f}% over {b['trades']} trades, vs {overall['win_rate']:.1f}% "
            f"overall across {overall['trades']} trades ({gap:+.1f} points)."
        )
        lesson_id = _emit_or_refine(now_iso, book_key, strategy_name, "session", session, "win_rate",
                                     win_rate, overall["win_rate"], b["trades"], overall["trades"],
                                     b["position_ids"], title, description)
        if lesson_id:
            created.append(lesson_id)

    # -- Market-regime performance: "Strategy X's average RR drops when volatility is high" --
    if overall["avg_rr"] is not None:
        for regime, b in _bucket_by(history, lambda p: p.get("market_state")).items():
            if b["trades"] < MIN_SAMPLE_SIZE or b["rr_n"] < MIN_SAMPLE_SIZE:
                continue
            avg_rr = b["rr_sum"] / b["rr_n"]
            gap = avg_rr - overall["avg_rr"]
            if abs(gap) < SIGNIFICANT_RR_GAP:
                continue
            comp = "improves" if gap > 0 else "drops"
            title = f"{strategy_name}'s average RR {comp} when market regime is {regime}"
            description = (
                f"Average RR during '{regime}' regime is {avg_rr:.2f} over {b['rr_n']} trades, vs {overall['avg_rr']:.2f} "
                f"overall across {overall['trades']} trades ({gap:+.2f})."
            )
            lesson_id = _emit_or_refine(now_iso, book_key, strategy_name, "market_state", regime, "avg_rr",
                                         avg_rr, overall["avg_rr"], b["rr_n"], overall["trades"],
                                         b["position_ids"], title, description)
            if lesson_id:
                created.append(lesson_id)

    return created

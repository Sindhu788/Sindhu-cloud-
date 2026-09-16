"""Grand Master Batch #2, Phase 2.3: Signal Quality Calibration -- tracks
whether signals stated at "X% confidence" actually win close to X% of the
time, using only real closed paper trades. Purely read-only analysis, same
boundary paper_trading.challenge_analysis already documents for itself:
never touches a trade decision and is never called from any send/open
gate -- see paper_trading.telegram_bot's own gates (expected_value_check,
min_confidence_check, etc.) for the things that actually block a signal.

Deliberately NOT wired into the live Telegram message text: Grand Master
Batch's Phase 2.4 already reduced format_signal_message() to a fixed,
minimal set of fields on the CEO's own explicit request (see that
function's docstring) -- this module surfaces real calibration data on the
dashboard instead, so a stated confidence number is never silently
misleading without re-opening that very recent, deliberate decision about
what the channel itself shows.
"""

import time

from data_engine import storage

BUCKET_WIDTH = 10  # 0-10, 10-20, ..., 90-100
# Same "enough real evidence to trust a number" bar used everywhere else in
# this codebase (paper_trading.pattern_stats.MIN_SAMPLE_SIZE / the Wilson
# gate's own minimum).
MIN_TRUSTWORTHY_SAMPLE = 25

# 2026-09-17 (Investigation Batch, 1.1): confidence.score() now calls
# calibrated_win_rate_for() once per approved candidate every engine scan
# cycle (potentially dozens of times per tick across strategies/coins).
# compute_calibration_map() scans every closed paper position -- fine for
# an occasional dashboard request, too slow to redo on every single
# candidate. This tiny TTL cache is used ONLY by the use_cache=True path
# below (the hot engine-scoring path); the dashboard endpoint and every
# test in test_confidence_calibration.py keep calling
# compute_calibration_map() directly, so they stay exact and instantly
# reflect new data.
_CACHE_TTL_SECONDS = 30
_cache = {"map": None, "computed_at": 0.0}


def _cached_calibration_map(now=None):
    now = now if now is not None else time.time()
    if _cache["map"] is None or now - _cache["computed_at"] >= _CACHE_TTL_SECONDS:
        _cache["map"] = compute_calibration_map()
        _cache["computed_at"] = now
    return _cache["map"]


def invalidate_cache():
    """Tests (and anything that wants the very next cached lookup to see
    freshly-closed trades immediately) can force a recompute."""
    _cache["map"] = None
    _cache["computed_at"] = 0.0


def _bucket_index(confidence_pct):
    return min(int(confidence_pct // BUCKET_WIDTH), 9)  # clamp exactly 100% into the top bucket


def compute_calibration_map():
    """Returns a list of exactly 10 buckets, 0-10% through 90-100%, each:
    {"bucket_range", "stated_avg_confidence", "real_win_rate_pct",
    "sample_size", "trustworthy"}. A bucket with zero or too few real
    trades still appears (never dropped) with real_win_rate_pct=None and
    trustworthy=False -- an honest "not enough evidence yet", never a
    fabricated number."""
    rows = storage.list_closed_paper_positions(limit=1_000_000)
    buckets = {i: [] for i in range(10)}
    for r in rows:
        conf, pnl = r.get("confidence"), r.get("pnl")
        if conf is None or pnl is None:
            continue
        buckets[_bucket_index(conf)].append(r)

    out = []
    for i in range(10):
        group = buckets[i]
        lo, hi = i * BUCKET_WIDTH, i * BUCKET_WIDTH + BUCKET_WIDTH
        if not group:
            out.append({
                "bucket_range": f"{lo}-{hi}%", "stated_avg_confidence": None,
                "real_win_rate_pct": None, "sample_size": 0, "trustworthy": False,
            })
            continue
        wins = sum(1 for r in group if r["pnl"] > 0)
        out.append({
            "bucket_range": f"{lo}-{hi}%",
            "stated_avg_confidence": round(sum(r["confidence"] for r in group) / len(group), 1),
            "real_win_rate_pct": round(wins / len(group) * 100, 1),
            "sample_size": len(group),
            "trustworthy": len(group) >= MIN_TRUSTWORTHY_SAMPLE,
        })
    return out


def calibrated_win_rate_for(confidence_pct, use_cache=False):
    """For one signal's raw stated confidence: returns
    (real_win_rate_pct_or_None, trustworthy, sample_size) for whichever
    bucket it falls into. None/False when that bucket doesn't have
    MIN_TRUSTWORTHY_SAMPLE real trades yet -- never fabricated from too
    little evidence.

    use_cache=True (only paper_trading.confidence's live scoring path
    passes this) serves up to _CACHE_TTL_SECONDS-old calibration data
    instead of rescanning every closed position on every call -- see the
    cache docstring above. Every other caller (the dashboard endpoint,
    every test here) defaults to False and always sees live data."""
    if confidence_pct is None:
        return None, False, 0
    calibration = _cached_calibration_map() if use_cache else compute_calibration_map()
    bucket = calibration[_bucket_index(confidence_pct)]
    if not bucket["trustworthy"]:
        return None, False, bucket["sample_size"]
    return bucket["real_win_rate_pct"], True, bucket["sample_size"]

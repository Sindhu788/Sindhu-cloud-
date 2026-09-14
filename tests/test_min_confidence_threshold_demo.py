"""2026-09-14: real before/after demonstration for the "Minimum Confidence
to Send" setting (Phase 3.4's min_confidence_pct_to_send, already fully
built -- see paper_trading/telegram_bot.py's min_confidence_check() and its
wiring into send_signal_for_position(), and the Control Center's own UI
control at sindhu_web/static/js/app.js's masterControlsBodyHtml()).

Uses the REAL confidence.score() function (not fabricated numbers) against
five representative candidate/market combinations, then runs each through
the REAL min_confidence_check() at the default threshold (0, off) and again
at a raised threshold (65), to show the setting genuinely does nothing at
its default and genuinely filters once raised -- without touching the
Confluence ratio/count or Wilson 25-trade gates, which run earlier in
send_signal_for_position() and are untouched by this filter.
"""

from paper_trading import confidence, telegram_bot


def _candidate(source="strategy", strategy_id="s1", strategy_version=5, direction="bullish", lesson_ids=None):
    return {
        "source": source, "strategy_id": strategy_id, "strategy_version": strategy_version,
        "direction": direction, "lesson_ids": lesson_ids or [],
    }


def _snapshot(symbol="BTCUSDT", market_state="trending_up", session="london"):
    return {"symbol": symbol, "market_state": market_state, "session": session}


def test_real_confidence_scores_and_threshold_behavior(test_db, tmp_path, monkeypatch):
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))

    scenarios = [
        # (label, candidate, snapshot)
        ("trend-aligned, strong strategy", _candidate(strategy_version=10), _snapshot(market_state="trending_up", )),
        ("trend-aligned, weak strategy", _candidate(strategy_version=1), _snapshot(market_state="trending_up")),
        ("ranging market (penalized)", _candidate(strategy_version=5), _snapshot(market_state="ranging")),
        ("counter-trend (no bonus)", _candidate(strategy_version=5, direction="bearish"), _snapshot(market_state="trending_up")),
        ("lesson-sourced, conservative", _candidate(source="lesson", lesson_ids=["L1"]), _snapshot(market_state="trending_up")),
    ]

    computed = []
    for label, cand, snap in scenarios:
        score = confidence.score(cand, snap)
        computed.append((label, score))

    # Sanity: these are genuinely different, real values from the real
    # scoring function -- not a hardcoded fixture.
    assert len({s for _, s in computed}) >= 3, f"expected varied real scores, got {computed}"

    def positions_with(scores):
        return [{"id": f"p{i}", "confidence": s} for i, (_, s) in enumerate(scores)]

    # --- BEFORE: default threshold (0 = off) -- every position passes,
    # regardless of confidence, exactly as today.
    telegram_bot.save_settings(min_confidence_pct_to_send=0)
    before = [telegram_bot.min_confidence_check(p)[0] for p in positions_with(computed)]
    assert all(before), f"default threshold must never filter anything, got {list(zip(computed, before))}"

    # --- AFTER: CEO raises the threshold to 65% -- only positions whose
    # REAL computed confidence is >= 65 should still pass.
    telegram_bot.save_settings(min_confidence_pct_to_send=65)
    after = [telegram_bot.min_confidence_check(p)[0] for p in positions_with(computed)]
    expected = [score >= 65 for _, score in computed]
    assert after == expected, (
        f"raising the threshold should filter exactly the sub-65 real scores.\n"
        f"scenarios+scores: {computed}\nexpected pass/block: {expected}\nactual: {after}"
    )
    # It must actually filter at least one and pass at least one for this
    # to be a meaningful demonstration (not vacuously true).
    assert any(after) and not all(after), (
        f"demo scenarios should span both sides of 65% -- got scores {computed}"
    )

    print("\nReal confidence scores (from confidence.score(), not fabricated):")
    for label, score in computed:
        print(f"  {label}: {score}%")
    print("At threshold=0 (default): all pass ->", before)
    print("At threshold=65: pass/block ->", after)

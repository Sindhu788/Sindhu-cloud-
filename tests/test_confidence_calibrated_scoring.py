"""Investigation Batch 2026-09-17, item 1.1: real evidence showed
paper_trading.confidence.score() was badly miscalibrated -- a recent
50-trade sample stated ~75.8% average confidence but had an 18% real win
rate. confidence.score() now looks up its raw heuristic value in
paper_trading.confidence_calibration's real calibration map and returns
the REAL historical win rate for that bucket once there's enough evidence
(confidence_calibration.MIN_TRUSTWORTHY_SAMPLE), falling back to the raw
heuristic only when a bucket doesn't have enough real trades yet.
"""

from data_engine import config as base_config, storage
from paper_trading import confidence, confidence_calibration


def _candidate(source="strategy", strategy_id="s1", strategy_version=5, direction="bullish", lesson_ids=None):
    return {
        "source": source, "strategy_id": strategy_id, "strategy_version": strategy_version,
        "direction": direction, "lesson_ids": lesson_ids or [],
    }


def _snapshot(symbol="BTCUSDT", market_state="trending_up", session="london"):
    return {"symbol": symbol, "market_state": market_state, "session": session}


def _close_trade(pid, conf, pnl):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy", "confidence": conf,
    })
    storage.close_paper_position(
        pid, 100.0 + pnl, 1700000600000, pnl, pnl, "take_profit", {}, {}, "2026-01-02T00:00:00+00:00",
    )


def test_falls_back_to_raw_heuristic_when_no_real_history(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    cand, snap = _candidate(strategy_version=10), _snapshot()
    raw = confidence._raw_score(cand, snap)
    scored = confidence.score(cand, snap)
    assert scored == raw, "with zero real closed trades, no bucket can be trustworthy yet"


def test_uses_real_calibrated_win_rate_once_bucket_has_enough_evidence(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    cand, snap = _candidate(strategy_version=10), _snapshot()
    raw = confidence._raw_score(cand, snap)
    assert 80.0 <= raw < 90.0, f"test assumes this candidate's raw score lands in 80-90%, got {raw}"

    # 30 real trades stated at this exact raw score: only 6 wins (20% real
    # win rate) -- deliberately far below the raw heuristic's own number,
    # mirroring the real 75.8%-stated/18%-real gap this fix addresses.
    for i in range(6):
        _close_trade(f"w{i}", raw, 10.0)
    for i in range(24):
        _close_trade(f"l{i}", raw, -5.0)
    confidence_calibration.invalidate_cache()

    scored = confidence.score(cand, snap)
    assert scored == 20.0, f"expected the real 20% bucket win rate, got {scored} (raw was {raw})"
    assert scored != raw


def test_calibration_cache_is_ttl_bounded_not_permanently_stale(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    cand, snap = _candidate(strategy_version=10), _snapshot()
    raw = confidence._raw_score(cand, snap)

    for i in range(25):
        _close_trade(f"w{i}", raw, 10.0)  # 100% real win rate in this bucket
    confidence_calibration.invalidate_cache()

    first = confidence.score(cand, snap)
    assert first == 100.0

    # New real trades close with a much worse outcome. Without invalidating
    # the cache, the stale map would still be served (by design, for
    # _CACHE_TTL_SECONDS) -- but invalidate_cache() (used above and by any
    # code that wants the next scan cycle to see it) proves the cache is
    # genuinely refreshable, not frozen at import time.
    for i in range(25):
        _close_trade(f"l{i}", raw, -5.0)
    confidence_calibration.invalidate_cache()
    second = confidence.score(cand, snap)
    assert second < first

"""Master Task 6, 2.3/2.4 -- engine-level wiring test: both the HTF
Confluence Filter and the Volume/Volatility Filter must be OFF by default
(an existing strategy's behavior is unchanged) and only ever reject a
candidate when this exact strategy has explicitly opted in via
paper_strategy_config."""

from unittest.mock import patch

from data_engine import storage
from paper_trading.engine import PaperTradingEngine


def _candidate(direction="bullish", timeframe="15m"):
    return {
        "direction": direction, "timeframe": timeframe, "confidence": 80,
        "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "entry_reason": "test", "strategy_id": "strat_a", "strategy_name": "Strat A",
        "lesson_ids": [],
    }


def _snapshot(volume_spike=False, market_state="trending_up"):
    return {"market_state": market_state, "session": "london", "volume_spike": volume_spike, "price": 100.0}


def _last_decision():
    decisions = storage.list_paper_decisions(limit=1)
    return decisions[0] if decisions else None


def test_htf_filter_off_by_default_never_blocks(test_db):
    engine = PaperTradingEngine()
    with patch("paper_trading.engine.htf_confluence_filter.check", return_value=(False, "would have blocked")):
        opened, rejected = engine._open_if_allowed(
            "strat_a", "binance", "BTCUSDT", _candidate(), _snapshot(), {"dry_run": True},
        )
    # Not opened for real (dry_run), but not rejected by the HTF filter either --
    # it must fall through to the normal dry-run path untouched.
    assert rejected == 0


def test_htf_filter_blocks_when_explicitly_enabled_for_this_strategy(test_db):
    storage.set_strategy_signal_filter_overrides("strat_a", True, None, None, "2026-01-01T00:00:00+00:00")
    engine = PaperTradingEngine()
    with patch("paper_trading.engine.htf_confluence_filter.check",
               return_value=(False, "HTF confluence filter: 1h structural trend is down, contradicts this bullish signal")):
        opened, rejected = engine._open_if_allowed(
            "strat_a", "binance", "BTCUSDT", _candidate(), _snapshot(), {"dry_run": True},
        )
    assert (opened, rejected) == (0, 1)
    engine._flush_decisions()  # decisions are buffered per-tick now, not written immediately
    decision = _last_decision()
    assert "HTF confluence filter" in decision["reason"]


def test_volume_filter_off_by_default_never_blocks(test_db):
    engine = PaperTradingEngine()
    opened, rejected = engine._open_if_allowed(
        "strat_a", "binance", "BTCUSDT", _candidate(), _snapshot(volume_spike=False), {"dry_run": True},
    )
    assert rejected == 0


def test_volume_filter_blocks_when_enabled_and_no_spike(test_db):
    storage.set_strategy_signal_filter_overrides("strat_a", None, True, None, "2026-01-01T00:00:00+00:00")
    engine = PaperTradingEngine()
    opened, rejected = engine._open_if_allowed(
        "strat_a", "binance", "BTCUSDT", _candidate(), _snapshot(volume_spike=False), {"dry_run": True},
    )
    assert (opened, rejected) == (0, 1)
    engine._flush_decisions()  # decisions are buffered per-tick now, not written immediately
    decision = _last_decision()
    assert "Volume/Volatility filter" in decision["reason"]


def test_volume_filter_allows_when_enabled_and_spike_present(test_db):
    storage.set_strategy_signal_filter_overrides("strat_a", None, True, None, "2026-01-01T00:00:00+00:00")
    engine = PaperTradingEngine()
    opened, rejected = engine._open_if_allowed(
        "strat_a", "binance", "BTCUSDT", _candidate(), _snapshot(volume_spike=True), {"dry_run": True},
    )
    # Passes the volume gate -- falls through to the normal dry-run path (not rejected).
    assert rejected == 0


def test_a_different_strategys_config_is_never_affected(test_db):
    """Enabling a filter for strat_a must never affect strat_b's own,
    independent book."""
    storage.set_strategy_signal_filter_overrides("strat_a", None, True, None, "2026-01-01T00:00:00+00:00")
    engine = PaperTradingEngine()
    opened, rejected = engine._open_if_allowed(
        "strat_b", "binance", "BTCUSDT", _candidate(), _snapshot(volume_spike=False), {"dry_run": True},
    )
    assert rejected == 0

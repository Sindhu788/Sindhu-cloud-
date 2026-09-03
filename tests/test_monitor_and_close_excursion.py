"""Grand Feature Expansion, Phase 3 Feature 8: confirms
paper_trading.position_manager.monitor_and_close() actually widens a
position's MAE/MFE excursion range on every tick (via
storage.update_position_excursion), not just at close time -- including
on the very tick a position exits, so the exit wick itself still counts.
"""

from data_engine import storage
from paper_trading import position_manager


def _open(position_id, direction="long", entry_price=100.0, stop_loss=90.0, take_profit=120.0):
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": direction,
        "entry_price": entry_price, "stop_loss": stop_loss, "take_profit": take_profit,
        "size": 1.0, "risk_amount": 5.0, "entry_time": 1700000000000,
        "created_at": "2026-01-01T00:00:00+00:00", "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })


def test_a_tick_that_does_not_close_still_widens_the_excursion_range(test_db):
    _open("p1")
    position_manager.monitor_and_close("binance", "BTCUSDT", latest_price=105.0, high=108.0, low=95.0)

    pos = storage.get_paper_position("p1")
    assert pos["status"] == "open"
    assert pos["lowest_price_seen"] == 95.0
    assert pos["highest_price_seen"] == 108.0


def test_excursion_widens_across_multiple_ticks(test_db):
    _open("p1")
    position_manager.monitor_and_close("binance", "BTCUSDT", latest_price=105.0, high=108.0, low=95.0)
    position_manager.monitor_and_close("binance", "BTCUSDT", latest_price=98.0, high=99.0, low=80.0)

    pos = storage.get_paper_position("p1")
    assert pos["lowest_price_seen"] == 80.0
    assert pos["highest_price_seen"] == 108.0


def test_the_exit_triggering_wick_itself_counts_toward_excursion(test_db):
    _open("p1", stop_loss=90.0)
    # A tick whose low touches the stop-loss (triggering exit) -- that low
    # must still be recorded as part of this trade's real excursion.
    closed = position_manager.monitor_and_close("binance", "BTCUSDT", latest_price=95.0, high=96.0, low=88.0)

    assert len(closed) == 1
    pos = storage.get_paper_position("p1")
    assert pos["status"] == "closed"
    assert pos["lowest_price_seen"] == 88.0


def test_falls_back_to_latest_price_when_high_low_are_unavailable(test_db):
    """The orphaned-position monitoring path (paper_trading.engine's
    _monitor_orphaned_positions) only ever has a ticker price, no
    high/low -- excursion tracking must degrade gracefully, not error."""
    _open("p1")
    position_manager.monitor_and_close("binance", "BTCUSDT", latest_price=93.0)
    pos = storage.get_paper_position("p1")
    assert pos["lowest_price_seen"] == 93.0
    assert pos["highest_price_seen"] == 100.0  # unchanged from the seeded entry_price -- 93 < 100 only lowered the low

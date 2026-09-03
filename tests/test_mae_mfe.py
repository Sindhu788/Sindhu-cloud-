"""Grand Feature Expansion, Phase 3 Feature 8: Maximum Adverse/Favorable
Excursion (MAE/MFE) -- how far a trade moved against (MAE) and in favor of
(MFE) the position before it closed, regardless of the final outcome.
Raw lowest/highest price seen is tracked tick-by-tick (data_engine.storage
.update_position_excursion, direction-agnostic); mae_amount/mfe_amount are
DERIVED at read time from those plus entry_price/direction/size (same
"don't store what you can recompute" convention this table already uses
for is_win/rr).
"""

from data_engine import storage


def _open(position_id, direction, entry_price=100.0, size=1.0):
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": direction,
        "entry_price": entry_price, "size": size, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })


def test_freshly_opened_position_has_zero_excursion(test_db):
    _open("p1", "long")
    pos = storage.get_paper_position("p1")
    assert pos["lowest_price_seen"] == 100.0
    assert pos["highest_price_seen"] == 100.0
    assert pos["mae_amount"] == 0.0
    assert pos["mfe_amount"] == 0.0


def test_long_position_mae_is_the_dip_and_mfe_is_the_run_up(test_db):
    _open("p1", "long", entry_price=100.0, size=2.0)
    storage.update_position_excursion("p1", tick_low=90.0, tick_high=95.0)  # dipped to 90 first
    storage.update_position_excursion("p1", tick_low=98.0, tick_high=120.0)  # then ran up to 120

    pos = storage.get_paper_position("p1")
    assert pos["lowest_price_seen"] == 90.0
    assert pos["highest_price_seen"] == 120.0
    assert pos["mae_amount"] == (90.0 - 100.0) * 2.0  # -20.0 -- the worst unrealized dip, in dollars
    assert pos["mfe_amount"] == (120.0 - 100.0) * 2.0  # +40.0 -- the best unrealized run-up


def test_short_position_mae_and_mfe_are_direction_flipped(test_db):
    _open("p1", "short", entry_price=100.0, size=1.0)
    storage.update_position_excursion("p1", tick_low=95.0, tick_high=110.0)  # rose to 110 (bad for a short) first
    storage.update_position_excursion("p1", tick_low=80.0, tick_high=105.0)  # then fell to 80 (good for a short)

    pos = storage.get_paper_position("p1")
    assert pos["mae_amount"] == (100.0 - 110.0) * 1.0  # -10.0 -- price rose against the short
    assert pos["mfe_amount"] == (100.0 - 80.0) * 1.0   # +20.0 -- price fell in the short's favor


def test_excursion_range_only_ever_widens_never_narrows(test_db):
    _open("p1", "long")
    storage.update_position_excursion("p1", tick_low=95.0, tick_high=105.0)
    storage.update_position_excursion("p1", tick_low=98.0, tick_high=102.0)  # a narrower tick -- must not shrink the range
    pos = storage.get_paper_position("p1")
    assert pos["lowest_price_seen"] == 95.0
    assert pos["highest_price_seen"] == 105.0


def test_excursion_update_is_a_no_op_once_the_position_is_closed(test_db):
    _open("p1", "long")
    storage.close_paper_position("p1", 105.0, 1700000100000, 5.0, 5.0, "take_profit", {}, {}, "2026-01-02T00:00:00+00:00")
    storage.update_position_excursion("p1", tick_low=50.0, tick_high=200.0)  # must be ignored -- position is closed
    pos = storage.get_paper_position("p1")
    assert pos["lowest_price_seen"] == 100.0  # unchanged (seeded at entry, never touched again)
    assert pos["highest_price_seen"] == 100.0


def test_a_winning_trade_can_still_have_a_real_mae(test_db):
    """The whole point of this feature: a trade that ended up a winner
    might still have gone significantly against the position first."""
    _open("p1", "long", entry_price=100.0)
    storage.update_position_excursion("p1", tick_low=85.0, tick_high=100.0)  # scary dip to 85 first
    storage.update_position_excursion("p1", tick_low=100.0, tick_high=110.0)  # then recovered and ran up to 110
    storage.close_paper_position("p1", 110.0, 1700000100000, 10.0, 10.0, "take_profit", {}, {}, "2026-01-02T00:00:00+00:00")

    pos = storage.get_paper_position("p1")
    assert pos["pnl"] == 10.0  # a real winner...
    assert pos["mae_amount"] < 0  # ...that still had a genuine adverse excursion along the way

"""Part 2 of the Telegram/Multi-Strategy/Challenge-Mode task: real,
database-backed proof that concurrent strategies track independently.

This constructs a realistic 3-strategy scenario against an isolated test
database (never the real one) and asserts, from real stored rows -- not
from reading the source and trusting the docstrings -- that:

  1. Each strategy's balance/PnL/win-rate/trade-count is independent.
  2. Each strategy's max-coin limit is enforced independently.
  3. Opposite signals on the same coin from different strategies are both
     allowed, with no interference.
  4. Position lock, cooldown, duplicate-signal protection and opposite-
     signal protection are all book (per-strategy) scoped -- one
     strategy's guard state never blocks a different strategy.
  5. Closing one strategy's position never mutates another strategy's
     records.

Strategy ids used are clearly test artifacts: TEST_STRAT_A/B/C.
"""

from datetime import datetime, timezone

import pytest

from data_engine import storage
from paper_trading import guards, position_manager, risk_manager

STRAT_A = "TEST_STRAT_A"
STRAT_B = "TEST_STRAT_B"
STRAT_C = "TEST_STRAT_C"

EXCHANGE = "binance"
SETTINGS = {"max_open_trades": 5, "initial_balance": 10000.0, "risk_pct_default": 1.0}


def _candidate(strategy_id, symbol, direction, entry, sl, tp, name=None):
    return {
        "direction": direction, "entry_price": entry, "stop_loss": sl, "take_profit": tp,
        "entry_reason": "test scenario", "strategy_id": strategy_id,
        "strategy_name": name or strategy_id, "strategy_version": "v1",
        "lesson_ids": [], "timeframe": "1h", "stop_loss_type": "structure",
    }


def _snapshot():
    return {"market_state": "trending_up", "session": "london", "volume_spike": False, "structure": False}


def _open(strategy_id, symbol, direction, entry, sl, tp):
    cand = _candidate(strategy_id, symbol, direction, entry, sl, tp)
    approved, reason, size, risk_amount = risk_manager.evaluate(strategy_id, symbol, cand, SETTINGS)
    assert approved, f"expected approval for {strategy_id}/{symbol}: {reason}"
    pos = position_manager.open_position(EXCHANGE, symbol, cand, size, risk_amount, confidence=0.9,
                                          market_snapshot=_snapshot())
    return pos


# ------------------------------------------------------------- 1 & 5: independent balance/PnL/win-rate/trade-count

def test_balance_pnl_and_stats_are_independent_and_closing_one_never_touches_another(test_db):
    posA = _open(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)
    posB = _open(STRAT_B, "BTCUSDT", "bearish", 100.0, 105.0, 90.0)
    posC = _open(STRAT_C, "ETHUSDT", "bullish", 100.0, 95.0, 110.0)

    balA_before = risk_manager.account_balance(STRAT_A, SETTINGS["initial_balance"])
    balB_before = risk_manager.account_balance(STRAT_B, SETTINGS["initial_balance"])
    balC_before = risk_manager.account_balance(STRAT_C, SETTINGS["initial_balance"])
    assert balA_before == balB_before == balC_before == SETTINGS["initial_balance"]

    # Close only strategy A's position at a WIN.
    position_manager._close(posA, 110.0, "take_profit")

    balA_after = risk_manager.account_balance(STRAT_A, SETTINGS["initial_balance"])
    balB_after = risk_manager.account_balance(STRAT_B, SETTINGS["initial_balance"])
    balC_after = risk_manager.account_balance(STRAT_C, SETTINGS["initial_balance"])

    assert balA_after > balA_before, "strategy A's balance should reflect its own win"
    assert balB_after == balB_before, "strategy B's balance must be untouched by A's close"
    assert balC_after == balC_before, "strategy C's balance must be untouched by A's close"

    # Strategy B and C's positions are still open and unmutated.
    stillB = storage.get_paper_position(posB["id"])
    stillC = storage.get_paper_position(posC["id"])
    assert stillB["status"] == "open" and stillB["exit_price"] is None
    assert stillC["status"] == "open" and stillC["exit_price"] is None

    stats = {s["strategy_id"]: s for s in storage.list_paper_strategy_stats()}
    assert stats[STRAT_A]["closed_trades"] == 1
    assert stats[STRAT_A]["win_count"] == 1
    assert stats[STRAT_A]["win_rate"] == 100.0
    assert STRAT_B not in stats, "B has no closed trades yet -- must not appear merged with A"
    assert STRAT_C not in stats


# ------------------------------------------------------------- 2: independent per-strategy coin limit

def test_max_coin_limit_is_enforced_independently_per_strategy(test_db):
    tight_settings = {**SETTINGS, "max_open_trades": 1}
    _open(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)

    # Strategy A is now at its (tight) 1-coin cap -- a second, DIFFERENT
    # coin must be rejected for A specifically.
    cand_eth_a = _candidate(STRAT_A, "ETHUSDT", "bullish", 2000.0, 1900.0, 2200.0)
    approved_a, reason_a, _, _ = risk_manager.evaluate(STRAT_A, "ETHUSDT", cand_eth_a, tight_settings)
    assert approved_a is False
    assert "max coins" in reason_a

    # Strategy B, evaluated under the SAME tight limit but with zero open
    # coins of its own, must still be approved -- the cap is per-book.
    cand_eth_b = _candidate(STRAT_B, "ETHUSDT", "bullish", 2000.0, 1900.0, 2200.0)
    approved_b, reason_b, size_b, risk_b = risk_manager.evaluate(STRAT_B, "ETHUSDT", cand_eth_b, tight_settings)
    assert approved_b is True, reason_b


# ------------------------------------------------------------- 3: opposite signals, same coin, different strategies

def test_opposite_direction_signals_same_coin_different_strategies_both_allowed(test_db):
    posA = _open(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)
    posB = _open(STRAT_B, "BTCUSDT", "bearish", 100.0, 105.0, 90.0)

    open_btc = storage.get_open_paper_positions(EXCHANGE, "BTCUSDT")
    directions = {(p["strategy_id"], p["direction"]) for p in open_btc}
    assert (STRAT_A, "long") in directions
    assert (STRAT_B, "short") in directions
    assert len(open_btc) == 2, "both opposite-direction positions from different strategies must coexist"


# ------------------------------------------------------------- 4a: Position Lock is book-scoped

def test_position_lock_is_book_scoped_not_shared(test_db):
    _open(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)

    # Strategy A already has an open BTC long -> locked for A.
    assert guards.position_locked(STRAT_A, EXCHANGE, "BTCUSDT", "long") is True
    # Strategy B has no position at all on BTC -> must NOT be locked by A's.
    assert guards.position_locked(STRAT_B, EXCHANGE, "BTCUSDT", "long") is False


# ------------------------------------------------------------- 4b: Cooldown is book-scoped

def test_cooldown_is_book_scoped_not_shared(test_db):
    posA = _open(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)
    position_manager._close(posA, 95.0, "stop_loss")

    # Strategy A just closed a BTC long -> its own cooldown is active.
    assert guards.cooldown_active(STRAT_A, EXCHANGE, "BTCUSDT", "long", cooldown_minutes=30) is True
    # Strategy B never traded BTC -> its cooldown must be unaffected by A's close.
    assert guards.cooldown_active(STRAT_B, EXCHANGE, "BTCUSDT", "long", cooldown_minutes=30) is False


# ------------------------------------------------------------- 4c: Duplicate-signal fingerprint includes the book

def test_duplicate_signal_fingerprint_differs_per_strategy(test_db):
    candA = _candidate(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)
    candB = _candidate(STRAT_B, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)
    fpA = guards.signal_fingerprint(EXCHANGE, "BTCUSDT", candA)
    fpB = guards.signal_fingerprint(EXCHANGE, "BTCUSDT", candB)
    assert fpA != fpB, "identical market condition from two different strategies must not collide in the decision cache"

    state = guards.GuardState()
    assert state.is_duplicate(fpA) is False  # first time for A -- not a duplicate
    assert state.is_duplicate(fpB) is False  # first time for B, even though same coin/direction -- not a duplicate
    assert state.is_duplicate(fpA) is True   # A repeating immediately -- IS a duplicate for A
    assert state.is_duplicate(fpB) is True   # B repeating immediately -- IS a duplicate for B (independently)


# ------------------------------------------------------------- 4d: Trade Reservation is book-scoped

def test_trade_reservation_is_book_scoped_not_shared():
    state = guards.GuardState()
    assert state.reserve(STRAT_A, EXCHANGE, "BTCUSDT") is True
    # Same strategy reserving the same coin again in the same tick -> blocked.
    assert state.reserve(STRAT_A, EXCHANGE, "BTCUSDT") is False
    # A DIFFERENT strategy reserving the SAME coin in the SAME tick -> allowed.
    assert state.reserve(STRAT_B, EXCHANGE, "BTCUSDT") is True


# ------------------------------------------------------------- 4e: Opposite-signal protection only governs one book

def test_opposite_signal_protection_only_applies_within_one_strategys_own_book(test_db):
    # resolve_opposite_signal is called with "long"/"short" (the same
    # vocabulary paper_positions.direction stores) -- see engine.py:356-367,
    # where `side` is already converted from the candidate's "bullish"/
    # "bearish" before being passed in.
    _open(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)

    # Strategy B has no open BTC position of its own -- resolve_opposite_signal
    # for B must see "proceed" regardless of A's opposite-direction position,
    # because it only ever looks at B's own book.
    outcome, detail = guards.resolve_opposite_signal(STRAT_B, EXCHANGE, "BTCUSDT", "short", policy="block")
    assert outcome == "proceed"

    # Now open B's own long BTC position, then have B signal short again --
    # THIS should trigger B's own opposite-signal policy.
    _open(STRAT_B, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)
    outcome2, detail2 = guards.resolve_opposite_signal(STRAT_B, EXCHANGE, "BTCUSDT", "short", policy="block")
    assert outcome2 == "block"


def test_opposite_signal_protection_was_previously_dead_code_now_fixed(test_db):
    """Regression guard for the confirmed bug this audit found: the
    vocabulary mismatch ("bullish"/"bearish" vs the real "long"/"short")
    meant opposite_open_position() could NEVER find a real stored position,
    so resolve_opposite_signal() always returned "proceed" no matter what.
    Directly exercises opposite_open_position() to prove it now finds the
    real stored row."""
    _open(STRAT_A, "BTCUSDT", "bullish", 100.0, 95.0, 110.0)  # stored direction: "long"
    found = guards.opposite_open_position(STRAT_A, EXCHANGE, "BTCUSDT", "short")
    assert found is not None
    assert found["direction"] == "long"

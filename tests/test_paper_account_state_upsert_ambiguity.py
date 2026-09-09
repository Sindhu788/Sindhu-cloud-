"""Urgent bug fix, 2026-09-09: confirmed live -- close_paper_position()'s
paper_account_state upsert crashed on Postgres with AmbiguousColumn
('column reference "realized_pnl_total" is ambiguous') on EVERY tick
that had a position to check, for 3+ hours straight. Because this
INSERT shares one connection/transaction with the preceding
paper_positions UPDATE, the failure rolled that back too -- the position
was never actually marked closed, so the next tick hit the same SL/TP
and repeated the identical failure forever. Table-qualifying the ON
CONFLICT DO UPDATE SET's right-hand-side column references
(paper_account_state.col) removes the ambiguity outright.
"""
from data_engine import storage


def _open_position(**overrides):
    pos = {
        "id": overrides.pop("id", "pos1"), "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _close(position_id, pnl, closed_at="2026-01-01T01:00:00+00:00", book_key="strat1"):
    storage.close_paper_position(
        position_id, exit_price=105.0, exit_time=1700003600000, pnl=pnl, pnl_pct=5.0,
        exit_reason="take_profit", lifecycle={}, reflection=None, closed_at=closed_at,
        book_key=book_key,
    )


def test_upsert_sql_text_qualifies_the_ambiguous_columns():
    """Regression guard: the exact bug was bare column names on the
    right of `=` in ON CONFLICT DO UPDATE SET -- lock in the qualified
    form so it can never silently regress."""
    import inspect
    source = inspect.getsource(storage.close_paper_position)
    assert "paper_account_state.realized_pnl_total + excluded.realized_pnl_total" in source
    assert "paper_account_state.closed_count + 1" in source
    assert "paper_account_state.win_count + excluded.win_count" in source


def test_single_close_creates_the_account_state_row(test_db):
    _open_position(id="pos1")
    _close("pos1", pnl=50.0)

    summary = storage.get_paper_account_summary("strat1")
    assert summary["realized_pnl_total"] == 50.0
    assert summary["closed_count"] == 1
    assert summary["win_count"] == 1


def test_multiple_closes_accumulate_via_the_on_conflict_path(test_db):
    """This is the exact code path the ambiguous-column bug broke --
    the SECOND (and later) close for the same strategy must hit
    ON CONFLICT DO UPDATE, not a fresh INSERT."""
    _open_position(id="pos1")
    _open_position(id="pos2")
    _open_position(id="pos3")
    _close("pos1", pnl=50.0)
    _close("pos2", pnl=-20.0)
    _close("pos3", pnl=30.0)

    summary = storage.get_paper_account_summary("strat1")
    assert summary["realized_pnl_total"] == 60.0
    assert summary["closed_count"] == 3
    assert summary["win_count"] == 2


def test_closing_also_commits_the_position_status_update(test_db):
    """The other half of the real incident: a failure in the account-
    state upsert used to roll back the paper_positions status update
    too (same connection/transaction), leaving the position stuck open
    forever. Confirm the position row itself is genuinely closed."""
    _open_position(id="pos1")
    _close("pos1", pnl=50.0)

    position = storage.get_paper_position("pos1")
    assert position["status"] == "closed"
    assert position["pnl"] == 50.0

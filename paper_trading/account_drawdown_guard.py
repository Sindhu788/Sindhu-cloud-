"""Account-wide Drawdown Circuit-Breaker (Grand Feature Expansion, Phase 1
Feature 5): unlike drawdown_guard.py (per-strategy, one book's own peak),
this compares the COMBINED balance across every book against its own
all-time peak and halts NEW entries for every strategy at once once a
configured percentage drop is crossed.

Deliberately does NOT close any open position and does NOT touch
telegram/engine state -- it only blocks new trade approval (checked in
risk_manager.evaluate, same gate as kill_switch). For an instant, harder
stop that also closes positions, that is what kill_switch.py is for.

Re-evaluated on every position close (paper_trading.position_manager),
same trigger point drawdown_guard.evaluate_strategy already uses -- cheap
(reads paper_account_state once, no full engine.status() computation) and
catches every point balance can actually move.

Same accepted convention paper_trading.insights.compute_risk_metrics
already uses for the per-strategy Max/Current Drawdown %: the peak starts
at whatever combined balance this module FIRST observes, not some
hypothetical pre-history genesis value -- so the very first trade this
account ever closes can never itself register a drawdown (there is no
earlier peak to fall from yet). In practice the engine calls this
repeatedly from the moment trading starts, so the peak is established
almost immediately; only a single catastrophic first-ever trade would be
invisible to this specific check (the kill switch remains available as a
manual, instant backstop regardless).
"""

from datetime import datetime, timezone

from data_engine import storage
from paper_trading import config as pt_config


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _combined_balance():
    settings = pt_config.load()
    initial_balance = settings.get("initial_balance", 10000.0)
    states = storage.list_paper_account_states()
    open_positions = storage.get_open_paper_positions()
    books = {s["strategy_id"] for s in states}
    books |= {p.get("strategy_id") or "__lessons__" for p in open_positions}
    realized_by_book = {s["strategy_id"]: s["realized_pnl_total"] for s in states}
    return initial_balance * len(books) + sum(realized_by_book.get(b, 0.0) for b in books)


def status():
    state = storage.get_account_drawdown_state()
    combined = _combined_balance()
    if not state:
        return {"paused": False, "paused_reason": None, "peak_balance": combined,
                "current_balance": combined, "drawdown_pct": 0.0}
    peak = max(state["peak_balance"], combined)
    drawdown_pct = ((peak - combined) / peak * 100) if peak > 0 else 0.0
    return {"paused": state["paused"], "paused_reason": state["paused_reason"],
            "peak_balance": peak, "current_balance": combined, "drawdown_pct": round(drawdown_pct, 2)}


def is_globally_paused():
    state = storage.get_account_drawdown_state()
    return bool(state and state["paused"])


def evaluate_account():
    """Re-checks combined balance against its all-time peak and pauses new
    entries system-wide if the configured threshold is crossed. Returns the
    pause reason if a pause was (newly) applied this call, else None. Never
    un-pauses itself -- see resume_account() for the explicit, deliberate
    reversal (mirrors drawdown_guard.evaluate_strategy/resume_strategy)."""
    state = storage.get_account_drawdown_state()
    if state and state["paused"]:
        return None  # already paused; don't re-trigger/overwrite the reason

    combined = _combined_balance()
    peak = max(state["peak_balance"], combined) if state else combined
    threshold_pct = pt_config.load().get("account_drawdown_pause_pct_threshold", 20.0)
    drawdown_pct = ((peak - combined) / peak * 100) if peak > 0 else 0.0

    if drawdown_pct >= threshold_pct:
        reason = (f"combined account balance dropped {drawdown_pct:.1f}% from its all-time peak "
                  f"(threshold: {threshold_pct:.0f}%). New trades paused for EVERY strategy; "
                  f"existing open positions are unaffected.")
        storage.update_account_drawdown_state(peak, True, reason, _now_iso(), _now_iso())
        from sindhu_web import sync
        sync.notify("account_drawdown", "paused", reason)
        return reason

    storage.update_account_drawdown_state(peak, False, None, None, _now_iso())
    return None


def resume_account(actor="CEO"):
    """Reverses a system-wide pause -- an explicit, deliberate action, same
    contract as drawdown_guard.resume_strategy. Always safe to call even if
    not currently paused."""
    state = storage.get_account_drawdown_state()
    peak = state["peak_balance"] if state else _combined_balance()
    storage.update_account_drawdown_state(peak, False, None, None, _now_iso())

    from sindhu_web import sync
    sync.notify("account_drawdown", "resumed", f"Account-wide drawdown pause cleared by {actor}")

"""Strategy Lab: on a weekly schedule, honestly checks whether any real
strategy has become genuinely profitable -- real, after-cost paper trading
results, with a meaningful number of closed trades behind them. Reuses
storage.list_paper_strategy_stats(), the exact same all-time win_rate/
total_pnl/closed_trades numbers already shown on the Paper Trading and
Reports pages -- nothing new is computed here, only judged against a bar
and reported.

If nothing clears the bar, the scan is still saved (qualifying_strategy_id
stays NULL) so "no profitable strategy yet" is a real, dated fact, not a
guess -- the dashboard must say so plainly rather than showing whichever
strategy merely lost the least. A qualifying strategy is never fed into
live Paper Trading or Telegram automatically -- see approve_candidate()
below, which only ever runs from an explicit CEO click.
"""

from datetime import datetime, timezone, timedelta

from data_engine import storage, feature_toggles
from backtest_engine import strategy_library as lib

SCAN_INTERVAL_DAYS = 7
# A strategy must clear ALL three bars to count as "genuinely profitable":
# real money edge (net positive after cost), a win rate that isn't just
# a few lucky trades, and enough closed trades that the first two numbers
# mean something. 25 matches the same statistical floor already used
# elsewhere in this project (Signal Tracker's win-rate reveal, System
# Maturity's Level 2 threshold) -- one consistent bar for "enough real
# trades to trust a number," not a new one invented for this feature.
MIN_CLOSED_TRADES = 25
MIN_WIN_RATE = 50.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def scan_for_profitable_strategy():
    """Checks every strategy's real, all-time paper trading record and
    saves one scan row. Returns the saved scan dict. Picks at most ONE
    qualifying strategy (the highest total_pnl among everything that
    clears the bar) -- never more than one "best" shown at a time, and
    never a losing/weak strategy dressed up as one."""
    stats = storage.list_paper_strategy_stats()
    live_names = {m["id"]: m["name"] for m in lib.list_all()}
    for s in stats:
        if s["strategy_id"] in live_names:
            s["strategy_name"] = live_names[s["strategy_id"]]  # prefer the current name over a stale one

    qualifiers = [
        s for s in stats
        if s["closed_trades"] >= MIN_CLOSED_TRADES
        and s["total_pnl"] > 0
        and s["win_rate"] >= MIN_WIN_RATE
    ]
    best = max(qualifiers, key=lambda s: s["total_pnl"]) if qualifiers else None

    scan_id = storage.save_strategy_lab_scan(
        scanned_at=_now_iso(),
        strategies_checked=len(stats),
        qualifying_strategy_id=best["strategy_id"] if best else None,
        qualifying_strategy_name=best["strategy_name"] if best else None,
        qualifying_win_rate=best["win_rate"] if best else None,
        qualifying_pnl=best["total_pnl"] if best else None,
        qualifying_trade_count=best["closed_trades"] if best else None,
    )
    return storage.get_latest_strategy_lab_scan() or {"id": scan_id}


def maybe_run_strategy_lab_scan():
    """Called periodically by the scheduler thread -- only actually scans
    if SCAN_INTERVAL_DAYS+ have passed since the last scan (or none exists
    yet). Safe to call as often as convenient."""
    if not feature_toggles.is_enabled("strategy_lab_enabled"):
        return None
    latest = storage.get_latest_strategy_lab_scan()
    if latest:
        last_dt = datetime.fromisoformat(latest["scanned_at"])
        if datetime.now(timezone.utc) - last_dt < timedelta(days=SCAN_INTERVAL_DAYS):
            return None
    return scan_for_profitable_strategy()


def start_strategy_lab_scheduler_thread():
    """Runs once at server startup; checks every few hours whether a new
    scan is due -- same shape as paper_trading.weekly_report's scheduler
    thread."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                result = maybe_run_strategy_lab_scan()
                if result:
                    log("[strategy-lab] ran a new scan")
            except Exception as e:
                log(f"[strategy-lab] scan failed: {e!r}")
            time.sleep(6 * 3600)  # check every 6 hours; the interval gate above prevents over-scanning

    threading.Thread(target=_loop, daemon=True).start()


class ApprovalError(Exception):
    pass


def approve_candidate(scan_id, strategy_id):
    """The ONLY code path that lets a Strategy Lab finding reach live
    Paper Trading / Telegram -- runs exclusively from an explicit CEO
    one-click approval (POST /api/strategy-lab/approve), never from the
    scheduler. Rejects approving anything other than the exact strategy
    that scan actually found qualifying, so a stale UI can't approve the
    wrong (or no-longer-qualifying) strategy by accident.

    Approving does two real, visible things: enables the strategy in
    Paper Trading (paper_strategy_config.enabled) and flags it for manual
    Telegram alerting (paper_strategy_overrides.manual_alert) -- the same
    two switches the CEO could already flip by hand elsewhere, just
    pre-filled from this scan's finding rather than typed again."""
    scan = storage.get_latest_strategy_lab_scan()
    if not scan or scan["id"] != scan_id:
        raise ApprovalError("This isn't the latest scan anymore -- refresh and try again.")
    if not scan["qualifying_strategy_id"]:
        raise ApprovalError("This scan has no qualifying strategy to approve.")
    if scan["qualifying_strategy_id"] != strategy_id:
        raise ApprovalError("That strategy isn't the one this scan found qualifying.")
    if scan["approved"]:
        raise ApprovalError("Already approved.")

    now = _now_iso()
    existing = storage.list_paper_strategy_configs().get(strategy_id, {})
    storage.save_paper_strategy_config(
        strategy_id, enabled=True,
        priority=existing.get("priority") if existing.get("priority") is not None else 5,
        supported_coins=existing.get("supported_coins"),
        supported_market_types=existing.get("supported_market_types"),
        now_iso=now,
    )
    override = storage.get_paper_strategy_override(strategy_id)
    storage.save_paper_strategy_override(strategy_id, manual_alert=True, note=override.get("note"), now_iso=now)
    storage.approve_strategy_lab_scan(scan_id, now)
    return storage.get_latest_strategy_lab_scan()

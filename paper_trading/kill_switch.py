"""Kill-Switch: one action that halts ALL trading immediately, system-wide.

Distinct from the existing "Start/Stop Engine" button
(sindhu_web/api/paper_trading.py) and the existing Master Pause
(sindhu_web/api/feature_control.py) in three ways:

1. Stop Engine only stops the Paper Trading tick loop -- it does not touch
   any position already open, and a fresh "Start Engine" click immediately
   undoes it. Master Pause explicitly does NOT stop trading at all (its own
   docstring: "Paper Trading itself keeps running").
2. The kill switch is enforced at the actual trade-approval gate
   (risk_manager.evaluate), not just the tick loop -- so even if the engine
   loop were somehow still ticking, no new position can open while it is
   active. It also silences real Telegram sends (telegram_bot.send_signal_for_position)
   so no actionable signal goes out either.
3. It persists across a restart and REFUSES to let the engine start again
   (PaperTradingEngine.start honors this) until a human explicitly
   deactivates it -- a plain restart or a stray "Start Engine" click cannot
   quietly undo an emergency stop.

Never touches strategy configs, backtests, or the Evolution Engine --
those are out of scope for a live-trading emergency stop.
"""

from datetime import datetime, timezone

from data_engine import storage


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def is_active():
    return storage.get_kill_switch_state()["active"]


def status():
    return storage.get_kill_switch_state()


def activate(reason=None, actor="CEO", close_positions=True):
    """Halts all trading right now. Returns a summary dict including how
    many open positions were force-closed (if close_positions=True)."""
    from paper_trading import engine as engine_mod

    reason = reason or "manual emergency stop"
    storage.activate_kill_switch(reason, actor, close_positions, _now_iso())

    engine_running_before = engine_mod.engine.is_running()
    engine_mod.engine.stop()

    closed = []
    if close_positions:
        closed = _close_all_open_positions(actor)

    from sindhu_web import sync
    sync.notify(
        "kill_switch", "activated",
        f"KILL SWITCH ACTIVATED by {actor}: {reason}"
        + (f" -- {len(closed)} open position(s) force-closed" if close_positions else " -- open positions left untouched"),
    )
    return {
        "ok": True, "active": True, "reason": reason,
        "engine_was_running": engine_running_before,
        "positions_closed": closed,
    }


def deactivate(actor="CEO"):
    """Clears the kill switch. Deliberately does NOT restart the engine --
    a human must explicitly press Start Engine again, so resuming live
    trading after an emergency stop is always a separate, deliberate act."""
    if not is_active():
        return {"ok": False, "error": "kill switch is not active"}
    storage.deactivate_kill_switch(actor, _now_iso())

    from sindhu_web import sync
    sync.notify("kill_switch", "deactivated",
                f"Kill switch deactivated by {actor}. Trading stays OFF until Start Engine is pressed again.")
    return {"ok": True, "active": False}


def _close_all_open_positions(actor):
    from data_engine import config as base_config
    from data_engine.exchanges.registry import get_exchange_client
    from paper_trading import position_manager

    quote_asset = base_config.load_or_seed("coins.json", base_config.DEFAULTS["coins.json"])["quote_asset"]

    closed = []
    open_positions = storage.get_open_paper_positions()
    by_exchange = {}
    for p in open_positions:
        by_exchange.setdefault(p["exchange"], []).append(p)

    for exchange, positions in by_exchange.items():
        try:
            client = get_exchange_client(exchange)
            tickers = client.get_tickers(quote_asset)
        except Exception:
            tickers = {}
        for p in positions:
            ticker = tickers.get(p["symbol"])
            price = ticker["price"] if ticker else p["entry_price"]
            result = position_manager.force_close(p["id"], price, reason="kill_switch")
            if result:
                closed.append({"position_id": p["id"], "symbol": p["symbol"], "exchange": exchange})
    return closed

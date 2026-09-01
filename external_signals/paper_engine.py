"""Phase 3 -- isolated (fake-money) paper trading engine for external
channel signals.

ISOLATION: every function here reads/writes ONLY external_positions /
external_channel_performance (via data_engine.storage's external_*
functions) -- never paper_positions, paper_account_state, or
paper_strategy_performance. This module does not import anything from
paper_trading/ except the one, explicitly-reused piece named in the task
(the emergency stop-loss fallback constant, imported directly from
backtest_engine.engine, the same place paper_trading/position_manager.py
itself imports it from -- not a second implementation).

AI is never called here. This module only ever does arithmetic and
storage reads/writes.
"""

import uuid
from datetime import datetime, timezone

from backtest_engine.engine import EMERGENCY_STOP_PCT
from data_engine import config as data_config, storage

STARTING_BALANCE = 1000.0
DEFAULT_RISK_PCT = 1.0  # % of this channel's own balance risked per position, entirely separate from the user's own risk settings


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _validate_stop_loss(direction, entry_price, stop_loss):
    """Same wrong-side re-check paper_trading.position_manager.open_position
    already applies -- a stop_loss on the wrong side of entry is worse
    than no stop_loss at all, so it's discarded (not trusted) here too."""
    if stop_loss is None:
        return None
    wrong_side = (direction == "long" and stop_loss >= entry_price) or (direction == "short" and stop_loss <= entry_price)
    return None if wrong_side else stop_loss


def _emergency_stop(direction, entry_price):
    """The exact fallback paper_trading/position_manager.py already uses
    when a real stop-loss can't be determined -- reused, not
    reimplemented, so an external position can never be left unprotected
    any differently than the user's own paper trades are."""
    return entry_price * (1 - EMERGENCY_STOP_PCT) if direction == "long" else entry_price * (1 + EMERGENCY_STOP_PCT)


def open_position_from_signal(signal):
    """signal: a dict shaped like storage.list_external_signals()'s
    output (must have is_signal=True). Fills the FIRST entry immediately
    at its stated price (the channel's signal price -- there is nothing
    "live" to wait for on the very first entry, same as any other trade
    signal); every additional (DCA) entry stays unfilled until
    check_price_updates() sees price genuinely reach it. Returns the new
    position id, or None if the signal has no usable entry."""
    entries = signal.get("entries") or []
    if not entries:
        return None
    direction = signal.get("direction")
    if direction not in ("long", "short"):
        return None

    first_price = entries[0]["price"]
    stop_loss = _validate_stop_loss(direction, first_price, signal.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _emergency_stop(direction, first_price)

    take_profit = [
        tp for tp in (signal.get("take_profit") or [])
        if (direction == "long" and tp > first_price) or (direction == "short" and tp < first_price)
    ]

    planned_entries = [
        {"price": e["price"], "size_pct": e["size_pct"], "filled": idx == 0,
         "filled_at": _now_iso() if idx == 0 else None}
        for idx, e in enumerate(entries)
    ]

    position_id = uuid.uuid4().hex[:16]
    now = _now_iso()
    storage.open_external_position(
        position_id, signal["channel_id"], signal["id"], signal["symbol"], direction,
        planned_entries, stop_loss, take_profit, now,
    )
    storage.update_external_position_entries(
        position_id, planned_entries, avg_entry_price=first_price,
        filled_size_pct=planned_entries[0]["size_pct"], status="open", opened_at=now,
    )
    return position_id


def _default_exchange():
    try:
        return data_config.DEFAULT_EXCHANGE
    except Exception:
        return "binance"


def _fetch_live_price(symbol, exchange=None):
    """Same real exchange-client price lookup
    paper_trading.telegram_bot._fetch_live_price already uses -- never a
    second implementation, never a simulated/estimated number."""
    try:
        from data_engine.exchanges.registry import get_exchange_client
        from data_engine import config as base_config
        client = get_exchange_client(exchange or _default_exchange())
        coins_cfg = base_config.load_or_seed("coins.json", base_config.DEFAULTS["coins.json"])
        tickers = client.get_tickers(coins_cfg["quote_asset"])
        ticker = tickers.get(symbol)
        return ticker["price"] if ticker else None
    except Exception:
        return None


def _weighted_avg(filled_entries):
    total_size = sum(e["size_pct"] for e in filled_entries)
    if total_size <= 0:
        return None
    return sum(e["price"] * e["size_pct"] for e in filled_entries) / total_size


def _dca_entry_reached(direction, entry_price, live_price):
    # A long DCA entry fills when price drops TO OR BELOW it (a better/
    # cheaper fill); a short DCA entry fills when price rises TO OR ABOVE it.
    if direction == "long":
        return live_price <= entry_price
    return live_price >= entry_price


def _exit_hit(direction, level, live_price, is_stop):
    if level is None:
        return False
    if direction == "long":
        return live_price <= level if is_stop else live_price >= level
    return live_price >= level if is_stop else live_price <= level


def check_price_updates(symbol=None):
    """The single live tick: for every open/pending external position
    (optionally scoped to one symbol, to avoid refetching a price already
    known), fills any DCA entries price has genuinely reached, and closes
    the position if its stop-loss or first take-profit target is hit.
    Never calls AI. Returns a list of {"position_id", "action"} for real
    verification evidence."""
    events = []
    positions = storage.list_external_positions(status="open") + storage.list_external_positions(status="pending")
    price_cache = {}
    for pos in positions:
        if symbol and pos["symbol"] != symbol:
            continue
        if pos["symbol"] not in price_cache:
            price_cache[pos["symbol"]] = _fetch_live_price(pos["symbol"])
        live_price = price_cache[pos["symbol"]]
        if live_price is None:
            continue

        entries = pos["entries"]
        changed = False
        for e in entries:
            if e["filled"]:
                continue
            if _dca_entry_reached(pos["direction"], e["price"], live_price):
                e["filled"] = True
                e["filled_at"] = _now_iso()
                changed = True

        filled = [e for e in entries if e["filled"]]
        if changed:
            avg = _weighted_avg(filled)
            filled_pct = sum(e["size_pct"] for e in filled)
            storage.update_external_position_entries(
                pos["id"], entries, avg_entry_price=avg, filled_size_pct=filled_pct,
                status=pos["status"], opened_at=None,
            )
            events.append({"position_id": pos["id"], "action": "dca_entry_filled"})
            pos["avg_entry_price"] = avg

        stop_hit = _exit_hit(pos["direction"], pos["stop_loss"], live_price, is_stop=True)
        target_hit = pos["take_profit"] and _exit_hit(pos["direction"], pos["take_profit"][0], live_price, is_stop=False)
        if stop_hit or target_hit:
            _close_position(pos, live_price, "stop_loss" if stop_hit else "take_profit")
            events.append({"position_id": pos["id"], "action": f"closed_{'stop_loss' if stop_hit else 'take_profit'}"})
    return events


def _close_position(pos, exit_price, exit_reason):
    avg_entry = pos.get("avg_entry_price") or pos["entries"][0]["price"]
    direction_mult = 1 if pos["direction"] == "long" else -1
    pnl_pct = direction_mult * (exit_price - avg_entry) / avg_entry * 100.0

    # R-multiple: how many multiples of the stop-loss distance this trade
    # actually made/lost -- the same "risk-normalized" concept used
    # elsewhere in SINDHU (telegram_analytics.hypothetical_pnl), computed
    # independently here since this is a fully separate book. risk_amount
    # is a fixed % of THIS channel's own current balance (never the
    # user's own paper trading balance/settings).
    stop_distance_pct = abs((pos["stop_loss"] - avg_entry) / avg_entry * 100.0) if pos["stop_loss"] else None
    r_multiple = (pnl_pct / stop_distance_pct) if stop_distance_pct else None

    perf = storage.get_external_channel_performance(pos["channel_id"])
    risk_amount = perf["balance"] * (DEFAULT_RISK_PCT / 100.0)
    pnl = risk_amount * r_multiple if r_multiple is not None else perf["balance"] * (pnl_pct / 100.0)

    now = _now_iso()
    storage.close_external_position(pos["id"], exit_price, pnl, pnl_pct, exit_reason, now)

    new_balance = perf["balance"] + pnl
    storage.update_external_channel_performance(pos["channel_id"], new_balance, True, pnl, r_multiple, now)


def close_position_manually(position_id, exit_price, exit_reason="manual_close"):
    """For 'close now' channel updates (Phase 3, item 4) once reliably
    linked to their original signal -- same close path as an automatic
    stop/target hit, just an explicit exit_price/reason instead of a
    live-price trigger."""
    pos = storage.get_external_position(position_id)
    if not pos or pos["status"] != "open":
        return False
    _close_position(pos, exit_price, exit_reason)
    return True


def move_stop_loss(position_id, new_stop_loss):
    """For 'move SL to breakeven' updates (Phase 3, item 4)."""
    pos = storage.get_external_position(position_id)
    if not pos or pos["status"] != "open":
        return False
    validated = _validate_stop_loss(pos["direction"], pos["avg_entry_price"] or pos["entries"][0]["price"], new_stop_loss)
    if validated is None:
        return False
    storage.update_external_position_stop_loss(position_id, validated)
    return True

"""Reflection: after every closed trade, save why it was entered, why it
exited, what went right/wrong, and the market context -- deterministic,
templated from the facts of the trade (no AI/no guessing), exactly like
every other "explain the decision" feature in this project.
"""


def build(position, exit_price, pnl, pnl_pct, exit_reason):
    why_enter = position.get("entry_reason") or "signal"
    why_exit = {
        "stop_loss": "Stop-loss was hit.",
        "take_profit": "Take-profit target was reached.",
        "exit_signal": "Strategy exit condition triggered.",
    }.get(exit_reason, exit_reason or "unknown")

    mistakes, success = [], []
    duration_ms = (position.get("exit_time") or 0) - position["entry_time"]
    duration_min = duration_ms / 60000 if duration_ms else 0

    if exit_reason == "stop_loss" and duration_min < 30:
        mistakes.append("Stopped out quickly (<30min) -- possible early/low-confidence entry timing.")
    if exit_reason == "stop_loss" and pnl_pct < -3:
        mistakes.append("Loss exceeded typical risk band -- review stop-loss distance for this setup.")
    if exit_reason == "take_profit":
        success.append("Target reached as planned -- entry timing and trade management were sound.")
    if pnl > 0 and duration_min > 60:
        success.append("Trade required patience and worked out -- good conviction holding through noise.")
    if not mistakes and not success:
        (success if pnl >= 0 else mistakes).append(
            "Closed on strategy/lesson exit logic with " + ("a gain." if pnl >= 0 else "a loss.")
        )

    return {
        "why_enter": why_enter,
        "why_exit": why_exit,
        "mistakes": mistakes,
        "success": success,
        "market_context": position.get("market_snapshot", {}),
        "duration_minutes": round(duration_min, 1),
        "pnl": round(pnl, 4),
        "pnl_pct": round(pnl_pct, 4),
    }


def build_no_trade(reason, market_snapshot):
    """The No-Trade Journal's per-rejection "why not" note -- same idea as
    a closed-trade reflection, just for a signal that never became a
    trade."""
    return {"why_no_trade": reason, "market_context": market_snapshot}

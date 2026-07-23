"""Phase 2 (BACKTESTING_MASTER_SPEC.md Requirement 12, Backtest Validation
Engine): for every trade a backtest produces, independently re-derive
entry/exit/SL/TP/direction/PnL/RR/win-loss from the raw candle data and the
trade's own recorded fields, and report the exact reason for any mismatch
-- never silently accept a bad trade record. Pure verification: never
mutates a trade, never re-runs the strategy, only checks arithmetic and
consistency that must hold regardless of which strategy produced the trade.
"""

import pandas as pd

# Real-world execution never lands EXACTLY on a computed level (commission/
# slippage/spread all nudge the fill price a little) -- this tolerance is
# generous enough to absorb normal execution friction while still catching
# a genuinely wrong-side-of-entry SL/TP or a fill price nowhere near the
# bar it claims to belong to.
_PRICE_TOLERANCE_PCT = 0.5  # 0.5% of price
_RR_TOLERANCE_PCT = 25.0    # RR-target types (structure/level SL) legitimately vary more


def _bar_at(df, ms):
    """Nearest bar to a stored millisecond timestamp. Trade timestamps are
    always an exact bar's timestamp (int(ts.value // 1_000_000) in
    engine.py), so "nearest" only ever needs to handle floating point/
    timezone round-trip noise, never a genuine ambiguity."""
    if ms is None or df is None or len(df) == 0:
        return None
    ts = pd.to_datetime(ms, unit="ms", utc=True)
    idx = df.index.get_indexer([ts], method="nearest")[0]
    if idx < 0:
        return None
    return df.iloc[idx]


def _pct_diff(a, b):
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b) * 100.0


def validate_trade(trade, df=None):
    """Returns a list of issue strings for ONE trade -- empty means every
    check passed. `df` (the merged OHLCV dataframe the backtest actually
    ran against), if given, additionally checks fill prices against the
    real candle they claim to belong to; without it, only the trade
    record's own internal arithmetic is checked (still catches direction/
    PnL/RR sign errors)."""
    issues = []
    side = trade.get("side")
    entry_price = trade.get("entry_price")
    exit_price = trade.get("exit_price")
    size = trade.get("size")
    sl = trade.get("stop_loss")
    tp = trade.get("take_profit")
    pnl = trade.get("pnl")
    gross_pnl = trade.get("gross_pnl")
    exit_reason = trade.get("exit_reason")

    # ---- Direction ----
    if side not in ("long", "short"):
        issues.append(f"invalid trade direction: {side!r}")

    # ---- Position size ----
    if size is None or size <= 0:
        issues.append(f"impossible position size: {size!r} (must be > 0)")

    # ---- Stop-loss / take-profit are on the CORRECT side of entry ----
    if entry_price is not None and side in ("long", "short"):
        if sl is not None:
            wrong_side = (side == "long" and sl >= entry_price) or (side == "short" and sl <= entry_price)
            if wrong_side:
                issues.append(
                    f"stop_loss ({sl}) is on the WRONG side of entry_price ({entry_price}) "
                    f"for a {side} trade -- a real stop must sit on the losing side"
                )
        if tp is not None:
            wrong_side = (side == "long" and tp <= entry_price) or (side == "short" and tp >= entry_price)
            if wrong_side:
                issues.append(
                    f"take_profit ({tp}) is on the WRONG side of entry_price ({entry_price}) "
                    f"for a {side} trade -- a real target must sit on the winning side"
                )

    # ---- Exit price matches SL/TP when that's the recorded reason ----
    if exit_reason == "stop_loss" and sl is not None and exit_price is not None:
        diff = _pct_diff(exit_price, sl)
        if diff is not None and diff > _PRICE_TOLERANCE_PCT:
            issues.append(
                f"exit_reason='stop_loss' but exit_price ({exit_price}) is {diff:.2f}% away "
                f"from the recorded stop_loss ({sl}) -- expected them to closely match"
            )
    if exit_reason == "take_profit" and tp is not None and exit_price is not None:
        diff = _pct_diff(exit_price, tp)
        if diff is not None and diff > _PRICE_TOLERANCE_PCT:
            issues.append(
                f"exit_reason='take_profit' but exit_price ({exit_price}) is {diff:.2f}% away "
                f"from the recorded take_profit ({tp}) -- expected them to closely match"
            )

    # ---- Win/Loss consistency with exit_reason (the exact bug class that
    # motivated this module: a structure SL on the wrong side previously
    # mislabeled real wins as "stop_loss" losses -- checked here against
    # GROSS pnl, since commission alone can flip a razor-thin NET result) ----
    if exit_reason == "stop_loss" and gross_pnl is not None and gross_pnl > 0:
        issues.append(
            f"exit_reason='stop_loss' but gross_pnl is positive ({gross_pnl:.6f}) -- "
            f"a real stop-loss exit can never be a gross win"
        )
    if exit_reason == "take_profit" and gross_pnl is not None and gross_pnl < 0:
        issues.append(
            f"exit_reason='take_profit' but gross_pnl is negative ({gross_pnl:.6f}) -- "
            f"a real take-profit exit can never be a gross loss"
        )

    # ---- PnL sign must match entry->exit price movement in the trade's
    # own direction (independently re-derived, not trusted from the
    # stored field) ----
    if entry_price is not None and exit_price is not None and size and side in ("long", "short"):
        expected_gross = (exit_price - entry_price) * size if side == "long" else (entry_price - exit_price) * size
        if gross_pnl is not None:
            # Same-sign check (not exact equality -- gross_pnl in the
            # trade record is computed off the SLIPPED/SPREAD fill price,
            # not the bare entry_price/exit_price fields, so a small
            # magnitude difference is expected; the SIGN must never
            # disagree).
            if (expected_gross > 0) != (gross_pnl > 0) and abs(expected_gross) > 1e-9 and abs(gross_pnl) > 1e-9:
                issues.append(
                    f"gross_pnl sign ({gross_pnl:.6f}) disagrees with entry/exit price movement "
                    f"for a {side} trade (entry={entry_price}, exit={exit_price}) -- "
                    f"expected sign matching {expected_gross:.6f}"
                )
        if pnl is not None and gross_pnl is not None:
            commission = trade.get("commission_cost") or 0.0
            expected_net = gross_pnl - commission
            if abs(pnl - expected_net) > max(abs(expected_net) * 0.01, 1e-6):
                issues.append(
                    f"pnl ({pnl:.6f}) does not equal gross_pnl - commission_cost "
                    f"({expected_net:.6f}) -- possible double-counted or dropped cost"
                )

    # ---- RR sanity (only meaningful when both a real risk and reward
    # distance were recorded) ----
    risk_amount = trade.get("risk_amount")
    reward_amount = trade.get("reward_amount")
    if risk_amount and reward_amount and risk_amount > 0:
        rr = reward_amount / risk_amount
        if rr <= 0 or rr > 1000:
            issues.append(f"implausible risk:reward ratio: {rr:.2f}")

    # ---- Cross-check fill prices against the ACTUAL candle they claim to
    # belong to (only when the real dataframe is supplied) ----
    if df is not None:
        entry_bar = _bar_at(df, trade.get("entry_time"))
        if entry_bar is not None and entry_price is not None:
            lo, hi = float(entry_bar["low"]), float(entry_bar["high"])
            tol = (hi - lo) * 0.02 + hi * (_PRICE_TOLERANCE_PCT / 100.0)
            if not (lo - tol <= entry_price <= hi + tol):
                issues.append(
                    f"entry_price ({entry_price}) is outside the entry bar's actual "
                    f"high/low range ({lo}-{hi}), beyond execution-friction tolerance"
                )
        exit_bar = _bar_at(df, trade.get("exit_time"))
        if exit_bar is not None and exit_price is not None:
            lo, hi = float(exit_bar["low"]), float(exit_bar["high"])
            tol = (hi - lo) * 0.02 + hi * (_PRICE_TOLERANCE_PCT / 100.0)
            if not (lo - tol <= exit_price <= hi + tol):
                issues.append(
                    f"exit_price ({exit_price}) is outside the exit bar's actual "
                    f"high/low range ({lo}-{hi}), beyond execution-friction tolerance"
                )

    return issues


def validate_all_trades(trades, df=None):
    """Runs validate_trade() over every trade in a batch, plus one
    batch-level check (no exact duplicates), and returns
    {"pass": bool, "trade_count": int, "issues_by_trade": {trade_num: [..]},
    "duplicate_trades": [...]}."""
    issues_by_trade = {}
    for t in trades:
        issues = validate_trade(t, df)
        if issues:
            issues_by_trade[t.get("trade_num")] = issues

    seen = {}
    duplicates = []
    for t in trades:
        key = (t.get("entry_time"), t.get("exit_time"), t.get("entry_price"),
               t.get("exit_price"), t.get("size"), t.get("side"))
        if key in seen:
            duplicates.append({"trade_num": t.get("trade_num"), "duplicate_of": seen[key]})
        else:
            seen[key] = t.get("trade_num")

    return {
        "pass": not issues_by_trade and not duplicates,
        "trade_count": len(trades),
        "issues_by_trade": issues_by_trade,
        "duplicate_trades": duplicates,
    }

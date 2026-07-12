"""Bar-by-bar backtest simulation. Vectorized indicator prep (via
strategy.prepare) keeps this fast even over a full year of 1m data; the
per-bar loop only runs the strategy's decision function and simple
arithmetic, so a 525k-row 1m backtest still finishes in a couple seconds.
"""


def _ts_to_ms(ts):
    return int(ts.value // 1_000_000)


def _apply_slippage(price, side, is_exit, slippage_pct):
    """Slippage always works against the trader: worse fill on both entry
    and exit, in whichever direction that means for the given side."""
    if slippage_pct == 0:
        return price
    worse_is_higher = (side == "long" and not is_exit) or (side == "short" and is_exit)
    return price * (1 + slippage_pct) if worse_is_higher else price * (1 - slippage_pct)


def _position_size(balance, entry_price, stop_loss, risk_pct, position_size_pct):
    """Risk-based sizing when the strategy gives a stop-loss (classic
    risk-per-trade position sizing); otherwise a fixed fraction of equity.
    Capped at 1x balance -- this engine doesn't model margin/leverage."""
    if stop_loss is not None and stop_loss != entry_price:
        stop_distance = abs(entry_price - stop_loss)
        size = (balance * risk_pct) / stop_distance
    else:
        size = (balance * position_size_pct) / entry_price
    return max(min(size, balance / entry_price), 0.0)


def _risk_amount(position):
    if position["stop_loss"] is None:
        return None
    return abs(position["entry_price"] - position["stop_loss"]) * position["size"]


def _reward_amount(position):
    if position["take_profit"] is None:
        return None
    return abs(position["take_profit"] - position["entry_price"]) * position["size"]


def _check_forced_exit(position, high, low):
    side = position["side"]
    sl, tp = position["stop_loss"], position["take_profit"]
    if side == "long":
        if sl is not None and low <= sl:
            return sl, "stop_loss"
        if tp is not None and high >= tp:
            return tp, "take_profit"
    else:
        if sl is not None and high >= sl:
            return sl, "stop_loss"
        if tp is not None and low <= tp:
            return tp, "take_profit"
    return None, None


def run_backtest(df, strategy, settings, control=None, on_trade=None, knowledge_engine=None, bar_progress_cb=None):
    """Returns (trades: list[dict], equity_curve: list[float], final_balance: float).

    knowledge_engine, if given, is consulted before every prospective entry
    purely for tracking/logging (Phase 4) -- it never blocks or modifies a
    signal the strategy has already produced. Optional and defaults to None
    so existing callers are unaffected -- when None, behavior is identical
    to before Phase 4.

    bar_progress_cb(bar_index_1based, total_bars, trades_so_far), if given,
    is invoked periodically (about 50 times over the run, plus once on the
    final bar) so a caller can show live within-coin progress and a live
    trade counter during simulation (Phase 6). Optional, no effect on the
    simulation itself."""
    df = strategy.prepare(df)

    balance = float(settings["initial_balance"])
    commission_pct = settings.get("commission_pct", 0.0) / 100.0
    slippage_pct = settings.get("slippage_pct", 0.0) / 100.0
    risk_pct = settings.get("risk_pct", 1.0) / 100.0
    position_size_pct = settings.get("position_size_pct", 10.0) / 100.0

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    times = df.index

    position = None
    trades = []
    equity_curve = []
    trade_num = 0
    n = len(df)
    progress_interval = max(1, n // 50)

    for i in range(n):
        if control is not None and control.should_stop():
            break

        price = closes[i]
        high = highs[i]
        low = lows[i]

        signal = strategy.on_bar(df, i, position)

        if position is not None:
            exit_price, exit_reason = _check_forced_exit(position, high, low)
            if exit_price is None and signal is not None and signal.action == "exit":
                exit_price, exit_reason = price, (signal.reason or "signal")

            if exit_price is not None:
                fill_price = _apply_slippage(exit_price, position["side"], True, slippage_pct)
                if position["side"] == "long":
                    gross_pnl = (fill_price - position["entry_price"]) * position["size"]
                else:
                    gross_pnl = (position["entry_price"] - fill_price) * position["size"]
                commission_cost = (position["entry_price"] + fill_price) * position["size"] * commission_pct
                net_pnl = gross_pnl - commission_cost
                balance += net_pnl

                trade_num += 1
                trade = {
                    "trade_num": trade_num,
                    "side": position["side"],
                    "entry_time": position["entry_time"],
                    "entry_price": position["entry_price"],
                    "exit_time": _ts_to_ms(times[i]),
                    "exit_price": fill_price,
                    "size": position["size"],
                    "pnl": net_pnl,
                    "pnl_pct": (net_pnl / (position["entry_price"] * position["size"])) * 100
                    if position["entry_price"] * position["size"] else 0.0,
                    "exit_reason": exit_reason,
                    "stop_loss": position["stop_loss"],
                    "take_profit": position["take_profit"],
                    "risk_amount": _risk_amount(position),
                    "reward_amount": _reward_amount(position),
                    "entry_reason": position["entry_reason"],
                }
                trades.append(trade)
                if on_trade:
                    on_trade(trade)
                position = None

        elif signal is not None and signal.action in ("buy", "sell"):
            side = "long" if signal.action == "buy" else "short"

            if knowledge_engine is not None:
                # Lessons are tracked/logged (check() still records each
                # lesson's approved/rejected outcome for Knowledge Score and
                # Reports stats) but never veto a Strategy's own validated
                # signal -- Strategies and Lessons are independent.
                direction = "bullish" if side == "long" else "bearish"
                knowledge_engine.check(df, i, direction)

            if signal is not None:
                fill_price = _apply_slippage(price, side, False, slippage_pct)
                size = _position_size(balance, fill_price, signal.stop_loss, risk_pct, position_size_pct)
                if size > 0:
                    position = {
                        "side": side,
                        "entry_price": fill_price,
                        "entry_time": _ts_to_ms(times[i]),
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "size": size,
                        "entry_reason": signal.reason or "signal",
                    }

        if position is None:
            equity = balance
        else:
            unrealized = (
                (price - position["entry_price"]) * position["size"]
                if position["side"] == "long"
                else (position["entry_price"] - price) * position["size"]
            )
            equity = balance + unrealized
        equity_curve.append(equity)

        if bar_progress_cb and (i % progress_interval == 0 or i == n - 1):
            bar_progress_cb(i + 1, n, len(trades))

    if position is not None and n > 0:
        fill_price = _apply_slippage(closes[-1], position["side"], True, slippage_pct)
        if position["side"] == "long":
            gross_pnl = (fill_price - position["entry_price"]) * position["size"]
        else:
            gross_pnl = (position["entry_price"] - fill_price) * position["size"]
        commission_cost = (position["entry_price"] + fill_price) * position["size"] * commission_pct
        net_pnl = gross_pnl - commission_cost
        balance += net_pnl
        trade_num += 1
        trade = {
            "trade_num": trade_num,
            "side": position["side"],
            "entry_time": position["entry_time"],
            "entry_price": position["entry_price"],
            "exit_time": _ts_to_ms(times[-1]),
            "exit_price": fill_price,
            "size": position["size"],
            "pnl": net_pnl,
            "pnl_pct": (net_pnl / (position["entry_price"] * position["size"])) * 100
            if position["entry_price"] * position["size"] else 0.0,
            "exit_reason": "end_of_data",
            "stop_loss": position["stop_loss"],
            "take_profit": position["take_profit"],
            "risk_amount": _risk_amount(position),
            "reward_amount": _reward_amount(position),
            "entry_reason": position["entry_reason"],
        }
        trades.append(trade)
        if on_trade:
            on_trade(trade)
        if equity_curve:
            equity_curve[-1] = balance

    return trades, equity_curve, balance

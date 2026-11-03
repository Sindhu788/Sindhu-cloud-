"""Bar-by-bar backtest simulation. Vectorized indicator prep (via
strategy.prepare) keeps this fast even over a full year of 1m data; the
per-bar loop only runs the strategy's decision function and simple
arithmetic, so a 525k-row 1m backtest still finishes in a couple seconds.

Trade Execution Engine (Phase 1, BACKTESTING_MASTER_SPEC.md Requirement
10): a signal doesn't always fill immediately at the signal bar's close --
`entry_type` (on the strategy's config, defaulting to "market") controls
how. Anything other than "market"/"current_candle_close" creates a
PENDING order that this loop checks against every subsequent bar's
high/low until it fills (limit/stop/signal-candle-high/signal-candle-low)
or unconditionally at the very next bar's open (next_candle_open) -- never
silently substituted for a different fill type.
"""

# Requirement 20 emergency fallback: when a structure-based stop_loss is
# invalidated post-fill (see _open_position below), the trade gets this
# fixed-percentage stop from the real fill price instead of NO stop at all.
# The invalidated zone was already validated against the correct side of
# the raw SIGNAL price at computation time (_compute_stop_loss), so it only
# flips sides here because slippage/spread nudged the real fill a hair past
# it -- meaning the zone, and therefore a safe protective distance, is
# always close by. 1% is tight enough to matter for the scalping-style
# strategies this most affects, without being so tight it gets brushed by
# ordinary noise on a bar that would have been fine under the original zone.
EMERGENCY_STOP_PCT = 0.01


def _ts_to_ms(ts):
    return int(ts.value // 1_000_000)


def _apply_slippage(price, side, is_exit, slippage_pct):
    """Slippage always works against the trader: worse fill on both entry
    and exit, in whichever direction that means for the given side."""
    if slippage_pct == 0:
        return price
    worse_is_higher = (side == "long" and not is_exit) or (side == "short" and is_exit)
    return price * (1 + slippage_pct) if worse_is_higher else price * (1 - slippage_pct)


def _apply_spread(price, side, is_exit, spread_pct):
    """Same directional logic as slippage (always against the trader), but
    a SEPARATE, independently-configurable cost -- spread and slippage are
    different real-world frictions (a market's bid/ask gap vs. execution
    drift) and Requirement 11 asks for both to be individually verifiable,
    so they're applied and reported as two distinct costs rather than
    folded into one number."""
    if spread_pct == 0:
        return price
    worse_is_higher = (side == "long" and not is_exit) or (side == "short" and is_exit)
    return price * (1 + spread_pct) if worse_is_higher else price * (1 - spread_pct)


def _position_size(risk_base, available_balance, entry_price, stop_loss, risk_pct, position_size_pct, leverage=1.0):
    """Risk-based sizing when the strategy gives a stop-loss (classic
    risk-per-trade position sizing); otherwise a fixed fraction of equity.

    `risk_base` and `available_balance` are deliberately separate:
    - `risk_base` is what the risk % is calculated against. A backtest
      passes a FIXED value (initial capital) so thousands of trades can't
      compound the position size into runaway numbers; live/paper trading
      passes the real current (compounding) balance, which is correct for
      an actual account.
    - `available_balance` is always the real current balance, regardless of
      `risk_base` -- it caps how much can actually be bought (can't risk
      money that isn't there) and returns 0 once the account is wiped out,
      exactly like a real broker would stop letting you open new positions
      at (or past) zero equity.

    `leverage` (Requirement 11, Risk Engine) raises that balance cap: with
    leverage=1 (the default, and every strategy's behavior before this
    field existed) the cap is exactly `available_balance / entry_price` as
    before. leverage>1 allows controlling a larger notional position with
    the same account equity as margin -- the cap becomes
    `available_balance * leverage / entry_price`. Never lets size go
    negative or infinite regardless of input."""
    if available_balance <= 0:
        return 0.0
    if stop_loss is not None and stop_loss != entry_price:
        stop_distance = abs(entry_price - stop_loss)
        size = (risk_base * risk_pct) / stop_distance
    else:
        size = (risk_base * position_size_pct) / entry_price
    leveraged_cap = (available_balance * max(leverage, 1.0)) / entry_price
    return max(min(size, leveraged_cap), 0.0)


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


def _check_partial_take_profit(position, ptp_config, high, low):
    """Requirement 10 (Partial Take Profit). Fires at most once per
    position (guarded by position["partial_tp_done"]) -- the trigger price
    is entry +/- trigger_rr multiples of the ORIGINAL risk (position["
    _original_risk_distance"], captured at entry so a later breakeven/
    trailing-stop move can't silently change what "1R" means). Returns the
    exact trigger price if hit this bar, else None. Requires a real
    stop-loss (the risk distance it's measured against) -- silently never
    fires without one, exactly like validator.py already requires for this
    feature."""
    if ptp_config is None or position.get("partial_tp_done"):
        return None
    risk_distance = position.get("_original_risk_distance")
    if not risk_distance:
        return None
    trigger_rr = ptp_config.get("trigger_rr")
    if trigger_rr is None:
        return None
    if position["side"] == "long":
        trigger_price = position["entry_price"] + trigger_rr * risk_distance
        if high >= trigger_price:
            return trigger_price
    else:
        trigger_price = position["entry_price"] - trigger_rr * risk_distance
        if low <= trigger_price:
            return trigger_price
    return None


def _update_trailing_stop(position, trailing_config, price, high, low, current_atr=None,
                           current_structure_support=None, current_structure_resistance=None):
    """Requirement 10 (Trailing Stop). Tracks the best price seen since
    entry (position["best_price"]) and, once it's moved far enough, tightens
    stop_loss toward it -- NEVER loosens an existing stop, and never moves
    it against the trade. "atr_multiple" needs the CURRENT bar's ATR value
    (passed in by the caller, never read off the shared strategy config --
    that config object can be reused across symbols/runs, so per-bar state
    must never be mutated onto it); with no ATR available on this bar it
    just updates best_price and leaves the stop untouched rather than
    inventing a distance.

    "structure" (New Batch 3, Strategy 1 -- HTF Trend Trendline Breakout):
    a GENERAL, reusable third trailing-stop type -- gap #12 in
    ENGINE_GAP_TRACKER.md ("no structural trailing stop-loss... would need a
    third trailing_stop.type") -- for a strategy that wants to "ride the
    trend" by moving the stop to the most recently confirmed swing point in
    the trade's favor, instead of a fixed %/ATR distance. `current_structure_
    support`/`current_structure_resistance` are this bar's already-computed
    entry_support/entry_resistance values (the SAME forward-filled swing-low/
    swing-high series the existing "support"/"resistance" concept already
    produces -- see concepts.support_resistance -- passed in by the caller
    exactly like current_atr above, never read off config), so any strategy
    that already declares "support"/"resistance" gets this trailing mode for
    free with zero new columns. Never loosens, never moves against the
    trade, and never trails the stop past the current price (a confirmed
    swing point can occasionally sit on the wrong side of a fast intrabar
    move; the price guard keeps the stop a real, fillable level)."""
    if trailing_config is None:
        return
    if position["side"] == "long":
        position["best_price"] = max(position.get("best_price", price), high)
        best = position["best_price"]
    else:
        position["best_price"] = min(position.get("best_price", price), low)
        best = position["best_price"]

    ts_type = trailing_config.get("type")

    if ts_type == "structure":
        if position["side"] == "long":
            level = current_structure_support
            if level is not None and level == level and level < price:  # NaN + price-side guard
                if position["stop_loss"] is None or level > position["stop_loss"]:
                    position["stop_loss"] = level
        else:
            level = current_structure_resistance
            if level is not None and level == level and level > price:
                if position["stop_loss"] is None or level < position["stop_loss"]:
                    position["stop_loss"] = level
        return

    value = trailing_config.get("value")
    if value is None:
        return

    if ts_type == "pct":
        distance = best * (value / 100.0)
    elif ts_type == "atr_multiple":
        if current_atr is None:
            return
        distance = value * current_atr
    else:
        return
    if distance <= 0:
        return

    if position["side"] == "long":
        new_stop = best - distance
        if position["stop_loss"] is None or new_stop > position["stop_loss"]:
            position["stop_loss"] = new_stop
    else:
        new_stop = best + distance
        if position["stop_loss"] is None or new_stop < position["stop_loss"]:
            position["stop_loss"] = new_stop


def _pending_trigger_price(pending, price):
    """Resolves the price a limit/stop/signal-candle-high/low order is
    waiting for. signal_candle_high/low were already resolved to an exact
    price at creation time (the signal bar's own high/low) -- only limit/
    stop derive it from an offset percent applied to the signal price."""
    if pending["order_type"] in ("signal_candle_high", "signal_candle_low"):
        return pending["trigger_price"]
    offset = pending.get("offset_pct") or 0.0
    offset = offset / 100.0
    side = pending["side"]
    order_type = pending["order_type"]
    if order_type == "limit":
        # A pullback in the trade's favor: below current price for a long,
        # above it for a short.
        return price * (1 - offset) if side == "long" else price * (1 + offset)
    else:  # "stop" -- a breakout in the trade's direction
        return price * (1 + offset) if side == "long" else price * (1 - offset)


def _check_pending_fill(pending, high, low, open_price, bar_is_next_bar):
    """Returns the fill price if `pending` should fill on THIS bar, else
    None. next_candle_open fills unconditionally on the bar immediately
    after the one the signal fired on, at that bar's open -- every other
    type only fills once price actually trades through its trigger level,
    checked against this bar's real high/low (never assumed)."""
    order_type = pending["order_type"]
    if order_type == "next_candle_open":
        return open_price if bar_is_next_bar else None

    trigger = pending["trigger_price"]
    side = pending["side"]
    if order_type == "limit":
        # Fills when price comes back TO the pullback level.
        return trigger if (low <= trigger if side == "long" else high >= trigger) else None
    if order_type == "stop":
        # Fills when price breaks THROUGH the level in the trade's direction.
        return trigger if (high >= trigger if side == "long" else low <= trigger) else None
    if order_type == "signal_candle_high":
        return trigger if high >= trigger else None
    if order_type == "signal_candle_low":
        return trigger if low <= trigger else None
    return None


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
    simulation itself.

    Every new Trade Execution/Risk Engine field (Phase 1) is read from
    `strategy.config` and defaults exactly to today's behavior when unset
    -- `getattr(config, ..., default)` throughout, and `config` itself
    defaults to None (market-only, no partial/trailing/time-exit) for any
    Strategy subclass that predates having a `.config` at all. A real
    backtest run with none of these fields set produces byte-identical
    results to before this feature existed."""
    df = strategy.prepare(df)

    config = getattr(strategy, "config", None)
    # Requirement 20 emergency fallback (see EMERGENCY_STOP_PCT / _open_
    # position below) only applies when the strategy actually configured a
    # real stop-loss mechanism -- "unknown" (the field's default) means the
    # strategy never set one and is relying on exit_conditions instead, so
    # forcing a stop onto it would be a genuine behavior change the CEO
    # didn't ask for, not a safety fix.
    stop_loss_type = getattr(getattr(config, "stop_loss", None), "type", None)
    entry_type = (getattr(config, "entry_type", None) or "market").strip().lower()
    # Batch 6, Task 4: per-direction override, None (the default) means
    # "use the shared entry_type" -- resolved per-signal below once `side`
    # is known, never changing behavior for a strategy that never sets these.
    long_entry_type_override = getattr(config, "long_entry_type", None)
    short_entry_type_override = getattr(config, "short_entry_type", None)
    entry_offset_pct = getattr(config, "entry_price_offset_pct", None)
    partial_tp_config = getattr(config, "partial_take_profit", None)
    trailing_config = getattr(config, "trailing_stop", None)
    time_exit_bars = getattr(config, "time_exit_bars", None)

    balance = float(settings["initial_balance"])
    # Position sizing risks a % of this FIXED starting capital, not the
    # ever-growing `balance` below. Risking a % of current equity compounds
    # every single trade -- over the thousands of trades a single backtest
    # coin can produce, that's mathematically guaranteed to blow up to
    # fantasy numbers (verified: one coin went from $1,000 to $164,586 over
    # 1,766 trades this way), regardless of whether the strategy's edge is
    # even real. A live/paper account sizing off its current balance is
    # correct there (trades happen slowly, in real time) -- this only
    # applies to the backtest's single-pass replay of historical bars.
    initial_balance = balance
    commission_pct = settings.get("commission_pct", 0.0) / 100.0
    slippage_pct = settings.get("slippage_pct", 0.0) / 100.0
    spread_pct = settings.get("spread_pct", 0.0) / 100.0
    risk_pct = settings.get("risk_pct", 1.0) / 100.0
    position_size_pct = settings.get("position_size_pct", 10.0) / 100.0
    leverage = max(settings.get("leverage", 1.0) or 1.0, 1.0)
    # Risk Engine circuit breakers (Requirement 11) -- both None/0 by
    # default, which disables them entirely and reproduces every backtest's
    # behavior from before this field existed.
    daily_loss_limit_pct = settings.get("daily_loss_limit_pct") or None
    max_drawdown_limit_pct = settings.get("max_drawdown_limit_pct") or None

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    times = df.index
    atr_col = df["entry_atr_14"].values if "entry_atr_14" in df.columns else None
    # For trailing_stop.type == "structure" -- see _update_trailing_stop's
    # docstring. Precomputed once here, same pattern as atr_col above.
    # Prefers a strategy's own dedicated "entry_trail_support"/
    # "entry_trail_resistance" columns (a strategy can compute these with
    # whatever swing lookback actually suits trailing -- see HTF Trend
    # Trendline Breakout's own trail_support/trail_resistance, lookback=8,
    # deliberately larger/less noisy than the lookback=2 columns most
    # entry-trigger logic uses) and falls back to the plain entry_support/
    # entry_resistance columns the existing "support"/"resistance" concept
    # already produces for any strategy that doesn't provide dedicated
    # trail columns -- so this stays a genuinely general, reusable
    # mechanism, not hardcoded to one strategy's swing lookback. None (the
    # common case: a strategy not using structural trailing) costs nothing.
    if "entry_trail_support" in df.columns:
        structure_support_col = df["entry_trail_support"].values
    elif "entry_support" in df.columns:
        structure_support_col = df["entry_support"].values
    else:
        structure_support_col = None
    if "entry_trail_resistance" in df.columns:
        structure_resistance_col = df["entry_trail_resistance"].values
    elif "entry_resistance" in df.columns:
        structure_resistance_col = df["entry_resistance"].values
    else:
        structure_resistance_col = None

    position = None
    pending = None  # a not-yet-filled Limit/Stop/Signal-Candle/Next-Open order
    trades = []
    equity_curve = []
    trade_num = 0
    n = len(df)
    progress_interval = max(1, n // 50)

    equity_peak = balance
    trading_halted = False  # set permanently once max_drawdown_limit_pct is breached
    daily_pnl = 0.0
    current_day = None

    def _close(position, fill_price_raw, exit_reason, exit_bar_i, size_override=None, is_partial=False):
        """Shared close path for a full exit, a partial exit, and the
        forced end-of-data exit -- one place computes gross/commission/
        slippage/spread/net PnL and appends the trade record, so those
        three call sites can never independently drift out of sync with
        each other.

        gross_pnl is computed from entry_price/exit_price, which already
        have slippage+spread baked in (they're the actual fill prices) --
        slippage_cost/spread_cost below are reported SEPARATELY purely for
        transparency/audit (Requirement 12: verify commission/fees/
        slippage per trade), not subtracted again from net_pnl (only
        commission is an explicit separate deduction, exactly as before
        this feature existed) -- that would double-count a cost already
        reflected in the price difference.

        The ENTRY leg's slippage/spread cost was computed once, at entry,
        against the position's ORIGINAL full size -- a partial close only
        attributes its proportional SHARE of that one-time cost (fraction
        = this close's size / the original entry size), so summing
        slippage_cost/spread_cost across a partial-then-final pair of
        trade rows adds up to the true one-time entry cost exactly once,
        never twice."""
        nonlocal balance, trade_num, daily_pnl
        size = size_override if size_override is not None else position["size"]
        original_size = position.get("_original_size") or size
        fraction = size / original_size if original_size else 1.0

        # Final Audit (Requirement 20): a take-profit hit is a resting LIMIT
        # order -- by definition it fills AT that price or better, never
        # worse, unlike a stop-loss (a stop-MARKET order, which really can
        # slip on a gap). Applying the same adverse slippage/spread used for
        # market exits here could push the realized fill back through
        # entry_price on a tight target, producing exit_reason='take_profit'
        # with a negative gross_pnl -- a real bug the Verification Engine
        # (Requirement 13) caught live on PDH-PDL Signal Candle Strategy (79
        # of 2852 trades). Filled at the exact level instead, same as a real
        # limit order would be.
        if exit_reason in ("take_profit", "partial_take_profit"):
            slipped_price = fill_price_raw
            fill_price = fill_price_raw
        else:
            slipped_price = _apply_slippage(fill_price_raw, position["side"], True, slippage_pct)
            fill_price = _apply_spread(slipped_price, position["side"], True, spread_pct)
        if position["side"] == "long":
            gross_pnl = (fill_price - position["entry_price"]) * size
        else:
            gross_pnl = (position["entry_price"] - fill_price) * size
        commission_cost = (position["entry_price"] + fill_price) * size * commission_pct

        exit_slippage_cost = abs(slipped_price - fill_price_raw) * size
        exit_spread_cost = abs(fill_price - slipped_price) * size
        entry_slippage_share = position.get("_entry_slippage_cost", 0.0) * fraction
        entry_spread_share = position.get("_entry_spread_cost", 0.0) * fraction
        slippage_cost = entry_slippage_share + exit_slippage_cost
        spread_cost = entry_spread_share + exit_spread_cost

        net_pnl = gross_pnl - commission_cost
        balance += net_pnl
        daily_pnl += net_pnl

        trade_num += 1
        trade = {
            "trade_num": trade_num,
            "side": position["side"],
            "entry_time": position["entry_time"],
            "entry_price": position["entry_price"],
            "exit_time": _ts_to_ms(times[exit_bar_i]),
            "exit_price": fill_price,
            "size": size,
            "pnl": net_pnl,
            "gross_pnl": gross_pnl,
            "commission_cost": commission_cost,
            "slippage_cost": slippage_cost,
            "spread_cost": spread_cost,
            "pnl_pct": (net_pnl / (position["entry_price"] * size)) * 100
            if position["entry_price"] * size else 0.0,
            "exit_reason": exit_reason,
            "stop_loss": position["stop_loss"],
            "take_profit": position["take_profit"],
            "risk_amount": _risk_amount({**position, "size": size}),
            "reward_amount": _reward_amount({**position, "size": size}),
            "entry_reason": position["entry_reason"],
            "entry_type": position["entry_type"],
            "is_partial": is_partial,
        }
        trades.append(trade)
        if on_trade:
            on_trade(trade)
        return net_pnl

    def _open_position(side, raw_price, stop_loss, take_profit, reason, entry_type_used, bar_i, risk_multiplier=None):
        """Shared open path for a market fill and a pending-order fill --
        computes the entry-leg slippage/spread cost ONCE here (against the
        full size being opened), so _close() only ever needs to add its
        own exit-leg cost plus this stored share -- never recomputed, never
        silently dropped for a partial close. Returns the new position
        dict, or None if sizing came out to zero (balance exhausted, or a
        leverage/margin cap left nothing to buy)."""
        slipped = _apply_slippage(raw_price, side, False, slippage_pct)
        fill_price = _apply_spread(slipped, side, False, spread_pct)

        # Final Audit (Requirement 20: correct SL/TP execution): stop_loss/
        # take_profit were computed by the strategy against the raw SIGNAL
        # price, before slippage/spread moved the fill. Normally that's a
        # sub-cent difference and never matters -- but a structural zone
        # (stop_loss.type/take_profit.type == "structure") can sit close
        # enough to the signal price that slippage/spread alone pushes the
        # REAL fill_price past it, landing it on the wrong side. Verified
        # live via the Phase 2 Verification Engine against real strategies
        # (Liquidity Sweeps, PDH-PDL Signal Candle Strategy): 7-30% of
        # their trades had a "take_profit" on the wrong side of the actual
        # entry, silently mislabeling real losses as wins. Re-validated
        # here against the REAL fill_price (whatever computed it, not just
        # "structure" specifically -- a general safety net) and discarded
        # rather than trusted if wrong: a missing stop/target is honestly
        # visible in the trade record, a wrong one silently corrupts every
        # downstream number.
        if stop_loss is not None:
            wrong_side = (side == "long" and stop_loss >= fill_price) or (side == "short" and stop_loss <= fill_price)
            if wrong_side:
                stop_loss = None
        # Emergency fallback: a missing stop_loss (unlike a missing take_
        # profit) doesn't just sit "honestly visible" -- it leaves the
        # trade with ZERO downside protection until _check_forced_exit's
        # stop check (which only fires when stop_loss is not None) has
        # nothing left to check, and the position rides to forced
        # end_of_data close, however far price has moved by then. This can
        # happen two ways: discarded just above (wrong-side post-slippage),
        # or never computed at all -- e.g. a "structure" stop-loss whose
        # zone-priority search (order block / FVG / support-resistance)
        # found no valid candidate on the signal bar. Confirmed on live
        # data (Fabio Valentina's Models, ZECUSDT): the latter case, a
        # trade with stop_loss=None from the moment it opened, stayed open
        # over a year and closed at -1075% (then -1183% once the wrong-
        # side branch above was independently fixed and re-run, since this
        # trade was never wrong-side to begin with -- it simply never had
        # a stop). Only applies when the strategy actually configured a
        # real stop-loss mechanism (stop_loss_type not "unknown"/None) --
        # a strategy that deliberately has no stop-loss and relies on
        # exit_conditions instead is untouched. A discarded take_profit has
        # no such failure mode (it only forfeits upside), so that branch
        # below is unchanged.
        if stop_loss is None and stop_loss_type not in (None, "unknown"):
            stop_loss = fill_price * (1 - EMERGENCY_STOP_PCT) if side == "long" else fill_price * (1 + EMERGENCY_STOP_PCT)
        if take_profit is not None:
            wrong_side = (side == "long" and take_profit <= fill_price) or (side == "short" and take_profit >= fill_price)
            if wrong_side:
                take_profit = None

        # New Batch 3, Strategy 1: an optional per-signal soft size
        # reduction (Signal.risk_multiplier -- e.g. "half size on weekends /
        # during a ranging HTF"), distinct from a hard skip. None (every
        # signal from every strategy before this field existed) means 1.0x,
        # byte-for-byte unchanged sizing.
        effective_risk_pct = risk_pct * (risk_multiplier if risk_multiplier is not None else 1.0)
        size = _position_size(initial_balance, balance, fill_price, stop_loss, effective_risk_pct, position_size_pct, leverage)
        if size <= 0:
            return None
        risk_distance = abs(fill_price - stop_loss) if stop_loss is not None else None
        return {
            "side": side,
            "entry_price": fill_price,
            "entry_time": _ts_to_ms(times[bar_i]),
            "entry_bar_index": bar_i,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "size": size,
            "entry_reason": reason or "signal",
            "entry_type": entry_type_used,
            "best_price": fill_price,
            "_original_risk_distance": risk_distance,
            "_original_size": size,
            "_entry_slippage_cost": abs(slipped - raw_price) * size,
            "_entry_spread_cost": abs(fill_price - slipped) * size,
        }

    for i in range(n):
        if control is not None and control.should_stop():
            break

        price = closes[i]
        high = highs[i]
        low = lows[i]
        open_ = opens[i]
        bar_date = times[i].date()
        if current_day != bar_date:
            current_day = bar_date
            daily_pnl = 0.0  # Requirement 11: daily loss limit resets at each new UTC day
        current_atr = None
        if atr_col is not None:
            raw_atr = atr_col[i]
            current_atr = raw_atr if raw_atr == raw_atr else None  # NaN check
        current_structure_support = None
        if structure_support_col is not None:
            raw_sup = structure_support_col[i]
            current_structure_support = raw_sup if raw_sup == raw_sup else None
        current_structure_resistance = None
        if structure_resistance_col is not None:
            raw_res = structure_resistance_col[i]
            current_structure_resistance = raw_res if raw_res == raw_res else None

        signal = strategy.on_bar(df, i, position)

        if position is not None:
            # Optional per-bar position management (e.g. move stop_loss to
            # breakeven, or trail it) -- runs before the forced-exit check
            # so a just-moved stop is checked against THIS bar's high/low
            # like any other stop, exactly as it would in real trading. The
            # base Strategy.manage_position() is a no-op, so this has zero
            # effect on any strategy that doesn't override it.
            strategy.manage_position(df, i, position)
            _update_trailing_stop(position, trailing_config, price, high, low, current_atr,
                                   current_structure_support, current_structure_resistance)

            # Requirement 10: Time Exit -- checked before price-based exits
            # since it's a scheduling decision, not a price trigger; fires
            # at this bar's close, not high/low.
            if time_exit_bars is not None and (i - position["entry_bar_index"]) >= time_exit_bars:
                _close(position, price, "time_exit", i)
                position = None

        if position is not None:
            # Requirement 10: Partial Take Profit -- checked once per bar,
            # before the full SL/TP check, so a bar that touches both the
            # partial level and the full TP/SL still gets the more specific
            # (partial) event recorded first, on the remaining size only.
            partial_price = _check_partial_take_profit(position, partial_tp_config, high, low)
            if partial_price is not None:
                close_fraction = partial_tp_config.get("close_fraction")
                partial_size = position["size"] * close_fraction
                _close(position, partial_price, "partial_take_profit", i, size_override=partial_size, is_partial=True)
                position["size"] -= partial_size
                position["partial_tp_done"] = True

        if position is not None:
            exit_price, exit_reason = _check_forced_exit(position, high, low)
            if exit_price is None and signal is not None and signal.action == "exit":
                exit_price, exit_reason = price, (signal.reason or "signal")

            if exit_price is not None:
                _close(position, exit_price, exit_reason, i)
                position = None

        elif pending is not None:
            # A pending (not-yet-filled) Limit/Stop/Signal-Candle/Next-Open
            # order -- checked every bar until it fills. While pending, the
            # strategy's own on_bar() entry signal for THIS bar is ignored
            # (mirrors "no new signal while a position is open": only one
            # order -- pending or filled -- at a time), so a still-true
            # entry condition can't queue up a second overlapping order.
            fill_price_raw = _check_pending_fill(pending, high, low, open_, bar_is_next_bar=(i == pending["created_bar"] + 1))
            if fill_price_raw is not None:
                position = _open_position(
                    pending["side"], fill_price_raw, pending["stop_loss"], pending["take_profit"],
                    pending["reason"], pending["order_type"], i,
                    risk_multiplier=pending.get("risk_multiplier"),
                )
                pending = None
            elif pending["order_type"] == "next_candle_open" and i > pending["created_bar"]:
                # Should already have filled exactly one bar after creation
                # -- if it somehow didn't (e.g. control-stopped mid-way),
                # drop it rather than leave a stale order silently pending
                # forever.
                pending = None

        elif signal is not None and signal.action in ("buy", "sell") and not trading_halted:
            side = "long" if signal.action == "buy" else "short"

            if knowledge_engine is not None:
                # Lessons are tracked/logged (check() still records each
                # lesson's approved/rejected outcome for Knowledge Score and
                # Reports stats) but never veto a Strategy's own validated
                # signal -- Strategies and Lessons are independent.
                direction = "bullish" if side == "long" else "bearish"
                knowledge_engine.check(df, i, direction)

            # Requirement 11: daily loss limit -- once today's realized
            # losses exceed the configured %, no new entries until the next
            # UTC day (an already-open position, if any, is unaffected --
            # this only blocks NEW ones).
            daily_halted = (
                daily_loss_limit_pct is not None
                and daily_pnl < 0
                and abs(daily_pnl) >= (daily_loss_limit_pct / 100.0) * initial_balance
            )

            if signal is not None and not daily_halted:
                # Batch 6, Task 4: resolve the EFFECTIVE entry type for
                # this specific signal's direction -- the per-direction
                # override if this strategy set one, else the shared
                # entry_type unchanged. A strategy that never sets
                # long_entry_type/short_entry_type always gets
                # effective_entry_type == entry_type, byte-for-byte the
                # same as before this feature existed.
                direction_override = long_entry_type_override if side == "long" else short_entry_type_override
                effective_entry_type = (direction_override or entry_type).strip().lower() if direction_override else entry_type

                if effective_entry_type in ("market", "current_candle_close"):
                    position = _open_position(
                        side, price, signal.stop_loss, signal.take_profit,
                        signal.reason, effective_entry_type, i,
                        risk_multiplier=signal.risk_multiplier,
                    )
                elif effective_entry_type == "next_candle_open":
                    pending = {
                        "side": side, "order_type": "next_candle_open", "trigger_price": None,
                        "stop_loss": signal.stop_loss, "take_profit": signal.take_profit,
                        "reason": signal.reason or "signal", "created_bar": i, "offset_pct": None,
                        "risk_multiplier": signal.risk_multiplier,
                    }
                elif effective_entry_type in ("limit", "stop"):
                    pending = {
                        "side": side, "order_type": effective_entry_type, "trigger_price": None,
                        "offset_pct": entry_offset_pct,
                        "stop_loss": signal.stop_loss, "take_profit": signal.take_profit,
                        "reason": signal.reason or "signal", "created_bar": i,
                        "risk_multiplier": signal.risk_multiplier,
                    }
                    pending["trigger_price"] = _pending_trigger_price(pending, price)
                elif effective_entry_type in ("signal_candle_high", "signal_candle_low"):
                    # Trigger is the SIGNAL bar's own high/low, captured
                    # now -- e.g. "wait for a later candle whose high goes
                    # above the signal candle's high" (a real, previously
                    # unrepresentable strategy rule).
                    trigger_price = high if effective_entry_type == "signal_candle_high" else low
                    pending = {
                        "side": side, "order_type": effective_entry_type, "trigger_price": trigger_price,
                        "offset_pct": None,
                        "stop_loss": signal.stop_loss, "take_profit": signal.take_profit,
                        "reason": signal.reason or "signal", "created_bar": i,
                        "risk_multiplier": signal.risk_multiplier,
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

        # Requirement 11: max drawdown limit -- a permanent circuit breaker
        # for the REST of this backtest once tripped (unlike the daily loss
        # limit, which resets). An already-open position keeps being
        # managed normally; only new entries stop.
        if equity > equity_peak:
            equity_peak = equity
        if (max_drawdown_limit_pct is not None and not trading_halted and equity_peak > 0
                and ((equity_peak - equity) / equity_peak * 100) >= max_drawdown_limit_pct):
            trading_halted = True

        if bar_progress_cb and (i % progress_interval == 0 or i == n - 1):
            bar_progress_cb(i + 1, n, len(trades))

    if position is not None and n > 0:
        _close(position, closes[-1], "end_of_data", n - 1)
        if equity_curve:
            equity_curve[-1] = balance

    return trades, equity_curve, balance

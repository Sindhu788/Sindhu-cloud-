"""Market State Detection + Event Trigger. Classifies each shortlisted
coin's current state (trending up/down, ranging, volatile, breakout) from
cheap, deterministic, transparent rules (no ML) -- and remembers the last
state per coin so the engine only continues the pipeline for a coin when
something actually changed (new candle, trend flip, breakout, volume
spike, structure change). This is the "never scan everything
continuously" gate.
"""

import time

from backtest_engine import concepts
from data_engine.resample import get_ohlcv

_STATE_TIMEFRAME = "15m"
_LOOKBACK_HOURS = 48
_TREND_THRESHOLD_PCT = 0.15
_VOLATILE_THRESHOLD_PCT = 0.6
_BREAKOUT_ATR_MULTIPLE = 2.0


def _now_ms():
    return int(time.time() * 1000)


def classify(exchange, symbol):
    """Returns None if there isn't enough data yet, otherwise a snapshot
    dict describing the coin's current state -- this IS the Market
    Snapshot the spec asks to save when a trade opens."""
    end_ms = _now_ms()
    start_ms = end_ms - _LOOKBACK_HOURS * 3600 * 1000
    df = get_ohlcv(exchange, symbol, interval=_STATE_TIMEFRAME, start_ms=start_ms, end_ms=end_ms)
    if len(df) < 20:
        return None

    closes = df["close"]
    ema_fast = closes.ewm(span=8, adjust=False).mean()
    ema_slow = closes.ewm(span=21, adjust=False).mean()
    trend_strength = float((ema_fast.iloc[-1] - ema_slow.iloc[-1]) / ema_slow.iloc[-1] * 100) if ema_slow.iloc[-1] else 0.0

    returns = closes.pct_change().dropna()
    volatility_pct = float(returns.std() * 100) if len(returns) else 0.0

    atr = concepts.atr(df, 14)
    last_range = float(df["high"].iloc[-1] - df["low"].iloc[-1])
    is_breakout = atr.iloc[-1] and last_range > _BREAKOUT_ATR_MULTIPLE * atr.iloc[-1]

    if is_breakout:
        state = "breakout"
    elif abs(trend_strength) > _TREND_THRESHOLD_PCT:
        state = "trending_up" if trend_strength > 0 else "trending_down"
    elif volatility_pct > _VOLATILE_THRESHOLD_PCT:
        state = "volatile"
    else:
        state = "ranging"

    volume_spike = bool(concepts.volume_filter(df).iloc[-1])

    bull_bos, bear_bos = concepts.break_of_structure(df)
    bull_choch, bear_choch = concepts.change_of_character(df)
    structure = None
    if bool(bull_choch.iloc[-1]):
        structure = "choch_bull"
    elif bool(bear_choch.iloc[-1]):
        structure = "choch_bear"
    elif bool(bull_bos.iloc[-1]):
        structure = "bos_bull"
    elif bool(bear_bos.iloc[-1]):
        structure = "bos_bear"

    last_bar_time = int(df.index[-1].timestamp() * 1000)
    return {
        "exchange": exchange, "symbol": symbol,
        "price": float(closes.iloc[-1]),
        # The latest closed candle's full range, so the Trade Monitor can
        # detect a stop/target that was touched INSIDE this bar rather than
        # only when the sampled close happens to be beyond it -- the same
        # rule backtest_engine.engine._check_forced_exit() applies. Without
        # these, any stop brushed and recovered between two 60s ticks was
        # invisible to paper trading but always caught by the backtest.
        "high": float(df["high"].iloc[-1]),
        "low": float(df["low"].iloc[-1]),
        "market_state": state,
        "trend_strength_pct": round(trend_strength, 4),
        "volatility_pct": round(volatility_pct, 4),
        "volume": float(df["volume"].iloc[-1]),
        "volume_spike": volume_spike,
        "structure": structure,
        "session": concepts.session_of_hour(time.gmtime(last_bar_time / 1000).tm_hour),
        "last_bar_time": last_bar_time,
        "snapshot_at": _now_ms(),
    }


class EventTracker:
    """Remembers the last classified state per (exchange, symbol) across
    ticks -- purely in-memory, which also doubles as the pipeline's
    Decision Cache: if nothing listed below changed, the tick is skipped
    for that coin instead of re-running strategy/lesson evaluation."""

    def __init__(self):
        self._last = {}

    def check(self, snapshot):
        key = (snapshot["exchange"], snapshot["symbol"])
        prev = self._last.get(key)
        self._last[key] = snapshot

        if prev is None:
            return ["new_candle"]

        events = []
        if snapshot["last_bar_time"] != prev["last_bar_time"]:
            events.append("new_candle")
        if snapshot["market_state"] != prev["market_state"]:
            if {snapshot["market_state"], prev["market_state"]} & {"trending_up", "trending_down"}:
                events.append("trend_change")
        if snapshot["market_state"] == "breakout" and prev["market_state"] != "breakout":
            events.append("breakout")
        if snapshot["volume_spike"] and not prev["volume_spike"]:
            events.append("volume_spike")
        if snapshot["structure"] and snapshot["structure"] != prev["structure"]:
            events.append("structure_change")
        return events

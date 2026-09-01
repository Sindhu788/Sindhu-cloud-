"""Every strategy lives in its own file under strategies/ and implements this
interface. SINDHU never invents trading rules on its own -- a strategy here
is always a direct translation of rules given by the CEO."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    action: str  # "buy", "sell", or "exit"
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: Optional[str] = None  # human-readable "why" -- stored as entry/exit reason in trade history
    # Optional soft position-size adjustment for THIS entry only (e.g. "half
    # size on weekends / during a ranging HTF" -- a real filter some
    # strategies describe, distinct from a hard skip). None (every Signal
    # from every strategy before this field existed) means 1.0x -- full,
    # unchanged size. Multiplies the strategy's own risk_pct at position-
    # sizing time (backtest_engine.engine._position_size); never affects
    # stop-loss/take-profit placement.
    risk_multiplier: Optional[float] = None


class Strategy:
    """Subclass this, give it a unique `name`, and implement on_bar()."""

    name = "unnamed"

    def prepare(self, df):
        """Add any indicator columns to `df` (vectorized, runs once per
        coin/timeframe before the bar loop). Default: no indicators."""
        return df

    def on_bar(self, df, i, position):
        """Decide what to do at bar `i`.

        df: the indicator-enriched dataframe returned by prepare().
        i: integer position of the current bar (use df.iloc[:i+1] to avoid
           look-ahead into future bars).
        position: None if flat, otherwise a dict with keys
           side ("long"/"short"), entry_price, stop_loss, take_profit, size.

        Return a Signal, or None to do nothing this bar.
        """
        raise NotImplementedError

    def manage_position(self, df, i, position):
        """Called once per bar, only while a position is open, right
        before the engine checks it for a stop-loss/take-profit hit --
        lets a strategy modify `position` in place (e.g. move stop_loss to
        breakeven once a trigger is reached) without changing on_bar's own
        entry/exit contract. Default: does nothing, so every existing
        Strategy subclass (and every existing backtest result) is
        completely unaffected unless it overrides this."""
        return None

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

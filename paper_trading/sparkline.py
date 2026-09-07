"""Master 15-Item task, Item 7: Telegram Chart Attachment decision.

Decided: a text sparkline, not a real chart image. A real chart (even a
small PNG) needs a plotting library (matplotlib or similar) purely to
render one throwaway image per signal, plus the extra send-a-photo
Telegram API call and byte payload -- real, ongoing weight for a
project whose own stated philosophy elsewhere in this codebase is to
avoid new dependencies unless something genuinely can't be done without
one (see e.g. this project's existing preference for plain HTTP over an
SDK for the Telegram API itself). A short row of Unicode block
characters costs nothing: no new dependency, no extra API call (it's
just more text in the same message already being sent), and it's
already legible in Telegram's monospace-friended message rendering.
Revisit a real image only if the CEO says the text version isn't
useful enough in practice.
"""

_BLOCKS = "▁▂▃▄▅▆▇█"  # ▁▂▃▄▅▆▇█, low to high


def make_sparkline(values):
    """values: a list of real closing prices (or any numeric series),
    oldest first. Returns a short string of block characters, one per
    value, scaled between this series' own min and max -- a flat/empty/
    single-value series (or one with no real variation) returns a
    straight line at the middle block rather than dividing by zero or
    raising. Never raises on bad input (None values, <2 points, all-
    equal) since a signal message must still send even if candle history
    happens to be incomplete for a brand-new coin."""
    clean = [v for v in (values or []) if v is not None]
    if len(clean) < 2:
        return _BLOCKS[len(_BLOCKS) // 2] * max(1, len(clean))

    lo, hi = min(clean), max(clean)
    span = hi - lo
    if span == 0:
        return _BLOCKS[len(_BLOCKS) // 2] * len(clean)

    n_levels = len(_BLOCKS) - 1
    return "".join(_BLOCKS[round((v - lo) / span * n_levels)] for v in clean)

"""Every protective gate between "a candidate signal exists" and "a paper
trade actually opens": Position Lock, Duplicate Signal Protection /
Decision Cache, Trade Reservation, Cooldown, Opposite Signal Protection,
and Signal Priority (when more than one candidate wants the same coin).
"""

import time
from datetime import datetime, timedelta, timezone

from data_engine import storage


def book_key(candidate):
    """Every strategy trades its own independent book (its own balance, PnL,
    open-position cap, guards) -- a candidate with no strategy_id (a
    lesson-only signal) shares one common synthetic "__lessons__" book
    instead, since lessons were never given individual per-lesson books."""
    return candidate.get("strategy_id") or "__lessons__"


def position_locked(book_key, exchange, symbol, direction):
    """If this strategy's BTC Long is already open, never open another
    identical BTC Long for the SAME strategy. Scoped per book so a
    different strategy's identical-looking position never blocks this
    one -- each strategy's positions are independent. Unlocks
    automatically the moment that position closes, because this reads
    live from paper_positions rather than tracking a separate flag."""
    return len(storage.get_open_paper_positions(exchange, symbol, direction, strategy_id=book_key)) > 0


def opposite_open_position(book_key, exchange, symbol, direction):
    opposite = "bearish" if direction == "bullish" else "bullish"
    positions = storage.get_open_paper_positions(exchange, symbol, opposite, strategy_id=book_key)
    return positions[0] if positions else None


def resolve_opposite_signal(book_key, exchange, symbol, direction, policy):
    """Returns ("proceed", None) | ("block", reason) | ("close_and_reverse", position_id).

    Scoped to one book: two DIFFERENT strategies producing opposite signals
    on the same coin are always independent positions and never reach this
    check against each other (each only ever sees its own open positions) --
    this policy only governs a single strategy reversing against itself."""
    opposite = opposite_open_position(book_key, exchange, symbol, direction)
    if not opposite:
        return "proceed", None
    if policy == "allow":
        return "proceed", None
    if policy == "close_and_reverse":
        return "close_and_reverse", opposite["id"]
    return "block", f"opposite {opposite['direction']} position already open (policy=block)"


def cooldown_active(book_key, exchange, symbol, direction, cooldown_minutes):
    if cooldown_minutes <= 0:
        return False
    last = storage.last_closed_paper_position(exchange, symbol, direction, strategy_id=book_key)
    if not last or not last.get("closed_at"):
        return False
    try:
        closed_at = datetime.fromisoformat(last["closed_at"])
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - closed_at) < timedelta(minutes=cooldown_minutes)


def signal_fingerprint(exchange, symbol, candidate):
    """Identifies "the same market condition producing the same signal" --
    used to stop a strategy/lesson from re-firing every tick while the
    condition that triggered it is still true (Duplicate Signal Protection
    doubles as the Decision Cache: identical fingerprint within the TTL
    means "we already decided this," so it's skipped rather than
    recomputed)."""
    source_key = candidate.get("strategy_id") or "lesson:" + "-".join(candidate.get("lesson_ids", []))
    price_bucket = round(candidate["entry_price"], 2)
    return f"{exchange}|{symbol}|{candidate['direction']}|{source_key}|{price_bucket}"


class GuardState:
    """Lives for the lifetime of the running engine (in-memory only --
    restarting the engine just means a clean slate, which is safe since
    Position Lock/Cooldown are re-derived from the database anyway)."""

    def __init__(self):
        self._reserved = set()
        self._decision_cache = {}

    def reserve(self, book_key, exchange, symbol):
        """Trade Reservation: claims a coin for the rest of this tick's
        decision, scoped per book -- guards against this SAME strategy's
        book being processed twice for one coin in one tick pass. Does NOT
        block a different strategy's independent candidate for the same
        coin (each book gets its own reservation), since two different
        strategies must be free to both trade the same coin at once.
        Released at the end of the tick regardless of outcome."""
        key = (book_key, exchange, symbol)
        if key in self._reserved:
            return False
        self._reserved.add(key)
        return True

    def release_all(self):
        self._reserved.clear()

    def is_duplicate(self, fingerprint, ttl_seconds=900):
        now = time.time()
        last_seen = self._decision_cache.get(fingerprint)
        if last_seen is not None and now - last_seen < ttl_seconds:
            return True
        self._decision_cache[fingerprint] = now
        return False


def rank_candidates(candidates, rule="confidence"):
    """Signal Priority: when multiple strategies/lessons trigger on the
    same coin in the same tick, pick one according to the configured
    rule. Ties fall back to confidence."""
    if not candidates:
        return None
    if rule == "win_rate":
        key = lambda c: (c.get("_win_rate", 0), c.get("confidence", 0))
    elif rule == "profit":
        key = lambda c: (c.get("_total_pnl", 0), c.get("confidence", 0))
    elif rule == "manual":
        key = lambda c: (c.get("_manual_priority", 0), c.get("confidence", 0))
    else:
        key = lambda c: (c.get("confidence", 0),)
    return max(candidates, key=key)

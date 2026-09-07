"""Grand Master Prompt, Phase 3.6: Coin Manager (per-coin priority) --
DISTINCT from paper_trading/coin_blacklist.py (a permanent deny-list) and
from coin_filter.py's shortlist() (an activity-score top-N ranker, no
manual override). Two independent, reversible lists a CEO can maintain:

  - "pinned": always included in the tick's shortlist, regardless of how
    coin_filter.py would have ranked it -- for a coin the CEO wants
    watched even if its activity score wouldn't otherwise make the cut.
  - "demoted": excluded from the shortlist the same way blacklist is, but
    kept as a separate, lighter-weight, easily-reversible choice (blacklist
    stays for a genuinely unwanted coin; demoted is for "not right now").

A symbol cannot be both -- setting one clears the other.
"""
from datetime import datetime, timezone

from data_engine import storage


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def pin(symbol, reason=None):
    storage.set_coin_priority(symbol.upper(), "pinned", reason, _now_iso())


def demote(symbol, reason=None):
    storage.set_coin_priority(symbol.upper(), "demoted", reason, _now_iso())


def clear(symbol):
    storage.remove_coin_priority(symbol.upper())


def list_all():
    rows = storage.list_coin_priority()
    return {"pinned": [r for r in rows if r["priority"] == "pinned"],
            "demoted": [r for r in rows if r["priority"] == "demoted"]}


def filter_out_demoted(symbols):
    demoted = {r["symbol"] for r in storage.list_coin_priority(priority="demoted")}
    if not demoted:
        return list(symbols)
    return [s for s in symbols if s not in demoted]


def ensure_pinned_included(shortlist, eligible_symbols, log=None):
    """Appends a minimal {"symbol": s} entry for any pinned symbol that
    coin_filter.shortlist() didn't already include -- ONLY if it's still
    in `eligible_symbols` (i.e. not blacklisted/demoted, and actually
    tradeable on this exchange). Never reorders or removes anything
    shortlist() already picked; only adds missing pinned coins on top."""
    pinned = {r["symbol"] for r in storage.list_coin_priority(priority="pinned")}
    if not pinned:
        return shortlist
    already = {entry["symbol"] for entry in shortlist}
    eligible = set(eligible_symbols)
    added = [s for s in pinned if s not in already and s in eligible]
    if added and log:
        log(f"[coin-priority] pinned coin(s) added to this tick's shortlist: {added}")
    return shortlist + [{"symbol": s} for s in added]

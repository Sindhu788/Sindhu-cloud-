"""Coin Blacklist (Grand Feature Expansion, Phase 5 Feature 1): a genuine
deny-list, distinct from coin_filter.py's shortlist() (a top-N ALLOWLIST
ranked by activity score -- never an exclude mechanism). A blacklisted
symbol is removed BEFORE it is even offered to coin_filter.shortlist(), so
it is never scored, ranked, or traded -- same "additive risk reduction"
category as Kill Switch / Account Drawdown Guard / Auto-Avoid, none of
which this module touches or replaces."""

from datetime import datetime, timezone

from data_engine import storage


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def add(symbol, reason=None):
    storage.add_to_coin_blacklist(symbol.upper(), reason, _now_iso())


def remove(symbol):
    storage.remove_from_coin_blacklist(symbol.upper())


def list_all():
    return storage.list_coin_blacklist()


def filter_out_blacklisted(symbols):
    blacklisted = storage.get_coin_blacklist_symbols()
    if not blacklisted:
        return list(symbols)
    return [s for s in symbols if s not in blacklisted]

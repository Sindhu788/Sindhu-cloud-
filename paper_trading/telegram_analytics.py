"""Task C: read-only analytics over signals already sent to Telegram.
Reuses paper_positions' own status/pnl (via
data_engine.storage.list_telegram_signal_outcomes) as the single source
of truth for win/loss -- the exact same data Paper Trading Analytics
already tracks -- so this module only aggregates, it never computes a
second, independent notion of a trade's outcome.

Win rate is only ever shown once enough CLOSED signals exist to be
meaningful, reusing paper_trading.pattern_stats.MIN_SAMPLE_SIZE (the same
25-trade floor the Genuine Evolution Engine's statistical gate already
uses elsewhere) rather than inventing a separate threshold here."""

from data_engine import storage
from paper_trading import pattern_stats
from paper_trading import config as pt_config

# The hypothetical base capital the $/month tracker simulates trading
# with -- purely a display convenience for "what would this have looked
# like on a small account," not a real balance anywhere in the system.
HYPOTHETICAL_CAPITAL = 100.0


def signal_period_summary(since_iso=None, until_iso=None):
    """How many signals fired in this period, and -- for the ones whose
    underlying trade has actually closed -- the real win/loss split.
    Still-open positions count as 'pending', never as a guessed win/loss."""
    rows = storage.list_telegram_signal_outcomes(since_iso, until_iso)
    wins = sum(1 for r in rows if r["outcome"] == "win")
    losses = sum(1 for r in rows if r["outcome"] == "loss")
    breakeven = sum(1 for r in rows if r["outcome"] == "breakeven")
    pending = sum(1 for r in rows if r["outcome"] == "pending")
    closed = wins + losses + breakeven
    win_rate_pct = round(wins / closed * 100, 1) if closed >= pattern_stats.MIN_SAMPLE_SIZE else None
    return {
        "total_signals": len(rows), "wins": wins, "losses": losses,
        "breakeven": breakeven, "pending": pending, "closed": closed,
        "win_rate_pct": win_rate_pct,
        "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE,
    }


def hypothetical_pnl(since_iso=None, until_iso=None):
    """A clearly-hypothetical "$100 account" tracker for the Telegram
    Dashboard: takes the REAL R-multiple (pnl / risk_amount) of every
    closed, telegram-signaled trade in this period -- the exact same
    ratio storage.get_paper_period_summary's avg_rr already computes from
    -- and rescales it onto a hypothetical HYPOTHETICAL_CAPITAL account
    using the actual configured risk-per-trade percentage
    (paper_trading.config's risk_pct_default, the same number the real
    position sizer uses). Never invents a win, loss, or R-multiple -- only
    real recorded outcomes are used; open/pending trades contribute
    nothing until they actually close."""
    rows = storage.list_telegram_signal_outcomes(since_iso, until_iso)
    risk_pct_default = pt_config.load().get("risk_pct_default", 1.0)
    hypothetical_risk_per_trade = HYPOTHETICAL_CAPITAL * (risk_pct_default / 100.0)

    total_pnl = 0.0
    counted_trades = 0
    for r in rows:
        if r["outcome"] not in ("win", "loss", "breakeven"):
            continue
        risk_amount = r.get("risk_amount")
        if not risk_amount:
            continue
        r_multiple = r["pnl"] / risk_amount
        total_pnl += r_multiple * hypothetical_risk_per_trade
        counted_trades += 1

    return {
        "hypothetical_capital": HYPOTHETICAL_CAPITAL,
        "risk_pct_used": risk_pct_default,
        "counted_trades": counted_trades,
        "hypothetical_pnl": round(total_pnl, 2),
        "hypothetical_balance": round(HYPOTHETICAL_CAPITAL + total_pnl, 2),
    }


def strategy_breakdown(since_iso=None, until_iso=None):
    """Per-strategy signal counts/outcomes for this period, ranked by
    total signals sent -- the per-strategy equivalent of
    signal_period_summary(), same win-rate gating."""
    rows = storage.list_telegram_signal_outcomes(since_iso, until_iso)
    by_strategy = {}
    for r in rows:
        sid = r["strategy_id"] or "unknown"
        entry = by_strategy.setdefault(sid, {
            "strategy_id": r["strategy_id"], "strategy_name": r["strategy_name"] or "Unknown",
            "total_signals": 0, "wins": 0, "losses": 0, "breakeven": 0, "pending": 0,
        })
        entry["total_signals"] += 1
        outcome_key = {"win": "wins", "loss": "losses", "breakeven": "breakeven", "pending": "pending"}.get(r["outcome"])
        if outcome_key:
            entry[outcome_key] += 1

    result = []
    for entry in by_strategy.values():
        closed = entry["wins"] + entry["losses"] + entry["breakeven"]
        entry["closed"] = closed
        entry["win_rate_pct"] = round(entry["wins"] / closed * 100, 1) if closed >= pattern_stats.MIN_SAMPLE_SIZE else None
        result.append(entry)
    result.sort(key=lambda e: e["total_signals"], reverse=True)
    return result

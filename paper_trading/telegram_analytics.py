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
    # Real total PnL (not the hypothetical_pnl() rescaled figure below) --
    # the actual sum of paper_positions.pnl for every closed, Telegram-
    # signaled trade in this period. Still-open ("pending") signals
    # contribute nothing until they actually close, same as win/loss.
    total_pnl = sum(r["pnl"] for r in rows if r["outcome"] in ("win", "loss", "breakeven") and r["pnl"] is not None)
    return {
        "total_signals": len(rows), "wins": wins, "losses": losses,
        "breakeven": breakeven, "pending": pending, "closed": closed,
        "win_rate_pct": win_rate_pct, "total_pnl": round(total_pnl, 2),
        "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE,
    }


def hypothetical_pnl(since_iso=None, until_iso=None, capital=None):
    """Grand Master Batch, Phase 4 Item 2 ("Simulate Real Money"): a
    clearly-hypothetical account tracker for the Telegram Dashboard --
    takes the REAL R-multiple (pnl / risk_amount) of every closed,
    telegram-signaled trade in this period -- the exact same ratio
    storage.get_paper_period_summary's avg_rr already computes from --
    and rescales it onto a hypothetical account of `capital` (defaults to
    HYPOTHETICAL_CAPITAL, but the CEO can plug in any real-money figure
    they're actually considering) using the actual configured
    risk-per-trade percentage (paper_trading.config's risk_pct_default,
    the same number the real position sizer uses). Never invents a win,
    loss, or R-multiple, and never enables real trading -- only real
    recorded outcomes are replayed against a hypothetical stake; open/
    pending trades contribute nothing until they actually close."""
    capital = HYPOTHETICAL_CAPITAL if capital is None else float(capital)
    rows = storage.list_telegram_signal_outcomes(since_iso, until_iso)
    risk_pct_default = pt_config.load().get("risk_pct_default", 1.0)
    hypothetical_risk_per_trade = capital * (risk_pct_default / 100.0)

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
        "hypothetical_capital": capital,
        "risk_pct_used": risk_pct_default,
        "counted_trades": counted_trades,
        "hypothetical_pnl": round(total_pnl, 2),
        "hypothetical_balance": round(capital + total_pnl, 2),
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
            "total_signals": 0, "wins": 0, "losses": 0, "breakeven": 0, "pending": 0, "total_pnl": 0.0,
        })
        entry["total_signals"] += 1
        outcome_key = {"win": "wins", "loss": "losses", "breakeven": "breakeven", "pending": "pending"}.get(r["outcome"])
        if outcome_key:
            entry[outcome_key] += 1
        if r["outcome"] in ("win", "loss", "breakeven") and r["pnl"] is not None:
            entry["total_pnl"] += r["pnl"]

    result = []
    for entry in by_strategy.values():
        closed = entry["wins"] + entry["losses"] + entry["breakeven"]
        entry["closed"] = closed
        entry["win_rate_pct"] = round(entry["wins"] / closed * 100, 1) if closed >= pattern_stats.MIN_SAMPLE_SIZE else None
        entry["total_pnl"] = round(entry["total_pnl"], 2)
        result.append(entry)
    result.sort(key=lambda e: e["total_signals"], reverse=True)
    return result


def best_performing_strategy(since_iso=None, until_iso=None):
    """Part 5 (Telegram-specific analytics): the single best-performing
    strategy among Telegram-SENT signals specifically, by real total PnL
    -- reuses strategy_breakdown() rather than a second query. Only
    considers strategies with at least one CLOSED Telegram-signaled trade
    (an all-pending strategy has no real performance to rank yet). Returns
    None if nothing qualifies."""
    candidates = [s for s in strategy_breakdown(since_iso, until_iso) if s["closed"] > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s["total_pnl"])


def worst_performing_strategy(since_iso=None, until_iso=None):
    """2026-09-15: the mirror of best_performing_strategy above, for the
    new Telegram Signal Performance Report -- same candidate pool (at
    least one CLOSED Telegram-signaled trade), same reuse of
    strategy_breakdown() rather than a second query."""
    candidates = [s for s in strategy_breakdown(since_iso, until_iso) if s["closed"] > 0]
    if not candidates:
        return None
    return min(candidates, key=lambda s: s["total_pnl"])


def status_summary(now=None):
    """2026-09-16 audit (CEO Sections 6.3 + 11): one shared source for the
    dashboard's Telegram Status section AND the daily 24h report, so the two
    can never show different numbers.

    Per-group figures come straight from strategy_groups.all_group_summaries()
    -- the exact function behind the Paper Trading Groups tab -- so they agree
    with that tab by construction. The system-wide total is summed from every
    per-strategy book (paper_account_state), which also includes any book not
    (yet) assigned to a group; `unassigned` makes that difference explicit
    instead of hiding it. As everywhere else in the app, PnL is realized PnL
    since the last Reset Balance, while trade counts are all-time.

    Today's Telegram block reuses signal_period_summary() (UTC day, the same
    bounds as the Telegram page's own "Today" tab); `today_by_group` counts
    today's sent signals by their strategy's CURRENT group, so the CEO can see
    at a glance whether any Losing-group signal went out."""
    from datetime import datetime, timezone
    from paper_trading import strategy_groups

    now = now or datetime.now(timezone.utc)
    today_start_iso = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    groups = strategy_groups.all_group_summaries()
    group_rows = {
        key: {
            "label": g["label"], "strategy_count": g["strategy_count"],
            "closed_trades": g["closed_trades"], "win_count": g["win_count"],
            "win_rate_pct": g["win_rate_pct"], "total_pnl": g["total_pnl"],
            "open_positions": g["open_positions"],
        }
        for key, g in groups.items()
    }

    states = storage.list_paper_account_states()
    total_trades = sum(s.get("closed_count") or 0 for s in states)
    total_wins = sum(s.get("win_count") or 0 for s in states)
    total_pnl = round(sum(s.get("realized_pnl_total") or 0.0 for s in states), 2)
    grouped_trades = sum(g["closed_trades"] for g in group_rows.values())
    grouped_pnl = round(sum(g["total_pnl"] for g in group_rows.values()), 2)

    today = signal_period_summary(today_start_iso, None)
    assignments = storage.list_paper_strategy_groups()
    today_by_group = {key: 0 for key in strategy_groups.GROUP_KEYS}
    today_by_group["unassigned"] = 0
    for row in storage.list_telegram_signal_outcomes(today_start_iso, None):
        key = assignments.get(row.get("strategy_id"))
        today_by_group[key if key in today_by_group else "unassigned"] += 1

    return {
        "generated_at": now.isoformat(),
        "overall": {
            "total_trades": total_trades, "win_count": total_wins,
            "win_rate_pct": round(total_wins / total_trades * 100, 2) if total_trades else 0.0,
            "total_pnl": total_pnl,
        },
        "groups": group_rows,
        "unassigned": {
            "closed_trades": total_trades - grouped_trades,
            "total_pnl": round(total_pnl - grouped_pnl, 2),
        },
        "telegram_today": {
            "day_start_utc": today_start_iso,
            "sent": today["total_signals"], "won": today["wins"], "lost": today["losses"],
            "breakeven": today["breakeven"], "pending": today["pending"],
            "by_group": today_by_group,
        },
    }


def performance_report(since_iso=None, until_iso=None):
    """2026-09-15, urgent CEO directive: the new Telegram Signal
    Performance Report -- win ratio, net PnL ($ and %), best/worst
    strategy, and total signals sent, for signals actually SENT to
    Telegram (never all paper trades). Reuses signal_period_summary() and
    best/worst_performing_strategy() above rather than recomputing win-
    rate/PnL math a second way -- this function only assembles their
    results into the exact shape the new dashboard section needs.

    net_pnl_pct is against the account's configured initial_balance, the
    same denominator paper_trading.strategy_groups.summarize_strategy_ids
    already uses for a group's own balance/PnL% -- not a second,
    competing definition of "percent return"."""
    summary = signal_period_summary(since_iso, until_iso)
    initial_balance = pt_config.load().get("initial_balance", 10000.0)
    net_pnl_pct = round(summary["total_pnl"] / initial_balance * 100, 2) if initial_balance else 0.0
    return {
        "total_signals_sent": summary["total_signals"],
        "win_rate_pct": summary["win_rate_pct"],
        "net_pnl": summary["total_pnl"],
        "net_pnl_pct": net_pnl_pct,
        "closed": summary["closed"],
        "pending": summary["pending"],
        "min_sample_size": summary["min_sample_size"],
        "best_strategy": best_performing_strategy(since_iso, until_iso),
        "worst_strategy": worst_performing_strategy(since_iso, until_iso),
    }

"""Batch 6, Task 5: Live Signal Tracker + Backtest/Paper/Telegram Match
Table. Purely read-only reporting over data that already exists --
telegram_message_log, paper_positions, and backtest_batches/backtest_results
(via backtest_engine.reports.quick_batch_summary) -- it never sends a
signal, opens/closes a position, or runs a backtest. It exists to answer
one question honestly: does what a strategy showed in its backtest still
hold up once it's live in paper trading and being signaled to Telegram?

Divergence is only ever flagged once BOTH sides being compared have at
least pattern_stats.MIN_SAMPLE_SIZE (25) closed trades -- the same
25-trade floor the Genuine Evolution Engine's statistical gate already
uses -- so a strategy with a handful of paper trades never gets an
alarming "diverges from backtest!" label off noise.
"""

from data_engine import storage
from backtest_engine.reports import quick_batch_summary
from paper_trading import pattern_stats
from paper_trading import telegram_analytics

# How many percentage points apart two win rates need to be, once both
# sides have enough trades to trust, before this is reported as a real
# divergence worth a human's attention rather than routine sampling noise.
DIVERGENCE_THRESHOLD_PCT = 15.0


def live_signal_feed(limit=50):
    """Every real Telegram signal actually sent, newest first, each with
    its real current outcome (win/loss/breakeven/pending/unknown) --
    reuses storage.list_telegram_signal_outcomes(), the same send-to-
    outcome join the Telegram Dashboard's per-signal list already uses.
    Adds a running summary (counts + win rate, gated at MIN_SAMPLE_SIZE
    like every other win-rate figure in this system)."""
    rows = storage.list_telegram_signal_outcomes()
    feed = rows[:limit]
    wins = sum(1 for r in rows if r["outcome"] == "win")
    losses = sum(1 for r in rows if r["outcome"] == "loss")
    breakeven = sum(1 for r in rows if r["outcome"] == "breakeven")
    pending = sum(1 for r in rows if r["outcome"] == "pending")
    closed = wins + losses + breakeven
    win_rate_pct = round(wins / closed * 100, 1) if closed >= pattern_stats.MIN_SAMPLE_SIZE else None
    return {
        "signals": feed,
        "total_signals": len(rows),
        "wins": wins, "losses": losses, "breakeven": breakeven, "pending": pending,
        "closed": closed, "win_rate_pct": win_rate_pct,
        "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE,
    }


def _backtest_win_rate(strategy_name):
    # The lightweight cloud runner's curated Postgres schema deliberately
    # excludes backtest_batches/backtest_results (see data_engine/
    # db_backend.py's POSTGRES_SCHEMA docstring) -- on that runner this
    # query would raise "relation does not exist" rather than return no
    # rows. Treated the same as "no backtest exists yet for this strategy"
    # (None, None) rather than crashing this page's other two, genuinely
    # available comparisons (paper vs Telegram-sent).
    try:
        batch_id = storage.latest_completed_batch_for_strategy_name(strategy_name)
    except Exception:
        return None, None
    if not batch_id:
        return None, None
    summary = quick_batch_summary(batch_id)
    if not summary or not summary.get("total_trades"):
        return None, batch_id
    return summary["win_rate"], batch_id


def strategy_match_table():
    """One row per strategy that has ever closed a paper trade: backtest
    win rate (from its most recent completed backtest, matched by name),
    paper win rate (every closed paper trade), and Telegram-sent win rate
    (only the subset of paper trades that were actually signaled) --
    side by side, with a `diverges` flag when paper and Telegram-sent win
    rates disagree by more than DIVERGENCE_THRESHOLD_PCT once both have
    enough closed trades to trust."""
    paper_stats = {s["strategy_id"]: s for s in storage.list_paper_strategy_stats()}
    telegram_stats = {s["strategy_id"]: s for s in telegram_analytics.strategy_breakdown()}

    strategy_ids = set(paper_stats) | set(telegram_stats)
    rows = []
    for sid in strategy_ids:
        p = paper_stats.get(sid)
        t = telegram_stats.get(sid)
        name = (p or t)["strategy_name"]
        backtest_win_rate, backtest_batch_id = _backtest_win_rate(name)

        paper_win_rate = p["win_rate"] if p else None
        paper_closed = p["closed_trades"] if p else 0
        telegram_win_rate = t["win_rate_pct"] if t else None
        telegram_closed = t["closed"] if t else 0

        diverges = (
            paper_win_rate is not None and telegram_win_rate is not None
            and paper_closed >= pattern_stats.MIN_SAMPLE_SIZE
            and telegram_closed >= pattern_stats.MIN_SAMPLE_SIZE
            and abs(paper_win_rate - telegram_win_rate) >= DIVERGENCE_THRESHOLD_PCT
        )
        # Grand Feature Expansion, Phase 1 Feature 8: the comparison the
        # feature is actually named for -- does live paper performance
        # still hold up against what the backtest showed? -- distinct from
        # `diverges` above (paper vs the Telegram-sent SUBSET). Gated the
        # same way: only once paper trading itself has enough closed trades
        # to trust (a completed backtest's own win rate is already a fixed,
        # trusted figure from a full historical run, so only the paper side
        # needs the sample-size floor).
        backtest_vs_paper_diverges = (
            backtest_win_rate is not None and paper_win_rate is not None
            and paper_closed >= pattern_stats.MIN_SAMPLE_SIZE
            and abs(backtest_win_rate - paper_win_rate) >= DIVERGENCE_THRESHOLD_PCT
        )

        rows.append({
            "strategy_id": sid, "strategy_name": name,
            "backtest_win_rate": backtest_win_rate, "backtest_batch_id": backtest_batch_id,
            "paper_win_rate": paper_win_rate, "paper_closed_trades": paper_closed,
            "telegram_win_rate": telegram_win_rate, "telegram_closed_trades": telegram_closed,
            "diverges": diverges,
            "backtest_vs_paper_diverges": backtest_vs_paper_diverges,
        })

    rows.sort(key=lambda r: r["paper_closed_trades"], reverse=True)
    return {
        "strategies": rows,
        "divergence_threshold_pct": DIVERGENCE_THRESHOLD_PCT,
        "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE,
    }


# Grand Feature Expansion, Phase 1 Feature 8: this table's backtest_vs_paper_diverges
# flag was purely passive (a badge nobody would see without opening this
# page) -- this turns a real divergence into an actual alert, reusing the
# existing paper_alerts table/Alerts dashboard section rather than a new
# notification channel. Throttled so the SAME still-diverging strategy is
# not re-alerted on every check -- only once per ALERT_RECHECK_HOURS.
ALERT_RECHECK_HOURS = 24


def check_and_alert_divergence(now_iso=None):
    """Call periodically (see paper_trading.engine's tick loop). Read-only
    over strategy_match_table() plus one paper_alerts write per newly (or
    still, past the recheck window) diverging strategy. Returns the list of
    strategy_ids a fresh alert was just created for."""
    from datetime import datetime, timedelta, timezone
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    since = (datetime.now(timezone.utc) - timedelta(hours=ALERT_RECHECK_HOURS)).isoformat()

    alerted = []
    table = strategy_match_table()
    for row in table["strategies"]:
        if not row["backtest_vs_paper_diverges"]:
            continue
        if storage.get_recent_paper_alert("backtest_paper_divergence", row["strategy_id"], since):
            continue
        message = (
            f"{row['strategy_name']}: backtest showed a {row['backtest_win_rate']:.1f}% win rate, "
            f"but live paper trading is showing {row['paper_win_rate']:.1f}% over "
            f"{row['paper_closed_trades']} closed trades -- a "
            f"{abs(row['backtest_win_rate'] - row['paper_win_rate']):.1f} point gap. "
            f"Worth reviewing whether market conditions have changed or the backtest was overfit."
        )
        storage.create_paper_alert(
            "backtest_paper_divergence", row["strategy_id"], row["strategy_name"],
            message, "warning", now_iso,
        )
        alerted.append(row["strategy_id"])
    return alerted

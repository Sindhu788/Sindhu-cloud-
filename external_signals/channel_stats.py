"""Phase 4 -- per-channel results, and the honest cross-channel
comparison view. Every number here comes from real stored
external_positions/external_channel_performance rows -- nothing
estimated, nothing averaged across channels.
"""

from data_engine import storage
from paper_trading import pattern_stats  # reused, not reimplemented: the SAME 25-trade Wilson-interval

PROVING_TRADES_REQUIRED = 30


def channel_report(channel_id):
    channel = storage.get_external_channel(channel_id)
    if not channel:
        return None
    perf = storage.get_external_channel_performance(channel_id)
    closed = storage.list_external_positions(channel_id=channel_id, status="closed")
    open_positions = storage.list_external_positions(channel_id=channel_id, status="open")
    pending = storage.list_external_positions(channel_id=channel_id, status="pending")

    win_rate_pct = round(perf["wins"] / perf["trades"] * 100.0, 1) if perf["trades"] else None
    avg_rr = round(perf["total_rr_sum"] / perf["trades"], 2) if perf["trades"] else None

    coin_breakdown = storage.external_channel_coin_breakdown(channel_id)
    best_coin = max(coin_breakdown, key=lambda c: c["total_pnl"], default=None)
    worst_coin = min(coin_breakdown, key=lambda c: c["total_pnl"], default=None)

    # Reuses the EXISTING 25-trade Wilson Score classification (never a
    # second/weaker confidence system) purely to label how much this
    # channel's own win rate can be trusted -- separate from, and layered
    # on top of, this module's own 30-trade proving threshold.
    reliability = pattern_stats.classify(perf["wins"], perf["trades"]) if perf["trades"] else None

    return {
        "channel_id": channel_id, "name": channel["name"], "enabled": bool(channel["enabled"]),
        "forwarding_source_label": channel["forwarding_source_label"],
        "balance": round(perf["balance"], 2),
        "closed_trades": len(closed), "open_trades": len(open_positions), "pending_trades": len(pending),
        "win_rate_pct": win_rate_pct, "total_pnl": round(perf["total_pnl"], 2), "avg_rr": avg_rr,
        "best_coin": best_coin, "worst_coin": worst_coin,
        "proving_progress": min(len(closed), PROVING_TRADES_REQUIRED),
        "proving_required": PROVING_TRADES_REQUIRED,
        "is_proven_sample_size": len(closed) >= PROVING_TRADES_REQUIRED,
        "reliability": reliability,
    }


def all_channel_reports():
    return [channel_report(c["id"]) for c in storage.list_external_channels()]


def comparison_view():
    """Side-by-side view across every channel -- explicitly labels a
    small-sample channel's numbers as statistically unproven instead of
    letting a lucky streak look like real edge, same honesty principle
    Challenge Mode/Strategy Lab already apply."""
    reports = all_channel_reports()
    for r in reports:
        r["honest_label"] = (
            f"Unproven -- only {r['closed_trades']}/{r['proving_required']} trades closed, numbers can change a lot"
            if not r["is_proven_sample_size"]
            else ("Reliable" if r["reliability"] and r["reliability"]["reliable"] else "Proven sample, but not yet a clearly reliable edge")
        )
    reports.sort(key=lambda r: (r["is_proven_sample_size"], r["total_pnl"]), reverse=True)
    return reports

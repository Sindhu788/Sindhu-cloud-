"""Coin-Performance Heatmap (Grand Feature Expansion, Phase 3 Feature 3):
which coins are CONSISTENTLY profitable across every strategy that has
traded them, not just which coin has the best raw total PnL (already
answered by storage.list_paper_coin_stats -- a single outlier strategy
could be propping up an otherwise-mediocre coin's aggregate number, and
that flat ranking has no way to show that).
"""

from data_engine import storage


def compute_coin_heatmap(since_iso=None):
    """Returns one row per coin that has closed at least one trade,
    sorted by consistency (what fraction of the strategies that traded it
    were profitable on it) first, then total PnL -- so a coin that is
    reliably good across many strategies ranks above one coin whose big
    total PnL come from a single lucky strategy."""
    rows = storage.list_paper_coin_strategy_matrix(since_iso=since_iso)
    by_symbol = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], []).append(r)

    result = []
    for symbol, entries in by_symbol.items():
        strategy_count = len(entries)
        profitable_count = sum(1 for e in entries if e["total_pnl"] > 0)
        result.append({
            "symbol": symbol,
            "strategy_count": strategy_count,
            "profitable_strategy_count": profitable_count,
            "consistency_pct": round(profitable_count / strategy_count * 100, 1),
            "avg_win_rate": round(sum(e["win_rate"] for e in entries) / strategy_count, 1),
            "total_pnl": round(sum(e["total_pnl"] for e in entries), 2),
            "closed_trades": sum(e["closed_trades"] for e in entries),
        })

    result.sort(key=lambda r: (r["consistency_pct"], r["total_pnl"]), reverse=True)
    return result


def compute_coin_deep_dive(symbol, since_iso=None):
    """Grand Feature Expansion, Phase 3 Feature 17: Coin-Specific Deep-Dive
    -- every strategy's own performance on ONE symbol, side by side.
    Reuses the exact same raw matrix compute_coin_heatmap() builds from
    (storage.list_paper_coin_strategy_matrix), just filtered to one coin
    and sorted per-strategy instead of aggregated per-coin."""
    rows = [r for r in storage.list_paper_coin_strategy_matrix(since_iso=since_iso) if r["symbol"] == symbol]
    rows.sort(key=lambda r: r["total_pnl"], reverse=True)

    total_trades = sum(r["closed_trades"] for r in rows)
    total_pnl = round(sum(r["total_pnl"] for r in rows), 2)
    profitable_strategies = sum(1 for r in rows if r["total_pnl"] > 0)

    return {
        "symbol": symbol,
        "strategies": rows,
        "strategy_count": len(rows),
        "profitable_strategy_count": profitable_strategies,
        "total_closed_trades": total_trades,
        "total_pnl": total_pnl,
    }

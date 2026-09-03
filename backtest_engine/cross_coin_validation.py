"""Cross-Coin Group Validation (Grand Feature Expansion, Phase 6 Feature
8): checks whether a strategy's real backtest performance holds up
similarly across DIFFERENT VOLATILITY GROUPS of coins, not just overfit to
one specific coin's quirks -- distinct from the existing per-coin ranking
table (a flat list of every coin, no grouping at all).

Reuses paper_trading.coin_filter's own existing volatility scoring
(_coin_activity_score) rather than inventing a second metric, and splits
coins into low/medium/high volatility TERCILES computed fresh from real
data every time -- never a hardcoded large-cap/small-cap list, which
would silently go stale as the market changes (same reasoning
coin_filter.py's own docstring already gives for not hardcoding a
"these coins move together" list)."""

from data_engine import storage
from paper_trading.coin_filter import _coin_activity_score

GROUP_LABELS = ["low_volatility", "medium_volatility", "high_volatility"]
# A strategy is called "consistent across groups" when the win rate swing
# between its best and worst volatility group stays within this many
# percentage points -- a documented, disclosed threshold, not a hidden one.
MAX_WIN_RATE_SWING_FOR_CONSISTENCY_PTS = 20.0


def _volatility_tercile_groups(exchange, symbols):
    scored = []
    for symbol in symbols:
        try:
            s = _coin_activity_score(exchange, symbol)
        except Exception:
            s = None
        if s:
            scored.append((symbol, s["volatility_pct"]))
    if not scored:
        return {}
    scored.sort(key=lambda pair: pair[1])
    n = len(scored)
    third = max(1, n // 3)
    groups = {}
    for i, (symbol, _) in enumerate(scored):
        if i < third:
            groups[symbol] = "low_volatility"
        elif i < 2 * third:
            groups[symbol] = "medium_volatility"
        else:
            groups[symbol] = "high_volatility"
    return groups


def validate_across_coin_groups(batch_id):
    batch = storage.get_batch(batch_id)
    if not batch:
        return None
    results = storage.get_batch_results(batch_id)
    completed = [r for r in results if r["status"] == "completed" and r.get("metrics")]
    if not completed:
        return {"groups": [], "consistent_across_groups": None,
                "reason": "no completed coin results in this batch yet"}

    exchange = batch["exchange"]
    symbols = [r["symbol"] for r in completed]
    group_of = _volatility_tercile_groups(exchange, symbols)

    by_group = {}
    for r in completed:
        group = group_of.get(r["symbol"])
        if group:
            by_group.setdefault(group, []).append(r)

    summary = []
    for label in GROUP_LABELS:
        rows = by_group.get(label, [])
        if not rows:
            continue
        total_trades = sum(row["metrics"].get("total_trades", 0) for row in rows)
        wins = sum(row["metrics"].get("wins", 0) for row in rows)
        net_pnl = sum(row["metrics"].get("net_profit", 0) or 0 for row in rows)
        win_rate = round(wins / total_trades * 100, 2) if total_trades else None
        summary.append({
            "group": label, "coin_count": len(rows), "total_trades": total_trades,
            "win_rate": win_rate, "net_pnl": round(net_pnl, 2),
        })

    if len(summary) < 2:
        return {"groups": summary, "consistent_across_groups": None,
                "reason": "this batch's coins don't span enough distinct volatility groups to compare"}

    win_rates = [g["win_rate"] for g in summary if g["win_rate"] is not None]
    if len(win_rates) < 2:
        consistent = None
    else:
        consistent = (max(win_rates) - min(win_rates)) <= MAX_WIN_RATE_SWING_FOR_CONSISTENCY_PTS

    return {"groups": summary, "consistent_across_groups": consistent, "reason": None}

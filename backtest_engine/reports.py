import json
import os
from datetime import datetime, timezone

from data_engine import storage
from data_engine.paths import REPORTS_DIR
from backtest_engine.concepts import session_of_hour


def quick_batch_summary(batch_id):
    """Cheap per-batch summary for list views (Backtest History) -- avoids
    recomputing coin/timeframe ranking, session analysis, and lesson stats
    that generate_report() does for a single batch's detail view. Returns
    None if the batch has no completed results yet."""
    batch = storage.get_batch(batch_id)
    if not batch:
        return None
    results = storage.get_batch_results(batch_id)
    completed = [r for r in results if r["status"] == "completed" and r["metrics"]]
    if not completed:
        return {
            "batch_id": batch_id, "strategy": batch["strategy_name"],
            "symbol_count": len(results), "combos_completed": 0, "combos_total": len(results),
            "total_trades": 0, "win_rate": 0.0, "total_pnl": None,
            "avg_profit_pct": 0.0, "avg_final_balance": None, "max_drawdown_pct": 0.0,
        }

    total_trades = sum(r["metrics"]["total_trades"] for r in completed)
    wins = sum(r["metrics"]["wins"] for r in completed)
    win_rate = (wins / total_trades * 100) if total_trades else 0.0
    initial_balance = (batch.get("settings") or {}).get("initial_balance")
    total_pnl = (
        round(sum(r["metrics"]["final_balance"] - initial_balance for r in completed), 2)
        if initial_balance is not None else None
    )
    avg_profit_pct = sum(r["metrics"]["profit_pct"] for r in completed) / len(completed)
    avg_final_balance = sum(r["metrics"]["final_balance"] for r in completed) / len(completed)
    max_drawdown = max((r["metrics"]["max_drawdown_pct"] for r in completed), default=0.0)
    return {
        "batch_id": batch_id, "strategy": batch["strategy_name"],
        "symbol_count": len(results), "combos_completed": len(completed), "combos_total": len(results),
        "total_trades": total_trades, "win_rate": round(win_rate, 2), "total_pnl": total_pnl,
        "avg_profit_pct": round(avg_profit_pct, 2), "avg_final_balance": round(avg_final_balance, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
    }


def _aggregate_by(results, key):
    """Average profit % per symbol or per timeframe, across completed
    combos -- used to pick best/worst coin and best/worst timeframe."""
    totals, counts = {}, {}
    for r in results:
        if r["status"] != "completed" or not r["metrics"]:
            continue
        k = r[key]
        totals[k] = totals.get(k, 0.0) + r["metrics"]["profit_pct"]
        counts[k] = counts.get(k, 0) + 1
    return {k: totals[k] / counts[k] for k in totals}


def _rank_by(results, key, initial_balance=None):
    """Full ranked list (best first) of {key, combos, total_trades,
    win_rate, avg_profit_pct, total_pnl, max_drawdown_pct,
    avg_profit_factor} -- the Coin Ranking / Timeframe Ranking views read
    this directly. total_pnl (dollar, summed final_balance-initial_balance
    across every combo grouped under this key) is only computed when
    initial_balance is given, since the timeframe grouping doesn't need it."""
    grouped = {}
    for r in results:
        if r["status"] != "completed" or not r["metrics"]:
            continue
        grouped.setdefault(r[key], []).append(r["metrics"])

    ranked = []
    for k, metrics_list in grouped.items():
        total_trades = sum(m["total_trades"] for m in metrics_list)
        wins = sum(m["wins"] for m in metrics_list)
        win_rate = (wins / total_trades * 100) if total_trades else 0.0
        avg_profit = sum(m["profit_pct"] for m in metrics_list) / len(metrics_list)
        max_dd = max((m["max_drawdown_pct"] for m in metrics_list), default=0.0)
        pfs = [m["profit_factor"] for m in metrics_list if m["profit_factor"] is not None]
        avg_pf = sum(pfs) / len(pfs) if pfs else None
        entry = {
            key: k, "combos": len(metrics_list), "total_trades": total_trades,
            "win_rate": round(win_rate, 2), "avg_profit_pct": round(avg_profit, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "avg_profit_factor": round(avg_pf, 4) if avg_pf is not None else None,
        }
        if initial_balance is not None:
            entry["total_pnl"] = round(sum(m["final_balance"] - initial_balance for m in metrics_list), 2)
        ranked.append(entry)
    ranked.sort(key=lambda r: r["avg_profit_pct"], reverse=True)
    return ranked


def _session_analysis(batch_id):
    """Groups every trade in the batch by the UTC session its entry fell
    in (Asian/London/NY), ranked by total pnl -- shows which session this
    strategy actually performs best in."""
    trades = storage.get_trades(batch_id)
    buckets = {}
    for t in trades:
        if t.get("pnl") is None or t.get("entry_time") is None:
            continue
        dt = datetime.fromtimestamp(t["entry_time"] / 1000, tz=timezone.utc)
        session = session_of_hour(dt.hour)
        buckets.setdefault(session, []).append(t)

    result = []
    for session, tlist in buckets.items():
        total = len(tlist)
        wins = sum(1 for t in tlist if t["pnl"] > 0)
        total_pnl = sum(t["pnl"] for t in tlist)
        result.append({
            "session": session, "trades": total,
            "win_rate": round((wins / total * 100) if total else 0.0, 2),
            "total_pnl": round(total_pnl, 4),
        })
    result.sort(key=lambda r: r["total_pnl"], reverse=True)
    return result


def generate_report(batch_id):
    batch = storage.get_batch(batch_id)
    results = storage.get_batch_results(batch_id)
    completed = [r for r in results if r["status"] == "completed" and r["metrics"]]

    total_trades = sum(r["metrics"]["total_trades"] for r in completed)
    wins = sum(r["metrics"]["wins"] for r in completed)
    losses = sum(r["metrics"]["losses"] for r in completed)
    win_rate = (wins / total_trades * 100) if total_trades else 0.0
    avg_profit_pct = (sum(r["metrics"]["profit_pct"] for r in completed) / len(completed)) if completed else 0.0
    avg_final_balance = (sum(r["metrics"]["final_balance"] for r in completed) / len(completed)) if completed else 0.0
    max_drawdown = max((r["metrics"]["max_drawdown_pct"] for r in completed), default=0.0)
    avg_win = (sum(r["metrics"]["avg_win"] for r in completed) / len(completed)) if completed else 0.0
    avg_loss = (sum(r["metrics"]["avg_loss"] for r in completed) / len(completed)) if completed else 0.0

    profit_factors = [r["metrics"]["profit_factor"] for r in completed if r["metrics"]["profit_factor"] is not None]
    avg_profit_factor = sum(profit_factors) / len(profit_factors) if profit_factors else None
    risk_rewards = [r["metrics"]["risk_reward"] for r in completed if r["metrics"]["risk_reward"] is not None]
    avg_risk_reward = sum(risk_rewards) / len(risk_rewards) if risk_rewards else None

    initial_balance = (batch.get("settings") or {}).get("initial_balance")
    total_pnl = (
        round(sum(r["metrics"]["final_balance"] - initial_balance for r in completed), 2)
        if completed and initial_balance is not None else None
    )

    by_symbol = _aggregate_by(completed, "symbol")
    by_timeframe = _aggregate_by(completed, "timeframe")
    coin_ranking = _rank_by(completed, "symbol", initial_balance=initial_balance)
    timeframe_ranking = _rank_by(completed, "timeframe")
    session_analysis = _session_analysis(batch_id)

    best_coin = max(by_symbol, key=by_symbol.get) if by_symbol else None
    worst_coin = min(by_symbol, key=by_symbol.get) if by_symbol else None
    # coin_ranking is sorted best-first by avg_profit_pct (same criterion as
    # best_coin/worst_coin above), so its first/last rows carry the exact
    # PnL/win-rate figures for whichever symbol that already picked.
    best_coin_row = coin_ranking[0] if coin_ranking else None
    worst_coin_row = coin_ranking[-1] if coin_ranking else None
    best_timeframe = max(by_timeframe, key=by_timeframe.get) if by_timeframe else None
    worst_timeframe = min(by_timeframe, key=by_timeframe.get) if by_timeframe else None
    best_session = session_analysis[0]["session"] if session_analysis else None
    worst_session = session_analysis[-1]["session"] if session_analysis else None
    lesson_stats = storage.get_batch_lesson_stats(batch_id)

    summary = {
        "batch_id": batch_id,
        "strategy": batch["strategy_name"],
        "exchange": batch["exchange"],
        "settings": batch["settings"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "combos_completed": len(completed),
        "combos_total": len(results),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "avg_profit_pct": round(avg_profit_pct, 2),
        "total_pnl": total_pnl,
        "avg_final_balance": round(avg_final_balance, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "avg_profit_factor": round(avg_profit_factor, 4) if avg_profit_factor is not None else None,
        "avg_risk_reward": round(avg_risk_reward, 4) if avg_risk_reward is not None else None,
        "best_coin": best_coin,
        "worst_coin": worst_coin,
        "best_coin_pnl": best_coin_row["total_pnl"] if best_coin_row else None,
        "best_coin_win_rate": best_coin_row["win_rate"] if best_coin_row else None,
        "worst_coin_pnl": worst_coin_row["total_pnl"] if worst_coin_row else None,
        "worst_coin_win_rate": worst_coin_row["win_rate"] if worst_coin_row else None,
        "best_timeframe": best_timeframe,
        "worst_timeframe": worst_timeframe,
        "best_session": best_session,
        "worst_session": worst_session,
        "coin_ranking": coin_ranking,
        "timeframe_ranking": timeframe_ranking,
        "session_analysis": session_analysis,
        "lessons_applied": lesson_stats["lessons_applied"],
        "trades_approved_by_lessons": lesson_stats["trades_approved_by_lessons"],
        "trades_rejected_by_lessons": lesson_stats["trades_rejected_by_lessons"],
        "results": results,
    }

    out_dir = os.path.join(REPORTS_DIR, batch_id)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write(_render_text(summary))

    return summary


def _render_text(s):
    def fmt(v):
        return "N/A" if v is None else v

    lines = [
        "SINDHU Backtest Report",
        f"Batch: {s['batch_id']}",
        f"Strategy: {s['strategy']}",
        f"Exchange: {s['exchange']}",
        f"Generated: {s['generated_at']}",
        "",
        f"Coin/Timeframe Combos: {s['combos_completed']} / {s['combos_total']} completed",
        "",
        f"Total Trades: {s['total_trades']}",
        f"Wins: {s['wins']}",
        f"Losses: {s['losses']}",
        f"Win Rate: {s['win_rate']}%",
        f"Average Profit %: {s['avg_profit_pct']}%",
        f"Total PnL (all coins combined): {fmt(s['total_pnl'])}",
        f"Average Final Balance: {s['avg_final_balance']}",
        f"Maximum Drawdown: {s['max_drawdown_pct']}%",
        f"Average Win: {s['avg_win']}",
        f"Average Loss: {s['avg_loss']}",
        f"Profit Factor: {fmt(s['avg_profit_factor'])}",
        f"Risk Reward: {fmt(s['avg_risk_reward'])}",
        "",
        f"Best Coin: {fmt(s['best_coin'])} (PnL={fmt(s['best_coin_pnl'])}, win_rate={fmt(s['best_coin_win_rate'])}%)",
        f"Worst Coin: {fmt(s['worst_coin'])} (PnL={fmt(s['worst_coin_pnl'])}, win_rate={fmt(s['worst_coin_win_rate'])}%)",
        f"Best Timeframe: {fmt(s['best_timeframe'])}",
        f"Worst Timeframe: {fmt(s['worst_timeframe'])}",
        f"Best Session: {fmt(s['best_session'])}",
        f"Worst Session: {fmt(s['worst_session'])}",
        "",
        f"Lessons Applied: {s['lessons_applied']}",
        f"Trades Approved by Lessons: {s['trades_approved_by_lessons']}",
        f"Trades Rejected by Lessons: {s['trades_rejected_by_lessons']}",
        "",
        "Coin Ranking:",
    ]
    for r in s["coin_ranking"]:
        lines.append(f"  {r['symbol']:<14} profit={r['avg_profit_pct']:>7}%  pnl={fmt(r.get('total_pnl')):>10}  "
                      f"win_rate={r['win_rate']:>6}%  trades={r['total_trades']:<5} drawdown={r['max_drawdown_pct']}%")

    lines.append("")
    lines.append("Timeframe Ranking:")
    for r in s["timeframe_ranking"]:
        lines.append(f"  {r['timeframe']:<6} profit={r['avg_profit_pct']:>7}%  win_rate={r['win_rate']:>6}%  "
                      f"trades={r['total_trades']:<5} drawdown={r['max_drawdown_pct']}%")

    lines.append("")
    lines.append("Session Analysis:")
    for r in s["session_analysis"]:
        lines.append(f"  {r['session']:<10} trades={r['trades']:<5} win_rate={r['win_rate']:>6}%  total_pnl={r['total_pnl']}")

    return "\n".join(lines)

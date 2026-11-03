"""Weekly scorecard (read-only): performance by group / strategy / coin, confidence calibration and RECOMMENDED pauses.

Never changes anything - pauses are only recommended, with sample size and a Wilson interval so small samples are not
over-read. Works on SQLite (local) and Postgres (Cloud) through data_engine.storage.
"""
import math
from datetime import datetime, timezone

from paper_trading.pattern_stats import MIN_SAMPLE_SIZE, wilson_interval

CALIBRATION_CUTOFF = "2026-09-17"          # confidence was recalibrated on this date; older trades are not comparable
MIN_CALIBRATION_TRADES = 100                # below this the buckets say nothing
BUCKETS = ((0, 50), (50, 60), (60, 70), (70, 80), (80, 101))


def _to_dt(v):
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            return datetime.fromtimestamp(float(v) / 1000.0, tz=timezone.utc)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def load_trades(conn):
    rows = conn.execute(
        "SELECT p.symbol, p.entry_time, p.pnl, p.strategy_id, p.strategy_name, p.confidence, g.group_key "
        "FROM paper_positions p LEFT JOIN paper_strategy_groups g ON g.strategy_id = p.strategy_id "
        "WHERE p.status != 'open' AND p.pnl IS NOT NULL").fetchall()
    return [{"symbol": r[0], "entry": _to_dt(r[1]), "pnl": float(r[2]), "strategy_id": r[3],
             "strategy": r[4] or r[3] or "?", "confidence": None if r[5] is None else float(r[5]),
             "group": r[6] or "unclassified"} for r in rows]


def stats(trades):
    n = len(trades)
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    gross_w, gross_l = sum(wins), -sum(losses)
    avg_w = gross_w / len(wins) if wins else 0.0
    avg_l = -gross_l / len(losses) if losses else 0.0
    pf = (gross_w / gross_l) if gross_l > 0 else None
    return {"n": n, "wins": len(wins), "win_rate": round(100.0 * len(wins) / n, 1) if n else None,
            "avg_win": round(avg_w, 4), "avg_loss": round(avg_l, 4),
            "expectancy": round(sum(t["pnl"] for t in trades) / n, 4) if n else None,
            "pnl": round(sum(t["pnl"] for t in trades), 2), "profit_factor": round(pf, 2) if pf is not None else None}


def group_by(trades, key):
    out = {}
    for t in trades:
        out.setdefault(t[key], []).append(t)
    return {k: stats(v) for k, v in out.items()}


def recommend_pauses(trades):
    """Wilson-aware: 'pause' only when the 95% upper bound of the win rate is below the break-even win rate."""
    by = {}
    for t in trades:
        by.setdefault(t["strategy"], []).append(t)
    pauses, watch = [], []
    for name, ts in by.items():
        s = stats(ts)
        if s["n"] < MIN_SAMPLE_SIZE or s["pnl"] >= 0 or (s["profit_factor"] or 0) >= 1:
            continue
        breakeven = (abs(s["avg_loss"]) / (s["avg_win"] + abs(s["avg_loss"]))) if (s["avg_win"] + abs(s["avg_loss"])) else 0.5
        lo, hi = wilson_interval(s["wins"], s["n"])
        row = {"strategy": name, **s, "breakeven_win_rate": round(100 * breakeven, 1),
               "win_rate_ci95": [round(100 * lo, 1), round(100 * hi, 1)]}
        (pauses if hi < breakeven else watch).append(row)
    key = lambda r: r["pnl"]
    return {"pause": sorted(pauses, key=key), "watch": sorted(watch, key=key),
            "insufficient_sample": sum(1 for ts in by.values() if len(ts) < MIN_SAMPLE_SIZE)}


def calibration(trades, cutoff=CALIBRATION_CUTOFF):
    cut = datetime.fromisoformat(cutoff).replace(tzinfo=timezone.utc)
    post = [t for t in trades if t["entry"] and t["entry"] >= cut and t["confidence"] is not None]
    if len(post) < MIN_CALIBRATION_TRADES:
        return {"cutoff": cutoff, "trades": len(post), "status": f"too few trades after {cutoff} ({len(post)} < {MIN_CALIBRATION_TRADES}) - no calibration claim"}
    rows = []
    for lo, hi in BUCKETS:
        b = [t for t in post if lo <= t["confidence"] < hi]
        if b:
            rows.append({"bucket": f"{lo}-{min(hi, 100)}", "n": len(b), "predicted_mean": round(sum(t["confidence"] for t in b) / len(b), 1),
                         "actual_win_rate": round(100.0 * sum(t["pnl"] > 0 for t in b) / len(b), 1)})
    pos = [t["confidence"] for t in post if t["pnl"] > 0]
    neg = [t["confidence"] for t in post if t["pnl"] <= 0]
    auc = None
    if pos and neg:
        auc = round(sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg)), 3)
    return {"cutoff": cutoff, "trades": len(post), "buckets": rows, "auc": auc, "status": "ok"}


def build(trades):
    return {"overall": stats(trades), "by_group": group_by(trades, "group"), "by_coin": group_by(trades, "symbol"),
            "by_strategy": group_by(trades, "strategy"), "calibration": calibration(trades),
            "recommendations": recommend_pauses(trades)}


def render_markdown(card, title="SINDHU weekly scorecard"):
    o = card["overall"]
    L = [f"# {title}", "", f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} (read-only; nothing is paused automatically).", "",
         f"**Overall:** {o['n']} closed trades, win rate {o['win_rate']}%, avg win {o['avg_win']}, avg loss {o['avg_loss']}, "
         f"expectancy {o['expectancy']}, profit factor {o['profit_factor']}, PnL {o['pnl']}.", "", "## By group", "",
         "| Group | Trades | Win % | Avg win | Avg loss | Expectancy | PF | PnL |", "|---|---|---|---|---|---|---|---|"]
    for k, s in sorted(card["by_group"].items()):
        L.append(f"| {k} | {s['n']} | {s['win_rate']} | {s['avg_win']} | {s['avg_loss']} | {s['expectancy']} | {s['profit_factor']} | {s['pnl']} |")
    for title2, key in (("Worst 8 coins", "by_coin"),):
        L += ["", f"## {title2}", "", "| Coin | Trades | Win % | PF | PnL |", "|---|---|---|---|---|"]
        for k, s in sorted(card[key].items(), key=lambda kv: kv[1]["pnl"])[:8]:
            L.append(f"| {k} | {s['n']} | {s['win_rate']} | {s['profit_factor']} | {s['pnl']} |")
    L += ["", "## Worst 10 strategies (any sample size)", "", "| Strategy | Trades | Win % | PF | PnL |", "|---|---|---|---|---|"]
    for k, s in sorted(card["by_strategy"].items(), key=lambda kv: kv[1]["pnl"])[:10]:
        L.append(f"| {k[:60]} | {s['n']} | {s['win_rate']} | {s['profit_factor']} | {s['pnl']} |")
    r = card["recommendations"]
    L += ["", f"## Recommended pauses (n >= {MIN_SAMPLE_SIZE}, win-rate 95% upper bound below break-even)", ""]
    L += ["| Strategy | Trades | Win % (95% CI) | Break-even win % | PF | PnL |", "|---|---|---|---|---|---|"]
    for x in r["pause"]:
        L.append(f"| {x['strategy'][:60]} | {x['n']} | {x['win_rate']} ({x['win_rate_ci95'][0]}-{x['win_rate_ci95'][1]}) | {x['breakeven_win_rate']} | {x['profit_factor']} | {x['pnl']} |")
    if not r["pause"]:
        L.append("| (none statistically conclusive) | | | | | |")
    L += ["", f"Watch-list (n >= {MIN_SAMPLE_SIZE}, losing, but not yet conclusive): {len(r['watch'])}. Strategies below {MIN_SAMPLE_SIZE} trades (no conclusion possible): {r['insufficient_sample']}.", ""]
    for x in r["watch"][:10]:
        L.append(f"- {x['strategy'][:60]}: {x['n']} trades, win {x['win_rate']}% (CI {x['win_rate_ci95'][0]}-{x['win_rate_ci95'][1]}), PF {x['profit_factor']}, PnL {x['pnl']}")
    c = card["calibration"]
    L += ["", f"## Confidence calibration (trades on/after {c['cutoff']} only)", "", c["status"]]
    if c.get("buckets"):
        L += ["", "| Confidence bucket | Trades | Predicted mean | Actual win % |", "|---|---|---|---|"]
        L += [f"| {b['bucket']} | {b['n']} | {b['predicted_mean']} | {b['actual_win_rate']} |" for b in c["buckets"]]
        L.append(f"\nAUC {c['auc']} (0.5 = no predictive value).")
    return "\n".join(L) + "\n"

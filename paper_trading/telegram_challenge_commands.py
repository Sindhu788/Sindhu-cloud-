"""Investigation Batch 2026-09-17, Parts 2-5: Telegram commands for the
multi-challenge system (paper_trading/challenge_multi.py, already built
for the dashboard's own Challenge Mode widget) -- /challenge,
/stopchallenge, /mychallenges, /report, /menu. Registered into
paper_trading.telegram_commands._COMMANDS by that module (see its own
import of this one), reusing its exact authorization/dispatch/reply
plumbing rather than a second, parallel command system.

Auto strategy selection (2.2) reuses challenge_analysis.recommend_paths()
verbatim -- the same real-history-ranked path list Level 2's dashboard
"Recommended Paths" view already shows, never a new selection heuristic.
"""

import re
from datetime import datetime, timezone

from data_engine import storage
from paper_trading import challenge_analysis, challenge_multi, telegram_bot

# 2.7: quick-start templates, exactly as specified.
TEMPLATES = {
    "conservative": {"start_amount": 50.0, "target_amount": 100.0, "days": 14.0, "name": None},
    "aggressive": {"start_amount": 20.0, "target_amount": 50.0, "days": 5.0, "name": None},
}

_TIME_RE = re.compile(r"^(\d+(?:\.\d+)?)(d|h|day|days|hour|hours)?$", re.IGNORECASE)


def _normalize_coin(token):
    token = token.strip().upper()
    return token if token.endswith("USDT") else f"{token}USDT"


def _parse_challenge_args(args):
    """Returns (parsed_dict, error_message). parsed_dict has start_amount,
    target_amount, days (float, fractional for an hours time limit),
    coins (list[str] or None), name (str or None)."""
    args = (args or "").strip()
    if not args:
        return None, None
    template = TEMPLATES.get(args.lower())
    if template:
        return dict(template, coins=None), None

    tokens = args.split()
    if len(tokens) < 3:
        return None, "Usage: /challenge <balance> <target> <days>d [coins=BTC,ETH] [name...]"
    try:
        start_amount = float(tokens[0])
        target_amount = float(tokens[1])
    except ValueError:
        return None, "Balance and target must be numbers, e.g. /challenge 50 100 14d"
    if start_amount <= 0:
        return None, "Initial balance must be positive."
    if target_amount <= start_amount:
        return None, "Target must be greater than the initial balance."

    m = _TIME_RE.match(tokens[2])
    if not m:
        return None, "Time limit must look like 14d (days) or 36h (hours), e.g. /challenge 50 100 14d"
    value = float(m.group(1))
    unit = (m.group(2) or "d").lower()
    days = value / 24.0 if unit.startswith("h") else value
    if days <= 0:
        return None, "Time limit must be positive."

    coins, name_parts = None, []
    for tok in tokens[3:]:
        if tok.lower().startswith("coins="):
            coins = [_normalize_coin(c) for c in tok[6:].split(",") if c.strip()]
        else:
            name_parts.append(tok)
    return {
        "start_amount": start_amount, "target_amount": target_amount, "days": days,
        "coins": coins or None, "name": " ".join(name_parts) or None,
    }, None


def _progress_bar(pct, width=10):
    pct = max(0.0, min(100.0, pct))
    filled = round(pct / 100.0 * width)
    return "[" + "█" * filled + "-" * (width - filled) + f"] {pct:.0f}%"


def _challenge_create_reply(args):
    parsed, error = _parse_challenge_args(args)
    if error:
        return error
    if parsed is None:
        return (
            "Usage: /challenge <balance> <target> <days>d [coins=BTC,ETH] [name]\n"
            "Or a template: /challenge conservative ($50->$100, 14 days) / /challenge aggressive ($20->$50, 5 days)"
        )

    start_amount, target_amount, days = parsed["start_amount"], parsed["target_amount"], parsed["days"]
    coins, name = parsed["coins"], parsed["name"]

    # 2.2: auto-select the best-matching real strategy+coin for THIS
    # target/timeframe -- reuses recommend_paths() exactly, no new logic.
    recommendation = challenge_analysis.recommend_paths(start_amount, target_amount, days, restrict_symbols=coins)
    # 2.12: never claim a (strategy, coin) another active challenge already owns.
    best = challenge_multi.find_non_conflicting_path(recommendation["paths"])

    scope_strategy_id = best["strategy_id"] if best else None
    scope_symbol = best["symbol"] if best else None
    try:
        challenge = challenge_multi.create_challenge(
            name, start_amount, target_amount, "custom", days=days,
            scope_strategy_id=scope_strategy_id, scope_symbol=scope_symbol,
            telegram_report_enabled=True,
        )
    except ValueError as e:
        return f"Could not create challenge: {e}"

    lines = [
        f"✅ Challenge created: \"{challenge['label'] or challenge['id']}\"",
        f"${start_amount:.2f} -> ${target_amount:.2f} in {days:.1f} days.",
    ]
    if best:
        lines.append(
            f"\U0001F916 Auto-selected strategy: {best['strategy_name']} on {best['symbol']} "
            f"(real win rate {best['win_rate_pct']:.1f}%, {best['sample_size']} closed trades). "
            f"Its signals will be marked ⚫ for this challenge."
        )
    else:
        lines.append(
            "⚠️ No single strategy+coin combination could be confidently recommended yet "
            "(not enough matching real history, or every good match is already claimed by another "
            "active challenge) -- tracking your WHOLE account's real progress toward this target instead."
        )
    # 2.11: honest, non-blocking realism warning.
    if not recommendation["any_achievable"]:
        fb = recommendation["fallback"]
        if fb:
            lines.append(
                f"⚠️ Based on real history, this target may not be realistic: the best demonstrated "
                f"real pace ({fb['based_on_strategy_name']} on {fb['based_on_symbol']}) would reach about "
                f"${fb['realistic_amount_in_same_days']:.2f} in {days:.0f} days instead"
                + (f", or take about {fb['days_needed_for_original_target']:.0f} days to reach your ${target_amount:.2f} target."
                   if fb.get("days_needed_for_original_target") else ".")
            )
        else:
            lines.append(
                "⚠️ Not enough real closed-trade history yet to judge whether this target is realistic."
            )
    lines.append(f"Challenge ID: {challenge['id']} (use /stopchallenge {challenge['id']} to end it early)")
    return "\n".join(lines)


def _stop_challenge_reply(args):
    challenge_id = (args or "").strip().split()[0] if (args or "").strip() else None
    if not challenge_id:
        return "Usage: /stopchallenge <challenge_id> -- see /mychallenges for the id."
    try:
        progress = challenge_multi.stop_challenge(challenge_id)
    except ValueError as e:
        return str(e)
    if progress is None:
        return f"Challenge {challenge_id} stopped. (No progress could be computed for its final state.)"
    return (
        f"\U0001F6D1 Challenge stopped: final result ${progress['current_amount']:.2f} of "
        f"${progress['target_amount']:.2f} target ({progress['progress_pct']:.1f}%). This is now final -- "
        f"see /report for history."
    )


def _resume_challenge_reply(args):
    challenge_id = (args or "").strip().split()[0] if (args or "").strip() else None
    if not challenge_id:
        return "Usage: /resumechallenge <challenge_id>"
    try:
        row = challenge_multi.resume_challenge(challenge_id)
    except ValueError as e:
        return str(e)
    return f"▶️ Challenge \"{row['label'] or row['id']}\" resumed."


def _challenge_line(row, progress):
    label = row["label"] or row["id"]
    if progress is None:
        return f"• {label} ({row['id']}) -- no progress data yet"
    paused_tag = " [PAUSED]" if row["paused"] else ""
    return (
        f"• {label}{paused_tag}: {_progress_bar(progress['progress_pct'])} "
        f"${progress['current_amount']:.2f}/${progress['target_amount']:.2f}, "
        f"{progress['remaining_days']:.1f}d left (id: {row['id']})"
    )


def _my_challenges_reply(args):
    rows = storage.list_challenges()
    if not rows:
        return "No active challenges. Start one with /challenge <balance> <target> <days>d, or /challenge conservative"
    lines = ["\U0001F3AF Active challenges:"]
    progresses = []
    for row in rows:
        progress = challenge_multi.compute_progress_for(row["id"])
        progresses.append((row, progress))
        lines.append(_challenge_line(row, progress))
    # 3.4: simple leaderboard when 2+ are active.
    ranked = [(r, p) for r, p in progresses if p is not None]
    if len(ranked) >= 2:
        ranked.sort(key=lambda rp: rp[1]["progress_pct"], reverse=True)
        lines.append("")
        lines.append("\U0001F3C6 Leaderboard (by % of target reached):")
        for i, (row, progress) in enumerate(ranked, 1):
            lines.append(f"{i}. {row['label'] or row['id']} -- {progress['progress_pct']:.1f}%")
    return "\n".join(lines)


def _report_reply(args):
    """3.1: a single organized message with clear sections (no stateful
    multi-step menu -- this bot has no per-chat conversation state; every
    command is a stand-alone real-content reply, same convention every
    other command here already follows)."""
    from paper_trading import telegram_analytics
    summary = telegram_analytics.status_summary()
    lines = ["\U0001F4CA <b>Report</b>", "", "<b>1) Total Trades</b>"]
    overall = summary["overall"]
    lines.append(f"• {overall['total_trades']} closed, win rate {overall['win_rate_pct']:.1f}%, PnL ${overall['total_pnl']:.2f}")
    lines.append("")
    lines.append("<b>2) Group Detail</b>")
    for key in ("profitable", "losing", "challenge"):
        g = summary["groups"][key]
        wr = f"{g['win_rate_pct']:.1f}%" if g["closed_trades"] else "-"
        lines.append(f"• {g['label']}: {g['closed_trades']} trades, win rate {wr}, PnL ${g['total_pnl']:.2f}")
    lines.append("")
    lines.append("<b>3) Challenges</b>")
    rows = storage.list_challenges()
    if not rows:
        lines.append("• None active -- start one with /challenge")
    else:
        for row in rows:
            progress = challenge_multi.compute_progress_for(row["id"])
            lines.append(_challenge_line(row, progress))
    return "\n".join(lines)


def _menu_reply(args):
    """5.1: every command and every marker, in one message, written for
    someone who has never used this bot before."""
    return (
        "\U0001F4D6 <b>SINDHU Telegram Bot -- Full Guide</b>\n\n"
        "<b>Commands</b>\n"
        "/status -- engine state, open trades, balance, kill switch / drawdown pause\n"
        "/pause -- stop the paper trading engine\n"
        "/resume -- start the paper trading engine\n"
        "/test -- send a fake sample signal to check formatting\n"
        "/challenge &lt;balance&gt; &lt;target&gt; &lt;days&gt;d [coins=BTC,ETH] [name] -- start a new challenge "
        "(or /challenge conservative / /challenge aggressive for a quick-start template)\n"
        "/stopchallenge &lt;id&gt; -- end a challenge early; the result at that moment is final\n"
        "/resumechallenge &lt;id&gt; -- continue a challenge that auto-paused after a balance drop\n"
        "/mychallenges -- quick list of every active challenge with progress bars and a leaderboard\n"
        "/report -- full report: total trades, group breakdown, and every active challenge\n"
        "/menu or /help -- this message\n\n"
        "<b>Signal markers</b>\n"
        "\U0001F535 Profitable group -- \U0001F534 Losing group (signals withheld from Telegram) -- "
        "\U0001F7E3 Challenge group -- \U000026AA Not yet classified -- "
        "\U000026AB Part of one of YOUR active /challenge challenges (shown alongside the group marker above, "
        "e.g. \U000026AB\U0001F535 means a Profitable-group strategy that's also currently running one of your challenges)"
    )


def send_lifecycle_event_messages(events):
    """Turns challenge_multi.sweep_challenge_lifecycle()'s detected state
    transitions into the real Telegram messages 2.5/2.6/2.13 ask for.
    Kept separate from the detection logic itself (sweep_challenge_
    lifecycle never sends anything) so the detection can be tested
    without a real/mocked network call every time."""
    for event in events:
        if event["kind"] == "completed":
            best = event.get("best_trade")
            worst = event.get("worst_trade")
            text = (
                f"\U0001F389 Challenge complete: \"{event['label'] or event['challenge_id']}\"!\n"
                f"${event['start_amount']:.2f} -> ${event['target_amount']:.2f}"
                + (f" in {event['days_taken']:.1f} days" if event["days_taken"] is not None else "") + ".\n"
                f"Signals used: {event['signals_used']}"
                + (f", profit factor: {event['profit_factor']:.2f}" if isinstance(event.get("profit_factor"), (int, float)) else "") + "\n"
                + (f"Best trade: {best['symbol']} +${best['pnl']:.2f}\n" if best else "")
                + (f"Worst trade: {worst['symbol']} ${worst['pnl']:.2f}\n" if worst else "")
            )
            telegram_bot._raw_send(text)
        elif event["kind"] == "failed":
            telegram_bot._raw_send(
                f"❌ Challenge failed -- \"{event['label'] or event['challenge_id']}\" reached "
                f"{event['progress_pct']:.1f}% (${event['current_amount']:.2f} of ${event['target_amount']:.2f}) "
                f"before its {event['days']}-day deadline. This is now final."
            )
        elif event["kind"] == "paused":
            telegram_bot._raw_send(
                f"⚠️ Challenge \"{event['label'] or event['challenge_id']}\" paused: balance dropped to "
                f"${event['current_amount']:.2f} (below {event['threshold_pct']:.0f}% of its ${event['start_amount']:.2f} "
                f"starting amount). Reply /resumechallenge {event['challenge_id']} to continue, or "
                f"/stopchallenge {event['challenge_id']} to end it here."
            )


COMMANDS = {
    "/challenge": _challenge_create_reply,
    "/stopchallenge": _stop_challenge_reply,
    "/resumechallenge": _resume_challenge_reply,
    "/mychallenges": _my_challenges_reply,
    "/report": _report_reply,
    "/menu": _menu_reply,
}

"""Phase 5 -- proving threshold, eligibility, and real-time forwarding.

Eligibility (per the CEO's own explicit decision): a channel must have
BOTH >= 30 closed trades in THIS module AND a genuinely positive total
PnL over those trades. Trade count alone is deliberately not enough.

PRIVACY: the forwarded message never contains the source channel's real
name/handle/link -- only its stable "Source A"/"Source B" label
(assigned once, in external_channels.forwarding_source_label, at channel-
creation time -- never regenerated, so it stays consistent for the CEO
over time).

FRESHNESS: reuses paper_trading.telegram_bot.freshness_check verbatim
(imported directly, not reimplemented) -- a stale copied signal is
withheld, never sent late.

Sending uses its OWN minimal Telegram HTTP call (external_signals'
own bot_token/channel_id from external_signals.config), deliberately NOT
paper_trading.telegram_bot._raw_send, so this module never depends on
paper_trading's settings/state for anything beyond the one explicitly
reused pure function above.
"""

import requests

from data_engine import storage
from external_signals import channel_stats, config as ext_config

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def is_channel_eligible_for_forwarding(channel_id):
    """Returns (eligible: bool, reason: str)."""
    report = channel_stats.channel_report(channel_id)
    if not report:
        return False, "Channel not found."
    settings = ext_config.load()
    required = settings.get("proving_trades_required", 30)
    if report["closed_trades"] < required:
        return False, f"Still proving itself -- {report['closed_trades']}/{required} closed trades."
    if settings.get("require_profitable_to_forward", True) and report["total_pnl"] <= 0:
        return False, f"Reached {required} trades but is not profitable overall (total PnL {report['total_pnl']}) -- not forwarded."
    return True, "Eligible -- proven sample size and profitable."


def _next_source_label():
    existing = {c["forwarding_source_label"] for c in storage.list_external_channels() if c["forwarding_source_label"]}
    letter_index = 0
    while True:
        label = f"Source {chr(ord('A') + letter_index)}"
        if label not in existing:
            return label
        letter_index += 1
        if letter_index > 25:
            return f"Source {letter_index}"  # 26+ channels -- extremely unlikely, but never crash


def format_forwarded_message(channel, signal, lang="ur"):
    """Emoji-led, short bullet lines, labeled fields -- the same
    scannable contract paper_trading's own signal messages follow (see
    tests/test_telegram_formatting_contract.py). NEVER includes the
    source channel's real name/handle/link -- only its stable label."""
    source_label = channel["forwarding_source_label"] or "Source ?"
    direction_word = {"ur": {"long": "LONG (Buy)", "short": "SHORT (Sell)"}}.get(lang, {}).get(
        signal["direction"], signal["direction"] or "-"
    )
    direction_emoji = "🟢" if signal["direction"] == "long" else "🔴"
    entries = signal["entries"] or []
    entry_line = ", ".join(str(e["price"]) for e in entries) if entries else "-"
    tp_line = ", ".join(str(t) for t in (signal["take_profit"] or [])) or "-"

    lines = [
        f"🚨 <b>Naya Signal — {source_label}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🪙 Coin: <b>{signal['symbol'] or '-'}</b>",
        f"{direction_emoji} Direction: <b>{direction_word}</b>",
        f"💰 {'Entries' if len(entries) > 1 else 'Entry'}: {entry_line}",
        f"🛑 Stop Loss: {signal['stop_loss'] if signal['stop_loss'] is not None else '-'}",
        f"🎯 Target: {tp_line}",
    ]
    if signal.get("leverage"):
        lines.append(f"⚙️ Leverage: {signal['leverage']}x")
    lines.append(f"📡 {source_label} -- proven external source")
    return "\n".join(lines)


def _raw_send(text, bot_token, channel_id, timeout=15):
    try:
        resp = requests.post(
            _TELEGRAM_API.format(token=bot_token),
            json={"chat_id": channel_id, "text": text, "parse_mode": "HTML"},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
        return True, None
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"


def forward_signal_if_eligible(channel_id, signal, entry_time_ms):
    """The single entry point called right after a NEW signal is parsed
    (Phase 5, item 3). Returns {"forwarded": bool, "reason": str}. Never
    raises. `entry_time_ms` is the signal's own real receipt time, used
    for the reused freshness gate -- never a fabricated/optimistic time."""
    eligible, reason = is_channel_eligible_for_forwarding(channel_id)
    if not eligible:
        return {"forwarded": False, "reason": reason}

    settings = ext_config.load()
    if not settings.get("forwarding_enabled", True):
        return {"forwarded": False, "reason": "Forwarding is turned off in settings."}
    bot_token, dest_channel_id = settings.get("forward_bot_token"), settings.get("forward_channel_id")
    if not bot_token or not dest_channel_id:
        return {"forwarded": False, "reason": "Forwarding bot token / destination channel not configured yet."}

    entries = signal.get("entries") or []
    if not entries:
        return {"forwarded": False, "reason": "No usable entry price to forward."}

    # Reused verbatim -- the exact same Signal Freshness Gate the user's
    # own paper-trading signals already go through, not a parallel
    # implementation with its own (possibly looser) timing rules.
    from paper_trading.telegram_bot import freshness_check
    from data_engine import config as data_config
    fake_position = {
        "entry_time": entry_time_ms, "entry_price": entries[0]["price"],
        "exchange": getattr(data_config, "DEFAULT_EXCHANGE", "binance"), "symbol": signal["symbol"],
    }
    fresh_ok, stale_reason, _live_price = freshness_check(fake_position)
    if not fresh_ok:
        return {"forwarded": False, "reason": f"Withheld -- {stale_reason}"}

    channel = storage.get_external_channel(channel_id)
    text = format_forwarded_message(channel, signal)
    ok, error = _raw_send(text, bot_token, dest_channel_id)
    return {"forwarded": ok, "reason": error or "Sent."}

"""Time-of-Day Trading Filter (Grand Feature Expansion, Phase 5 Feature 2):
blocks NEW paper-trading entries during a configured UTC hour window --
e.g. known-illiquid overnight hours a CEO has observed perform poorly.
Genuinely distinct from Phase 3's time_of_day_performance_breakdown
(storage.list_paper_hour_of_day_stats), which is a read-only stats query
never read by the trading loop.

Same overnight-wraparound window convention as Telegram's Silent Hours DND
(paper_trading.telegram_bot.is_within_silent_hours, Phase 2 Feature 24) --
kept as its own small, self-contained implementation rather than importing
from telegram_bot, since blocking a real trade is a materially different,
more consequential action than muting a notification sound and deserves
its own independent setting."""

from datetime import datetime, timezone

from paper_trading import config as pt_config


def _parse_hhmm(value):
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def is_blocked_now(now=None, settings=None):
    settings = settings if settings is not None else pt_config.load()
    if not settings.get("time_filter_enabled", False):
        return False
    now = now or datetime.now(timezone.utc)
    current = now.hour * 60 + now.minute
    try:
        start = _parse_hhmm(settings.get("time_filter_block_start_utc", "00:00"))
        end = _parse_hhmm(settings.get("time_filter_block_end_utc", "00:00"))
    except (ValueError, AttributeError):
        return False
    if start == end:
        return False  # zero-width window means "always off", not "always on"
    if start < end:
        return start <= current < end
    return current >= start or current < end  # overnight wraparound

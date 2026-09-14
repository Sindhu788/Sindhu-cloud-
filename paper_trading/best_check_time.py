"""Grand Master Batch, Phase 4 Item 9: "Best time to check dashboard" --
based on real historical signal-delivery timing, not a guess. Builds an
hour-of-day (UTC) histogram from every real, successfully-delivered
Telegram signal ever recorded, and names the busiest window(s).
"""

from collections import Counter
from datetime import datetime

from data_engine import storage

MIN_SIGNALS_FOR_A_SUGGESTION = 10


def best_check_times(top_n=3):
    """Returns {"has_enough_data": bool, "total_signals": int,
    "hourly_counts": [{"hour_utc": 0-23, "count": int}, ...] (all 24,
    zero-filled), "best_hours_utc": [...top_n busiest hours...]}.

    Below MIN_SIGNALS_FOR_A_SUGGESTION real signals, has_enough_data is
    False and best_hours_utc is empty -- never guesses a "best time" from
    a handful of data points that could just be noise."""
    timestamps = storage.list_successful_telegram_send_timestamps()
    hour_counts = Counter()
    for ts in timestamps:
        try:
            hour_counts[datetime.fromisoformat(ts).hour] += 1
        except (ValueError, TypeError):
            continue

    hourly = [{"hour_utc": h, "count": hour_counts.get(h, 0)} for h in range(24)]
    total = len(timestamps)
    has_enough_data = total >= MIN_SIGNALS_FOR_A_SUGGESTION

    best_hours = []
    if has_enough_data:
        ranked = sorted((h for h in hourly if h["count"] > 0), key=lambda h: h["count"], reverse=True)
        best_hours = [h["hour_utc"] for h in ranked[:top_n]]

    return {
        "has_enough_data": has_enough_data,
        "total_signals": total,
        "hourly_counts": hourly,
        "best_hours_utc": best_hours,
    }

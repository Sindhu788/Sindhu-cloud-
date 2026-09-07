"""Master 15-Item task, Item 7: Telegram Chart Attachment decision --
text sparkline (see paper_trading/sparkline.py's own docstring for why
a real chart image was rejected). Tests the pure sparkline generator
directly, then verifies it against REAL locally-downloaded candle data
for a real coin (not synthetic/mocked prices) to prove the end-to-end
wiring produces a real, sensible line for an actual signal."""
import pytest

from paper_trading.sparkline import make_sparkline
from paper_trading import telegram_bot


def test_rising_prices_produce_a_rising_sparkline():
    line = make_sparkline([1, 2, 3, 4, 5, 6, 7, 8])
    assert line[0] == "▁"
    assert line[-1] == "█"
    from paper_trading.sparkline import _BLOCKS
    levels = [_BLOCKS.index(c) for c in line]
    assert levels == sorted(levels), "a strictly increasing price series must produce a non-decreasing sparkline"


def test_falling_prices_produce_a_falling_sparkline():
    line = make_sparkline([8, 7, 6, 5, 4, 3, 2, 1])
    from paper_trading.sparkline import _BLOCKS
    levels = [_BLOCKS.index(c) for c in line]
    assert levels == sorted(levels, reverse=True)


def test_flat_prices_produce_a_flat_middle_line():
    line = make_sparkline([100.0] * 10)
    assert len(set(line)) == 1


def test_handles_none_values_and_short_series_without_raising():
    assert make_sparkline([])
    assert make_sparkline(None)
    assert make_sparkline([None, None])
    assert make_sparkline([5.0])
    assert len(make_sparkline([1.0, None, 3.0, None, 2.0])) == 3


def test_real_signal_end_to_end_with_real_local_candle_data():
    """Real evidence, not simulated: builds a full Telegram signal message
    for a real, currently-open (or the most recent) real paper-trading
    position if one exists locally, using REAL downloaded OHLCV data --
    confirms the sparkline line actually appears in the rendered message
    text when real candle history is available."""
    from data_engine import storage
    with storage.get_conn() as conn:
        row = conn.execute(
            "SELECT id, symbol, exchange, direction, strategy_id, strategy_name, entry_price, "
            "stop_loss, take_profit, entry_time, entry_reason FROM paper_positions "
            "WHERE symbol IS NOT NULL ORDER BY entry_time DESC LIMIT 1"
        ).fetchone()
    if not row:
        pytest.skip("no real paper_positions rows available locally to build a real signal message from")
    position = {
        "id": row[0], "symbol": row[1], "exchange": row[2], "direction": row[3],
        "strategy_id": row[4], "strategy_name": row[5], "entry_price": row[6],
        "stop_loss": row[7], "take_profit": row[8], "entry_time": row[9], "entry_reason": row[10],
    }
    sparkline = telegram_bot._recent_price_sparkline(position["exchange"], position["symbol"])
    if sparkline is None:
        pytest.skip(f"no real 1h candle history resampled yet for {position['symbol']} -- not a sparkline-code failure")
    assert len(sparkline) >= 2
    message = telegram_bot.format_signal_message(position, live_price=None, lang="en")
    assert sparkline in message
    assert "Last 24h:" in message

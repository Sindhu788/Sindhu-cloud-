"""Master 15-Item task, Item 7: Telegram Chart Attachment decision --
text sparkline (see paper_trading/sparkline.py's own docstring for why
a real chart image was rejected). Tests the pure sparkline generator
directly.

Grand Master Batch, Phase 2.4 removed the sparkline line from
format_signal_message's output entirely (message body is now exactly 5
fields) -- telegram_bot._recent_price_sparkline() is now dead code and
was deleted along with it, so the old end-to-end test that asserted the
sparkline appeared inside a real rendered message no longer applies.
make_sparkline() itself is untouched and still tested directly below."""

from paper_trading.sparkline import make_sparkline


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



import pandas as pd
import pytest

from backtest_engine.mtf_context import MultiTimeframeContext


@pytest.mark.parametrize("entry_unit,role_unit", [("ms", "ns"), ("ns", "ms"), ("us", "s")])
def test_mixed_timestamp_units_preserve_closed_bar_visibility(entry_unit, role_unit):
    entry_index = pd.date_range("2026-01-01", periods=9, freq="15min", tz="UTC").as_unit(entry_unit)
    role_index = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC").as_unit(role_unit)
    entry = pd.DataFrame({"close": range(9)}, index=entry_index)
    higher = pd.DataFrame({"close": [101., 202., 303.]}, index=role_index)
    roles = {"entry": "15m", "bias": "1h"}
    merged = MultiTimeframeContext.from_frames({"entry": entry, "bias": higher}, roles).build()
    assert merged.index.equals(entry_index.as_unit("ns"))
    assert merged.bias_close.iloc[:4].isna().all()
    assert merged.bias_close.iloc[4:8].tolist() == [101.] * 4
    assert merged.bias_close.iloc[8] == 202.
    prefix = MultiTimeframeContext.from_frames({"entry": entry.iloc[:7], "bias": higher.iloc[:2]}, roles).build()
    pd.testing.assert_frame_equal(merged.iloc[:7], prefix)
    assert entry.index.unit == entry_unit and higher.index.unit == role_unit

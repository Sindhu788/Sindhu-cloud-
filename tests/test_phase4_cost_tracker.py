"""Grand Master Batch, Phase 4 Item 6 -- Cost of Running This System tracker."""

import pytest

from data_engine import config as base_config
from paper_trading import cost_tracker


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_starts_empty():
    result = cost_tracker.summary()
    assert result["items"] == []
    assert result["monthly_total_usd"] == 0
    assert result["yearly_total_usd"] == 0


def test_add_monthly_cost_contributes_full_amount():
    cost_tracker.add_cost("Render hosting", 7.0, "monthly")
    result = cost_tracker.summary()
    assert result["monthly_total_usd"] == 7.0
    assert result["yearly_total_usd"] == 84.0


def test_add_yearly_cost_is_converted_to_monthly_equivalent():
    cost_tracker.add_cost("Domain name", 12.0, "yearly")
    result = cost_tracker.summary()
    assert result["monthly_total_usd"] == 1.0


def test_one_time_cost_excluded_from_recurring_total_but_tracked_separately():
    cost_tracker.add_cost("One-off API credit purchase", 50.0, "one_time")
    result = cost_tracker.summary()
    assert result["monthly_total_usd"] == 0
    assert result["one_time_total_usd"] == 50.0
    assert len(result["items"]) == 1


def test_remove_cost():
    item = cost_tracker.add_cost("Test", 5.0, "monthly")
    assert cost_tracker.remove_cost(item["id"]) is True
    assert cost_tracker.list_costs() == []


def test_remove_nonexistent_cost_returns_false():
    assert cost_tracker.remove_cost("does-not-exist") is False


def test_rejects_negative_amount():
    with pytest.raises(ValueError):
        cost_tracker.add_cost("Bad", -5.0, "monthly")


def test_rejects_invalid_period():
    with pytest.raises(ValueError):
        cost_tracker.add_cost("Bad", 5.0, "daily")


def test_persists_across_reload():
    cost_tracker.add_cost("Render hosting", 7.0, "monthly")
    cost_tracker.add_cost("AI provider", 20.0, "monthly")
    items = cost_tracker.list_costs()
    assert len(items) == 2
    assert cost_tracker.summary()["monthly_total_usd"] == 27.0

"""Grand Feature Expansion, Phase 6 Feature 13: Automated Weekly Strategy
Review (evolution_engine/weekly_review.py) -- a scheduled digest of
evolution/tuning activity, distinct from paper_trading.weekly_report and
paper_trading.monthly_report (trading performance only). Mirrors
weekly_report.py's own generate/gate/scheduler/Telegram-send shape.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, feature_toggles, storage
from evolution_engine import generation_manager, weekly_review


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


def test_generate_with_no_activity_says_nothing_evolved(test_db):
    result = weekly_review.generate_weekly_review()
    assert "Nothing evolved this week" in result["report_text"]
    assert result["report_data"]["generations_created"] == 0


def test_generate_reports_a_finalized_improvement(test_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    base_id = "lineage1"
    generation_manager.create_new_strategy_lineage(
        "Gen1", CONFIG, ["trend"], "sindhu_deterministic", False, "seed", now_iso, base_id=base_id,
    )
    child_id = generation_manager.create_next_strategy_generation(
        base_id, "Gen2", CONFIG, ["trend"], "sindhu_deterministic", False, "tuned", now_iso,
    )
    comp_id = storage.create_evolution_comparison(base_id, base_id, child_id, 100, {"win_rate": 40.0}, now_iso)
    storage.finalize_evolution_comparison(comp_id, {"win_rate": 70.0}, "improved", False, now_iso)

    result = weekly_review.generate_weekly_review()
    assert "1 improved" in result["report_text"]
    assert result["report_data"]["improved"] == 1


def test_generate_persists_a_permanent_row(test_db):
    weekly_review.generate_weekly_review()
    reports = storage.list_evolution_weekly_reports()
    assert len(reports) == 1


def test_maybe_generate_respects_the_7_day_gate(test_db):
    first = weekly_review.maybe_generate_weekly_review()
    assert first is not None
    second = weekly_review.maybe_generate_weekly_review()
    assert second is None  # too soon -- gate still active
    assert len(storage.list_evolution_weekly_reports()) == 1


def test_maybe_generate_returns_none_when_disabled(test_db):
    feature_toggles.set_toggle("evolution_weekly_review_enabled", False)
    result = weekly_review.maybe_generate_weekly_review()
    assert result is None
    assert storage.list_evolution_weekly_reports() == []


def test_gate_reopens_after_7_days(test_db, monkeypatch):
    weekly_review.generate_weekly_review()
    old_created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with storage.get_conn() as conn:
        conn.execute("UPDATE evolution_weekly_reports SET created_at=?", (old_created_at,))
    result = weekly_review.maybe_generate_weekly_review()
    assert result is not None
    assert len(storage.list_evolution_weekly_reports()) == 2


def test_endpoint_lists_reports(test_db):
    from sindhu_web.api.evolution import get_evolution_weekly_reviews

    weekly_review.generate_weekly_review()
    result = get_evolution_weekly_reviews()
    assert len(result["reports"]) == 1


def test_endpoint_generate_now_bypasses_the_gate(test_db):
    from sindhu_web.api.evolution import generate_evolution_weekly_review_now

    weekly_review.generate_weekly_review()
    generate_evolution_weekly_review_now()
    assert len(storage.list_evolution_weekly_reports()) == 2

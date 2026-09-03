"""Grand Feature Expansion, Phase 4 Feature 25: Custom Alert Rules
(paper_trading/custom_alerts.py) -- a user-DEFINED "alert me if X happens"
mechanism, distinct from every other alert in this system (all
system-generated). Deliberately bounded to a fixed, validated set of
metrics -- never an arbitrary user expression.
"""

from datetime import datetime, timezone, timedelta

import pytest

from data_engine import config as base_config, storage
from paper_trading import custom_alerts


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _close(position_id, pnl, strategy_id="strat1", days_ago=0):
    created_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    storage.open_paper_position({
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": created_at,
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(position_id, 100.0 + pnl, 1700000100000, pnl, pnl,
                                  "take_profit" if pnl >= 0 else "stop_loss", {}, {}, created_at,
                                  book_key=strategy_id)


def test_create_rule_rejects_an_unknown_metric(test_db):
    with pytest.raises(ValueError):
        custom_alerts.create_rule("bad", "not_a_real_metric", "below", 0.0, strategy_id="strat1")


def test_create_rule_rejects_an_unknown_comparison(test_db):
    with pytest.raises(ValueError):
        custom_alerts.create_rule("bad", "strategy_pnl", "sideways", 0.0, strategy_id="strat1")


def test_a_strategy_scoped_metric_requires_a_strategy_id(test_db):
    with pytest.raises(ValueError):
        custom_alerts.create_rule("bad", "strategy_pnl", "below", 0.0, strategy_id=None)


def test_account_wide_metric_does_not_require_a_strategy_id(test_db):
    rule_id = custom_alerts.create_rule("acct dd", "account_drawdown_pct", "above", 15.0)
    assert rule_id


def test_pnl_rule_triggers_when_the_real_pnl_breaches_the_threshold(test_db):
    custom_alerts.create_rule("pnl drop", "strategy_pnl", "below", 0.0, strategy_id="strat1")
    _close("p1", pnl=-50.0)
    triggered = custom_alerts.sweep_custom_alert_rules()
    assert len(triggered) == 1
    alerts = [a for a in storage.list_paper_alerts() if a["alert_type"] == "custom_rule"]
    assert len(alerts) == 1
    assert "strategy_pnl" in alerts[0]["message"]


def test_win_rate_rule_does_not_trigger_with_no_closed_trades_yet(test_db):
    """Honest degradation -- never fabricates a 0% or 100% win rate from
    zero data."""
    custom_alerts.create_rule("low win rate", "strategy_win_rate", "below", 50.0, strategy_id="strat1")
    triggered = custom_alerts.sweep_custom_alert_rules()
    assert triggered == []


def test_consecutive_losses_rule_triggers(test_db):
    custom_alerts.create_rule("losing streak", "consecutive_losses", "above", 2.0, strategy_id="strat1")
    _close("p1", pnl=-10.0, days_ago=3)
    _close("p2", pnl=-10.0, days_ago=2)
    _close("p3", pnl=-10.0, days_ago=1)
    triggered = custom_alerts.sweep_custom_alert_rules()
    assert len(triggered) == 1


def test_a_disabled_rule_is_never_evaluated(test_db):
    rule_id = custom_alerts.create_rule("pnl drop", "strategy_pnl", "below", 0.0, strategy_id="strat1")
    custom_alerts.set_rule_enabled(rule_id, False)
    _close("p1", pnl=-50.0)
    triggered = custom_alerts.sweep_custom_alert_rules()
    assert triggered == []


def test_a_rule_does_not_re_trigger_within_the_recheck_window(test_db):
    custom_alerts.create_rule("pnl drop", "strategy_pnl", "below", 0.0, strategy_id="strat1")
    _close("p1", pnl=-50.0)
    first = custom_alerts.sweep_custom_alert_rules()
    second = custom_alerts.sweep_custom_alert_rules()
    assert len(first) == 1
    assert second == []


def test_delete_rule_removes_it(test_db):
    rule_id = custom_alerts.create_rule("pnl drop", "strategy_pnl", "below", 0.0, strategy_id="strat1")
    custom_alerts.delete_rule(rule_id)
    assert custom_alerts.list_rules() == []


def test_a_rule_scoped_to_one_strategy_never_fires_from_another_strategys_data(test_db):
    custom_alerts.create_rule("pnl drop", "strategy_pnl", "below", 0.0, strategy_id="strat1")
    _close("p1", pnl=-50.0, strategy_id="strat2")  # a different strategy's loss
    triggered = custom_alerts.sweep_custom_alert_rules()
    assert triggered == []

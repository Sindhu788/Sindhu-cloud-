"""Grand Feature Expansion, Phase 4 Feature 4: Auto-Retirement Suggestion
(paper_trading/graveyard.py's compute_retirement_suggestions) -- surfaces
buried-but-still-active strategies so a human can approve archiving them.
Burial itself (bury_if_abandoned) never touches meta["archived"]; this is
purely the human-approval surfacing layer on top of that existing record.
"""

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import storage
from paper_trading import graveyard


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    yield


def _config(name):
    return StrategyConfig(
        name=name,
        timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[
            Condition(type="price_compare", op=">", indicator="sma", params={"period": 3}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


def test_empty_graveyard_yields_no_suggestions(test_db):
    assert graveyard.compute_retirement_suggestions() == []


def test_buried_and_still_active_strategy_is_suggested(test_db):
    sid = lib.create(_config("Buried Still Active"))
    storage.bury_strategy(sid, "Buried Still Active", "repeated_drawdown_pause",
                           "reached 12 consecutive losses", ["fvg"], "2026-09-01T00:00:00+00:00")
    suggestions = graveyard.compute_retirement_suggestions()
    assert len(suggestions) == 1
    assert suggestions[0]["strategy_id"] == sid
    assert suggestions[0]["strategy_name"] == "Buried Still Active"
    assert suggestions[0]["reason"] == "reached 12 consecutive losses"
    assert suggestions[0]["buried_at"] == "2026-09-01T00:00:00+00:00"


def test_already_archived_strategy_is_excluded(test_db):
    sid = lib.create(_config("Buried And Archived"))
    lib.set_archived(sid, True)
    storage.bury_strategy(sid, "Buried And Archived", "repeated_drawdown_pause",
                           "reached 15 consecutive losses", [], "2026-09-01T00:00:00+00:00")
    assert graveyard.compute_retirement_suggestions() == []


def test_strategy_no_longer_in_library_is_excluded(test_db):
    storage.bury_strategy("ghost-id", "Deleted Strategy", "repeated_drawdown_pause",
                           "reached 20 consecutive losses", [], "2026-09-01T00:00:00+00:00")
    assert graveyard.compute_retirement_suggestions() == []


def test_endpoint_returns_suggestions(test_db):
    from sindhu_web.api.paper_trading import get_retirement_suggestions

    sid = lib.create(_config("Via Endpoint"))
    storage.bury_strategy(sid, "Via Endpoint", "repeated_drawdown_pause",
                           "reached 11 consecutive losses", [], "2026-09-01T00:00:00+00:00")
    result = get_retirement_suggestions()
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["strategy_name"] == "Via Endpoint"

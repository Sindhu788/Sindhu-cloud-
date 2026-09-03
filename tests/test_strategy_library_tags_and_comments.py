"""Grand Feature Expansion, Phase 4 Features 3, 9, 10: Strategy Tagging
System, Strategy Comments/Notes, and Last-Changed Timestamp
(backtest_engine/strategy_library.py + sindhu_web/api/backtesting.py).

set_tags() and updated_at already existed in the backend before this
feature (confirmed via the Phase 4 audit) but had no endpoint/UI ever
using them -- these tests cover the NEW endpoint wiring
(set_strategy_tags/set_strategy_comment) plus the genuinely new
set_comment() function.
"""

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from sindhu_web.api.backtesting import (
    CommentRequest, TagsRequest, set_strategy_comment, set_strategy_tags,
)


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    yield


def _config(name="Test Strategy"):
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


def test_new_strategy_has_no_tags_or_comment_by_default():
    sid = lib.create(_config())
    meta = lib._read_meta(sid)
    assert meta["tags"] == []
    assert meta.get("ceo_comment", "") == ""


def test_set_tags_persists_and_is_searchable():
    sid = lib.create(_config())
    lib.set_tags(sid, ["swing", "high-risk"])
    meta = lib._read_meta(sid)
    assert meta["tags"] == ["swing", "high-risk"]
    assert lib.search(tag="high-risk")[0]["id"] == sid


def test_set_comment_persists():
    sid = lib.create(_config())
    lib.set_comment(sid, "Works best in trending markets.")
    meta = lib._read_meta(sid)
    assert meta["ceo_comment"] == "Works best in trending markets."


def test_set_comment_never_collides_with_clarification_notes():
    """set_clarification's own 'notes' list is a DIFFERENT, system-managed
    field (meta['clarification']['notes']) -- set_comment must never touch it."""
    sid = lib.create(_config())
    lib.set_clarification(sid, {"notes": ["auto note"], "hidden_rules": [], "confidence_pct": 50.0, "updated_at": "2026-01-01T00:00:00+00:00"})
    lib.set_comment(sid, "my own note")
    meta = lib._read_meta(sid)
    assert meta["clarification"]["notes"] == ["auto note"]
    assert meta["ceo_comment"] == "my own note"


def test_set_tags_and_set_comment_update_the_last_changed_timestamp():
    sid = lib.create(_config())
    original_updated_at = lib._read_meta(sid)["updated_at"]
    lib.set_tags(sid, ["new-tag"])
    assert lib._read_meta(sid)["updated_at"] >= original_updated_at


def test_tags_endpoint_strips_blanks_and_whitespace():
    sid = lib.create(_config())
    result = set_strategy_tags(sid, TagsRequest(tags=["  swing  ", "", "high-risk", "  "]))
    assert result["tags"] == ["swing", "high-risk"]
    assert lib._read_meta(sid)["tags"] == ["swing", "high-risk"]


def test_tags_endpoint_can_clear_all_tags():
    sid = lib.create(_config())
    lib.set_tags(sid, ["a", "b"])
    set_strategy_tags(sid, TagsRequest(tags=[]))
    assert lib._read_meta(sid)["tags"] == []


def test_comment_endpoint_sets_and_clears():
    sid = lib.create(_config())
    set_strategy_comment(sid, CommentRequest(comment="a real note"))
    assert lib._read_meta(sid)["ceo_comment"] == "a real note"
    set_strategy_comment(sid, CommentRequest(comment=""))
    assert lib._read_meta(sid)["ceo_comment"] == ""


def test_list_all_exposes_updated_at_and_ceo_comment_and_tags():
    sid = lib.create(_config())
    lib.set_tags(sid, ["swing"])
    lib.set_comment(sid, "a note")
    meta = next(m for m in lib.list_all() if m["id"] == sid)
    assert meta["tags"] == ["swing"]
    assert meta["ceo_comment"] == "a note"
    assert "updated_at" in meta

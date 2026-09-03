"""Grand Feature Expansion, Phase 5 Feature 1: Coin Blacklist
(paper_trading/coin_blacklist.py) -- a genuine deny-list, distinct from
coin_filter.py's shortlist() (a top-N ALLOWLIST/ranker, never an exclude
mechanism). Filtered out BEFORE coin_filter.shortlist() ever scores/ranks
a symbol, so a blacklisted coin can never be traded regardless of how
strong its activity score would otherwise be.
"""

import pytest

from data_engine import storage
from paper_trading import coin_blacklist


def test_empty_blacklist_filters_nothing(test_db):
    assert coin_blacklist.filter_out_blacklisted(["BTCUSDT", "ETHUSDT"]) == ["BTCUSDT", "ETHUSDT"]


def test_add_and_list(test_db):
    coin_blacklist.add("dogeusdt", reason="too erratic")
    entries = coin_blacklist.list_all()
    assert len(entries) == 1
    assert entries[0]["symbol"] == "DOGEUSDT"
    assert entries[0]["reason"] == "too erratic"


def test_blacklisted_symbol_is_filtered_out(test_db):
    coin_blacklist.add("DOGEUSDT")
    filtered = coin_blacklist.filter_out_blacklisted(["BTCUSDT", "DOGEUSDT", "ETHUSDT"])
    assert filtered == ["BTCUSDT", "ETHUSDT"]


def test_remove_restores_the_symbol(test_db):
    coin_blacklist.add("DOGEUSDT")
    coin_blacklist.remove("dogeusdt")
    assert coin_blacklist.list_all() == []
    assert coin_blacklist.filter_out_blacklisted(["DOGEUSDT"]) == ["DOGEUSDT"]


def test_adding_twice_does_not_duplicate(test_db):
    coin_blacklist.add("DOGEUSDT", reason="first reason")
    coin_blacklist.add("DOGEUSDT", reason="updated reason")
    entries = coin_blacklist.list_all()
    assert len(entries) == 1
    assert entries[0]["reason"] == "updated reason"


def test_engine_never_offers_a_blacklisted_symbol_to_coin_filter(test_db, monkeypatch):
    from paper_trading import engine as engine_mod

    coin_blacklist.add("DOGEUSDT")
    captured = {}

    def fake_shortlist(exchange, symbols, top_n, log=None):
        captured["symbols"] = symbols
        return []

    monkeypatch.setattr(engine_mod, "LIVE_CANDLES_ONLY", False)
    monkeypatch.setattr(engine_mod.coin_filter, "shortlist", fake_shortlist)
    monkeypatch.setattr(engine_mod.storage, "load_symbols", lambda exchange: ["BTCUSDT", "DOGEUSDT", "ETHUSDT"])
    monkeypatch.setattr(engine_mod, "get_exchange_client", lambda exchange: object())

    eng = engine_mod.PaperTradingEngine()
    eng._tick()
    assert "DOGEUSDT" not in captured["symbols"]
    assert captured["symbols"] == ["BTCUSDT", "ETHUSDT"]


def test_endpoint_add_list_remove(test_db):
    from sindhu_web.api.paper_trading import (
        CoinBlacklistRequest, add_coin_blacklist, get_coin_blacklist, remove_coin_blacklist,
    )

    add_coin_blacklist(CoinBlacklistRequest(symbol="dogeusdt", reason="testing"))
    result = get_coin_blacklist()
    assert len(result["blacklist"]) == 1
    assert result["blacklist"][0]["symbol"] == "DOGEUSDT"

    remove_coin_blacklist("DOGEUSDT")
    assert get_coin_blacklist()["blacklist"] == []


def test_endpoint_rejects_empty_symbol(test_db):
    from fastapi import HTTPException
    from sindhu_web.api.paper_trading import CoinBlacklistRequest, add_coin_blacklist

    with pytest.raises(HTTPException):
        add_coin_blacklist(CoinBlacklistRequest(symbol="   "))

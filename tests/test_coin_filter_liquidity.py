import pandas as pd

from paper_trading import coin_filter, config as pt_config


def _fake_scores(monkeypatch, table):
    monkeypatch.setattr(coin_filter, "_coin_activity_score", lambda ex, sym: table[sym])


def _row(sym, turnover, volume, vol, trend):
    return {"symbol": sym, "volume": volume, "turnover": turnover, "volatility_pct": vol, "trend_strength_pct": trend, "last_close_time": 1}


def test_liquidity_mode_picks_the_highest_usd_turnover_not_the_most_volatile(monkeypatch):
    table = {
        "BTC/USDT": _row("BTC/USDT", 9e9, 100, 0.2, 0.1),
        "ETH/USDT": _row("ETH/USDT", 5e9, 2000, 0.3, 0.1),
        "WLFI/USDT": _row("WLFI/USDT", 1e7, 5e8, 5.0, 4.0),     # huge base volume, tiny USD, very volatile
        "LIT/USDT": _row("LIT/USDT", 2e6, 9e8, 6.0, 5.0),
    }
    _fake_scores(monkeypatch, table)
    activity = [s["symbol"] for s in coin_filter.shortlist("x", list(table), 2, log=lambda m: None)]
    liquid = [s["symbol"] for s in coin_filter.shortlist("x", list(table), 2, log=lambda m: None, mode="liquidity")]
    assert set(activity) == {"WLFI/USDT", "LIT/USDT"}          # default behaviour unchanged (the Cloud bug-prone picks)
    assert liquid == ["BTC/USDT", "ETH/USDT"]


def test_config_accepts_only_known_modes():
    assert pt_config.defaults()["coin_filter_mode"] == "activity"
    assert "coin_filter_mode" in pt_config.validate_update({"coin_filter_mode": "bogus"})
    assert "coin_filter_mode" not in pt_config.validate_update({"coin_filter_mode": "liquidity"})

import types

from paper_trading import research_only as ro
from paper_trading import signal_generator


def test_off_by_default():
    assert ro.research_only_timeframes({}) == set()
    assert ro.is_research_only("1m", env={}) is False
    assert ro.is_research_only(None, env={"SINDHU_RESEARCH_ONLY_TIMEFRAMES": "1m"}) is False


def test_parsing_is_case_and_space_tolerant():
    env = {"SINDHU_RESEARCH_ONLY_TIMEFRAMES": " 1M, 3m ,,"}
    assert ro.research_only_timeframes(env) == {"1m", "3m"}
    assert ro.is_research_only("1m", env) and ro.is_research_only("3M", env)
    assert not ro.is_research_only("5m", env) and not ro.is_research_only("1h", env)


def _strategy(entry_tf):
    return {"config": types.SimpleNamespace(timeframes={"entry": entry_tf})}


def test_signal_generator_skips_listed_timeframes_without_loading_any_candles(monkeypatch):
    built = []

    def fake_ctx(exchange, symbol, tfs, start_ms=None):
        built.append(tfs["entry"])
        raise ValueError("stop here")                     # the loop 'continue's on this, nothing else runs

    monkeypatch.setattr(signal_generator, "MultiTimeframeContext", fake_ctx)
    strategies = [_strategy("1m"), _strategy("15m"), _strategy("3m")]
    monkeypatch.delenv("SINDHU_RESEARCH_ONLY_TIMEFRAMES", raising=False)
    signal_generator.strategy_candidates("okx", "BTC/USDT", strategies, [], {})
    assert built == ["1m", "15m", "3m"]                   # flag OFF: every strategy is evaluated
    built.clear()
    monkeypatch.setenv("SINDHU_RESEARCH_ONLY_TIMEFRAMES", "1m,3m")
    signal_generator.strategy_candidates("okx", "BTC/USDT", strategies, [], {})
    assert built == ["15m"]                                # flag ON: 1m and 3m never even build their context

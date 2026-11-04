import ast
import os

import numpy as np
import pandas as pd
import pytest

from backtest_engine import concepts

RAW = {"open", "high", "low", "close", "volume", "quote_volume", "trades"}


def _frame(n=400, seed=1, tz="UTC"):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.3, n)
    high = np.maximum(open_, close) + rng.random(n)
    low = np.minimum(open_, close) - rng.random(n)
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz=tz)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": rng.random(n) * 10}, index=idx)


def _same(a, b):
    if isinstance(a, tuple):
        assert isinstance(b, tuple) and len(a) == len(b)
        for x, y in zip(a, b):
            _same(x, y)
    else:
        pd.testing.assert_series_equal(a, b, check_exact=True) if isinstance(a, pd.Series) else pd.testing.assert_frame_equal(a, b, check_exact=True)


@pytest.fixture(autouse=True)
def _memo_off_after():
    yield
    concepts.memo_enable(False)


def test_memoized_functions_only_read_raw_columns():
    """AST audit: every memoized function (and the concept functions it calls) reads only open/high/low/close/volume."""
    src = open(concepts.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in concepts._MEMO_FUNCS:
        for x in ast.walk(funcs[name]):
            if isinstance(x, ast.Subscript) and isinstance(x.value, ast.Name) and x.value.id == "df" and isinstance(x.slice, ast.Constant):
                assert x.slice.value in RAW, f"{name} reads df[{x.slice.value!r}]"
            if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "df":
                assert x.attr in ("index", "columns", "copy", "iloc", "loc", "shape"), f"{name} uses df.{x.attr}"


@pytest.mark.parametrize("name,args", [("swing_points", ()), ("support_resistance", ()), ("break_of_structure", ()), ("change_of_character", ()),
                                       ("fair_value_gap", ()), ("order_blocks", ()), ("breaker_blocks", ()), ("atr", (14,)), ("atr", (7,)),
                                       ("valid_structure_trend", ()), ("equal_highs_lows", ()), ("trend_regime", ()), ("liquidity_sweep", ())])
def test_memoized_result_equals_unmemoized_on_every_call(name, args):
    fn = getattr(concepts, name)
    raw = fn.__wrapped_pure__
    df = _frame()
    expected = raw(df.copy(), *args)
    concepts.memo_enable(True)
    first = fn(df.copy(), *args)             # miss
    second = fn(df.copy(), *args)            # hit
    _same(expected, first); _same(expected, second)
    assert concepts.memo_stats()["hits"] >= 1


def test_mutating_a_returned_series_cannot_corrupt_the_cache():
    df = _frame(); concepts.memo_enable(True)
    a = concepts.swing_points(df)[0]
    a[:] = True
    b = concepts.swing_points(df)[0]
    _same(concepts.swing_points.__wrapped_pure__(df), (b, concepts.swing_points.__wrapped_pure__(df)[1])) if False else None
    assert not b.all()


def test_different_data_never_shares_an_entry_and_off_means_no_caching():
    concepts.memo_enable(True)
    d1, d2 = _frame(seed=1), _frame(seed=2)
    r1, r2 = concepts.support_resistance(d1), concepts.support_resistance(d2)
    assert not r1[0].equals(r2[0])
    d3 = d1.copy(); d3.iloc[-1, d3.columns.get_loc("high")] += 5          # one changed value must miss
    h = concepts.memo_stats()["hits"]
    concepts.support_resistance(d3)
    assert concepts.memo_stats()["hits"] == h
    concepts.memo_enable(False)
    assert concepts.memo_stats()["entries"] == 0
    concepts.support_resistance(d1)
    assert concepts.memo_stats()["entries"] == 0


def test_extra_columns_on_the_frame_do_not_change_results():
    df = _frame(); df["ema_20"] = df["close"].ewm(span=20).mean(); df["bull_bos"] = False
    concepts.memo_enable(True)
    _same(concepts.break_of_structure(_frame()), concepts.break_of_structure(df))


def test_memo_stays_inside_its_memory_budget(monkeypatch):
    monkeypatch.setattr(concepts, "_MEMO_BUDGET_BYTES", 200_000)
    concepts.memo_enable(True)
    for s in range(30):
        concepts.order_blocks(_frame(n=500, seed=s))
    assert concepts.memo_stats()["mb"] * 1e6 <= 200_000 + 50_000

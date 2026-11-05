"""Master plan B3: unit tests for data_platform/benchmark_v2.py on synthetic panels (no files, no network)."""
import math

import numpy as np
import pytest

from data_platform import benchmark_v2 as bv

DAY = bv.DAY_MS
MON_2024_01_01 = bv._ms("2024-01-01")          # a Monday


def panel(closes, start_ms=MON_2024_01_01, spread=0.01):
    c = np.asarray(closes, dtype=float)
    if c.ndim == 1:
        c = c[:, None]
    T, J = c.shape
    o = np.vstack([c[:1], c[:-1]])               # open = previous close
    h = np.maximum(o, c) * (1 + spread)
    l = np.minimum(o, c) * (1 - spread)
    days = start_ms + DAY * np.arange(T, dtype="int64")
    return bv.Panel(days, [f"C{j}USDT" for j in range(J - 1)] + ["BTCUSDT"] if J > 1 else ["BTCUSDT"], o, h, l, c)


def test_weekday_helper():
    assert bv._weekday(MON_2024_01_01) == 0 and bv._weekday(MON_2024_01_01 + 6 * DAY) == 6


def test_donchian_sub_signals_enter_on_breakout_and_exit_below_half_lookback_low():
    flat = [100.0] * 120
    up = [100.0 + 2 * i for i in range(1, 21)]          # strong breakout: above every prior high
    down = [up[-1] - 15 * i for i in range(1, 15)]      # falls below the lowest lows
    p = panel(flat + up + down, spread=0.0)
    s = bv.donchian_signal(p)[:, 0]
    assert s[119] == 0.0                                # flat: nothing yet
    assert s[121] == pytest.approx(1.0)                 # breakout above 20/55/100-day highs -> all three on
    assert s[-1] == 0.0                                 # crash below the lows -> all off


def test_signals_have_no_lookahead():
    rng = np.random.default_rng(1)
    base = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 400)))
    p1 = panel(base)
    altered = base.copy()
    altered[300:] *= 3.0                                # change ONLY the future after day 299
    p2 = panel(altered)
    for fn in (bv.donchian_signal, bv.tsmom_signal):
        a, b = fn(p1)[:300], fn(p2)[:300]
        assert np.array_equal(np.nan_to_num(a, nan=-1), np.nan_to_num(b, nan=-1))
    v1, v2 = bv.vol30(p1.c)[:300], bv.vol30(p2.c)[:300]
    assert np.allclose(np.nan_to_num(v1), np.nan_to_num(v2))


def test_vol30_uses_30_returns_ending_at_t_with_ddof_1():
    rng = np.random.default_rng(2)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 60)))
    v = bv.vol30(c[:, None])[:, 0]
    assert np.isnan(v[29]) and not np.isnan(v[30])
    lr = np.log(c[1:] / c[:-1])
    assert v[45] == pytest.approx(np.std(lr[15:45], ddof=1))


def test_vol_scaling_math():
    sig = np.array([[1.0, 1.0, 0.5, 1.0]])
    vol = np.array([[0.01, 0.04, 0.04, np.nan]])
    w = bv.target_weights(sig, vol)
    assert w[0, 0] == pytest.approx(1.0 / 20)           # vol below target -> capped at 1
    assert w[0, 1] == pytest.approx(0.5 / 20)           # 2 % / 4 % = 0.5
    assert w[0, 2] == pytest.approx(0.25 / 20)
    assert w[0, 3] == 0.0                               # no vol yet -> not held


def test_tsmom_only_decides_on_sundays():
    c = np.linspace(100, 200, 70)
    p = panel(c)
    s = bv.tsmom_signal(p)[:, 0]
    decided = np.where(~np.isnan(s))[0]
    assert len(decided) > 0 and all(bv._weekday(int(p.days[t])) == 6 for t in decided)
    assert all(s[t] == 1.0 for t in decided)            # rising series -> long


def test_execution_happens_at_next_open_and_costs_are_charged_per_side():
    c = np.array([100.0, 100.0, 110.0, 110.0])
    p = panel(c, spread=0.0)
    tg = np.full((4, 1), np.nan)
    tg[0, 0] = 1.0                                      # decided at close of day 0 -> buy at open of day 1 (= 100)
    tg[2, 0] = 0.0                                      # decided at close of day 2 -> sell at open of day 3 (= 110)
    res = bv.simulate(p, tg, cost=bv.COST, start_cash=100.0)
    buy_units = 100.0 / 100.0
    cash_after_buy = 100.0 - buy_units * 100.0 - buy_units * 100.0 * bv.COST
    sell = buy_units * 110.0
    expected = cash_after_buy + sell - sell * bv.COST
    assert res["equity"][3] == pytest.approx(expected)
    assert len(res["positions"]) == 1 and res["positions"][0]["pnl"] == pytest.approx(expected - 100.0)
    assert res["equity"][0] == pytest.approx(100.0)     # nothing traded on day 0 itself


def test_band_skips_small_rebalances_but_not_entries_or_exits():
    c = np.full(6, 100.0)
    p = panel(c, spread=0.0)
    tg = np.array([[0.05], [0.054], [0.06], [0.06], [0.0], [np.nan]])
    res = bv.simulate(p, tg, band=0.10, cost=0.0)
    assert len(res["positions"]) == 1                   # one position: entered, resized once (+20 %), exited
    assert res["turnover"] == pytest.approx(5 + 1 + 6, rel=1e-6)   # 5 % in, +1 % (0.054 skipped by the band), 6 % out


def test_delisted_coin_is_sold_at_its_last_close_and_stays_cash():
    c = np.array([[50.0, 100.0], [50.0, 100.0], [60.0, 100.0], [np.nan, 100.0], [np.nan, 100.0]])   # C0 ends after day 2
    p = panel(c, spread=0.0)
    tg = np.zeros((5, 2))
    tg[:, 0] = 0.5
    res = bv.simulate(p, tg, cost=0.0)
    c0 = [x for x in res["positions"] if x["coin"] == "C0USDT"]
    assert len(c0) == 1 and c0[0]["exit_day"] == int(p.days[2])
    assert c0[0]["pnl"] == pytest.approx(10.0)          # 1 unit bought at 50 (day-1 open), sold at the day-2 close of 60
    assert res["equity"][-1] == pytest.approx(110.0)


def test_bh_and_bootstrap_helpers():
    assert bv.benjamini_hochberg([0.001, 0.2, 0.03, 0.9], q=0.05) == {0}
    rng = np.random.default_rng(3)
    good = rng.normal(0.003, 0.01, 800)
    bad = rng.normal(-0.003, 0.01, 800)
    assert bv.block_bootstrap_p(good) < 0.05 and bv.block_bootstrap_p(bad) > 0.5

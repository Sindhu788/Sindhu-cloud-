import numpy as np
import pytest

from data_platform import rigor


def test_bootstrap_ci_contains_the_point_value_and_is_wider_with_fewer_clusters():
    rng = np.random.default_rng(1)
    pnl = rng.normal(0.05, 1.0, 4000) + np.repeat(rng.normal(0, 0.5, 10), 400)    # trades on the same "day" share a common shock
    wide = rigor.cluster_bootstrap(pnl, np.arange(4000) // 400, n_boot=1500, seed=3)       # 10 clusters
    narrow = rigor.cluster_bootstrap(pnl, np.arange(4000) // 4, n_boot=1500, seed=3)      # 1000 clusters
    assert wide["mean_ci"][0] <= wide["mean"] <= wide["mean_ci"][1]
    assert (wide["mean_ci"][1] - wide["mean_ci"][0]) > (narrow["mean_ci"][1] - narrow["mean_ci"][0])
    assert wide["clusters"] == 10 and narrow["clusters"] == 1000


def test_bootstrap_known_profit_factor():
    pnl = [10, -5] * 50                                              # PF exactly 2 in every resample that keeps the 1:1 mix
    r = rigor.cluster_bootstrap(pnl, np.arange(100) // 2, n_boot=500, seed=1)              # each cluster = one win + one loss
    assert r["pf"] == pytest.approx(2.0) and r["pf_ci"][0] == pytest.approx(2.0) and r["pf_ci"][1] == pytest.approx(2.0)


def test_bootstrap_empty_and_all_losses():
    assert rigor.cluster_bootstrap([], [])["n"] == 0
    r = rigor.cluster_bootstrap([-1.0] * 20, np.arange(20), n_boot=200, seed=1)
    assert r["pf"] == 0.0 and r["pf_ci"][1] == 0.0


def test_bh_fdr_textbook_example():
    # classic example, m = 5, q = 0.05: thresholds 0.01, 0.02, 0.03, 0.04, 0.05
    p = [0.001, 0.008, 0.039, 0.041, 0.60]
    assert rigor.bh_fdr(p, 0.05).tolist() == [True, True, False, False, False]      # 0.039 > 0.03 and 0.041 > 0.04
    assert rigor.bh_fdr([0.005, 0.011, 0.02, 0.03, 0.9], 0.05).tolist() == [True, True, True, True, False]   # step-up: 0.03 <= 0.04
    assert rigor.bh_fdr([0.04, 0.03, 0.9], 0.05).tolist() == [False, False, False]   # none under its own threshold
    assert rigor.bh_fdr([], 0.05).tolist() == []


def test_forty_two_pure_noise_strategies_are_not_discovered():
    rng = np.random.default_rng(5)
    p = rng.random(42)                                              # p-values of 42 strategies with no edge are uniform
    assert rigor.bh_fdr(p, 0.05).sum() <= 2


def _walk(n=30000, seed=2, drift=0.0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, 0.001, n)))
    return np.arange(n, dtype=np.int64) * 60_000, c


def test_null_model_gives_a_luck_strategy_a_large_p_and_a_skilled_one_a_small_p():
    t, c = _walk()
    dur = np.full(300, 30 * 60_000, dtype=np.int64); sides = np.ones(300)
    null = rigor.null_returns(t, c, dur, sides, rt_cost_pct=0.2, n_sims=400, seed=1)
    # "luck" book = a typical random draw from the null itself
    assert rigor.one_sided_p(float(np.median(null)), null) > 0.3
    # "skilled" book = enters only right before the best 30-minute up-moves
    ret = c[30:] / c[:-30] - 1.0
    best = np.sort(ret)[-300:]
    skilled = float((best - 0.002).mean())
    assert rigor.one_sided_p(skilled, null) < 0.01


def test_null_model_costs_matter_and_empty_input_is_safe():
    t, c = _walk()
    dur = np.full(50, 10 * 60_000, dtype=np.int64); sides = np.ones(50)
    a = rigor.null_returns(t, c, dur, sides, 0.0, n_sims=100, seed=4).mean()
    b = rigor.null_returns(t, c, dur, sides, 0.5, n_sims=100, seed=4).mean()
    assert a - b == pytest.approx(0.005, abs=1e-9)
    assert rigor.null_returns(t, c, [], [], 0.2, n_sims=5).tolist() == [0.0] * 5


def test_baselines_known_values():
    assert rigor.buy_and_hold([100, 110], 0.2)["return"] == pytest.approx(0.10 - 0.002)
    up = np.linspace(100, 200, 120)                                  # steady uptrend: SMA20 > SMA50 from the start -> one long trade
    r = rigor.sma_cross_4h(up, 0.0)
    assert r["trades"] == 1 and r["total"] == pytest.approx(up[-1] / up[49] - 1, rel=1e-9)
    flat = rigor.sma_cross_4h(np.full(100, 50.0), 0.0)
    assert flat["trades"] == 0
    base = [100, 101] * 15                                           # quiet, RSI near 50
    crash = [98, 95, 92, 90, 89]                                    # RSI falls under 30 -> buy
    rebound = [95, 100, 104, 105, 105]                              # RSI back above 50 -> sell
    rsi = rigor.rsi_reversion_1h(np.array(base + crash + rebound, dtype=float), 0.0)
    assert rsi["trades"] == 1 and rsi["mean_net"] > 0.03
    cost = rigor.rsi_reversion_1h(np.array(base + crash + rebound, dtype=float), 1.0)
    assert cost["mean_net"] == pytest.approx(rsi["mean_net"] - 0.01)

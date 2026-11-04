from data_platform import experiments as ex


def trades(n=5, bump=0.0):
    return [{"entry_time": 1000 + i, "exit_time": 2000 + i, "side": "long", "entry_price": 100.0 + i, "exit_price": 101.5 + i + bump, "pnl": 1.5 + bump} for i in range(n)]


def test_result_hash_is_deterministic_and_sensitive():
    assert ex.result_hash(trades()) == ex.result_hash(trades())
    assert ex.result_hash(trades()) != ex.result_hash(trades(bump=0.01))
    assert ex.result_hash(trades()) != ex.result_hash(trades(4))


def test_config_hash_ignores_key_order_and_changes_with_content():
    a, b = {"x": 1, "y": [1, 2]}, {"y": [1, 2], "x": 1}
    assert ex.config_hash(a) == ex.config_hash(b) and ex.config_hash(a) != ex.config_hash({"x": 2, "y": [1, 2]})


def test_tracker_stores_runs_side_by_side(tmp_path):
    root = str(tmp_path)
    for sym, h in (("BTCUSDT", "aa"), ("ETHUSDT", "bb")):
        ex.record({"kind": "dev", "strategy_id": "s1", "strategy_name": "S1", "config_hash": "c1", "code_commit": "abc1234", "data_version": "dv1",
                   "universe": "u", "symbol": sym, "window_start": 1, "window_end": 2, "cost_json": {"commission_pct": 0.1}, "n_trades": 5,
                   "metrics_json": {"pf": 1.2}, "trades_path": "x", "result_hash": h}, root=root)
    rows = ex.compare(["s1"], root=root)
    assert [r[2] for r in rows] == ["BTCUSDT", "ETHUSDT"] and rows[0][6] == "dv1" and rows[0][8] == "abc1234" and rows[1][9] == "bb"
    assert ex.compare(["nope"], root=root) == []


def test_two_identical_runs_have_the_same_result_hash_end_to_end():
    """The runner's contract: same strategy + same data + same costs -> the same trade list. Checked on a deterministic stand-in for the engine
    (the real-data check is scripts/ reproducibility run, recorded in docs/BACKTEST_PROTOCOL.md)."""
    import numpy as np

    def fake_engine(seed):
        rng = np.random.default_rng(seed)
        px = 100 + np.cumsum(rng.normal(0, 1, 50))
        return [{"entry_time": int(i), "exit_time": int(i) + 5, "side": "long", "entry_price": float(px[i]), "exit_price": float(px[i + 3]),
                 "pnl": float(px[i + 3] - px[i])} for i in range(0, 40, 5)]

    assert ex.result_hash(fake_engine(7)) == ex.result_hash(fake_engine(7)) != ex.result_hash(fake_engine(8))

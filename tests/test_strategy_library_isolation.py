import os

from backtest_engine import strategy_library as lib


def test_tests_never_point_at_the_real_git_tracked_library():
    real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies", "library")
    assert os.path.abspath(lib._LIBRARY_DIR) != os.path.abspath(real)


def test_snapshot_refresh_never_degrades_a_stored_profit_factor(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    os.makedirs(tmp_path / "abc")
    (tmp_path / "abc" / "meta.json").write_text('{"id": "abc", "backtest_snapshot": {"batch_id": "b1", "profit_factor": 2.0, "win_rate": 30}}')
    lib.save_backtest_snapshot("abc", {"batch_id": "b1", "profit_factor": None, "win_rate": 30})
    assert lib._read_meta("abc")["backtest_snapshot"]["profit_factor"] == 2.0
    lib.save_backtest_snapshot("abc", {"batch_id": "b2", "profit_factor": None, "win_rate": 31})
    assert lib._read_meta("abc")["backtest_snapshot"]["batch_id"] == "b2"

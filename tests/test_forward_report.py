import datetime as dt
import importlib.util
import pathlib

import pytest

spec = importlib.util.spec_from_file_location("fr", pathlib.Path(__file__).resolve().parents[1] / "tools" / "forward_report.py")
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)

START = "2026-11-06T00:00:00Z"
START_MS = fr._ms(START)
DAY = 86_400_000


def reg(candidates=()):
    r = {"forward_window_start_utc": START, "earliest_evaluation_date": "2027-01-05", "min_positions": 100, "candidates": list(candidates)}
    r["_start_ms"] = fr._ms(START); r["_earliest"] = dt.date(2027, 1, 5)
    return r


def pos(i, opened, status="closed", pnl=1.0, sid="s1", closed=None):
    return {"id": f"p{i}", "strategy_id": sid, "strategy_name": "Strat " + sid, "status": status, "entry_time": opened, "exit_time": closed or opened + 3_600_000,
            "pnl": pnl, "risk_amount": 1.0}


def test_only_positions_opened_in_the_window_and_closed_are_counted():
    ps = [pos(1, START_MS - 1, closed=START_MS + 1000),          # opened before the window, closed inside: excluded (and reported)
          pos(2, START_MS), pos(3, START_MS + DAY), pos(4, START_MS + 2 * DAY, status="open")]
    fwd, open_fwd, excluded = fr.select(ps, START_MS)
    assert [p["id"] for p in fwd] == ["p2", "p3"] and [p["id"] for p in open_fwd] == ["p4"] and excluded == 1


def test_before_the_evaluation_date_the_report_has_counts_only_no_results():
    ps = [pos(i, START_MS + i * 1000, pnl=(5.0 if i % 2 else -3.0)) for i in range(1, 30)]
    text, early = fr.build_report(ps, [], reg(), dt.date(2026, 12, 1))
    assert early is True and "NO VERDICT" in text and "Forward positions closed: **29**" in text
    for forbidden in ("PASSED", "FAILED", "INSUFFICIENT_DATA", "CANNOT CONCLUDE", "5.0", "-3.0", "| Wins", "| PF", "| Net", "Verdicts"):
        assert forbidden not in text, forbidden
    assert "deliberately not printed" in text and "Verdicts (registered" not in text


def test_verdict_function_refuses_before_the_date_even_when_called_directly():
    ps = [pos(i, START_MS + i * 1000) for i in range(200)]
    with pytest.raises(fr.ForwardTestTooEarly):
        fr.evaluate(ps, reg(), dt.date(2027, 1, 4))
    assert fr.evaluate(ps, reg(), dt.date(2027, 1, 5))["positions"] == 200      # on the date it is allowed


def test_no_command_line_option_can_change_the_date_or_force_a_verdict():
    import argparse
    src = (pathlib.Path(__file__).resolve().parents[1] / "tools" / "forward_report.py").read_text(encoding="utf-8")
    opts = [l for l in src.splitlines() if "add_argument" in l]
    assert all(("--export" in l or "--registry" in l or "--out" in l) for l in opts) and len(opts) == 3
    assert "--force" not in src and "--today" not in src


def test_after_the_date_too_few_positions_is_insufficient_not_a_verdict():
    ps = [pos(i, START_MS + i * 1000) for i in range(40)]
    v = fr.evaluate(ps, reg(), dt.date(2027, 2, 1))
    assert v["verdict"] == "INSUFFICIENT_DATA" and v["positions"] == 40


def test_after_the_date_enough_positions_gives_a_verdict_but_never_a_pass_without_the_candle_based_criteria():
    ps = [pos(i, START_MS + i * 3_600_000, pnl=(2.0 if i % 3 else -1.0)) for i in range(150)]
    v = fr.evaluate(ps, reg(), dt.date(2027, 3, 1))
    states = {c[0]: c[2] for c in v["criteria"]}
    assert states["random-entry null model p < 0.05"] == "NOT COMPUTED" and states["beats the best baseline"] == "NOT COMPUTED"
    assert v["verdict"] in ("CANNOT CONCLUDE (criteria not computed)", "FAILED") and v["verdict"] != "PASSED"


def test_unregistered_strategies_get_counts_but_no_verdict_after_the_date():
    ps = [pos(i, START_MS + i * 1000) for i in range(120)]
    text, early = fr.build_report(ps, [], reg(), dt.date(2027, 2, 1))
    assert early is False and "no candidate was registered before the window" in text


def test_data_quality_notes_report_scan_gaps_and_stale_open_positions():
    ps = [pos(1, START_MS, status="open"), pos(2, START_MS + DAY)]
    scans = [{"completed_at": "2026-11-06T01:00:00+00:00", "outcome": "complete"}, {"completed_at": "2026-11-06T11:00:00+00:00", "outcome": "complete"}]
    notes = fr.quality_notes(ps + [ps[0]], *fr.select(ps, START_MS)[:2], scans, START_MS, dt.date(2026, 11, 20))
    joined = " ".join(notes)
    assert "duplicate position ids in the export: 1" in joined and "still open after more than 7 days: 1 of 1" in joined and "longest gap between completed scans: 10.0 h" in joined


def test_registration_is_append_only_keeps_a_backup_and_sets_its_own_window(tmp_path):
    import json
    spec2 = importlib.util.spec_from_file_location("frg", pathlib.Path(__file__).resolve().parents[1] / "tools" / "forward_register.py")
    frg = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(frg)
    p = tmp_path / "forward_registry.json"
    p.write_text(json.dumps({"forward_window_start_utc": START, "earliest_evaluation_date": "2027-01-05", "min_positions": 100, "candidates": [], "looks": []}))
    now = dt.datetime(2026, 11, 20, 13, 30, tzinfo=dt.timezone.utc)
    e = frg.register(str(p), "abc123", "hash1", "deadbee", now=now)
    assert e["window_start_utc"] == "2026-11-21T00:00:00Z" and (tmp_path / "forward_registry.json.bak").exists()
    assert json.loads(p.read_text())["candidates"][0]["strategy_id"] == "abc123"
    with pytest.raises(ValueError):
        frg.register(str(p), "abc123", "hash1", "deadbee", now=now)                 # no double registration


def test_a_candidate_registered_later_counts_only_positions_opened_after_its_own_window_start():
    own_start = fr._ms("2026-12-01T00:00:00Z")
    r = reg([{"strategy_id": "s1", "window_start_utc": "2026-12-01T00:00:00Z"}])
    ps = [pos(i, START_MS + i * DAY, sid="s1") for i in range(1, 10)] + [pos(100 + i, own_start + i * 3_600_000, sid="s1") for i in range(120)]
    text, early = fr.build_report(ps, [], r, dt.date(2027, 2, 1))
    assert "**s1**" in text and "(120 positions)" in text                             # the 9 earlier positions are not part of the candidate's test

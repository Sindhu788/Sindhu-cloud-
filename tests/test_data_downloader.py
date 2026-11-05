"""Day 5: the candle downloader against a local mock of the Binance public archive (no network). Needs pyarrow (not in the cloud
requirements), so the file is skipped where pyarrow is missing."""
import datetime as dt
import hashlib
import io
import json
import os
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

pytest.importorskip("pyarrow")

from data_platform import downloader, quality, run_download, store  # noqa: E402


def month_minutes(month):
    y, m = int(month[:4]), int(month[5:7])
    start = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    return int(start.timestamp() * 1000), downloader.expected_minutes_month(month)


def make_csv(period, micro=True, drop=(), dup=0, spike_at=None):
    if len(period) == 7:
        t0, n = month_minutes(period)
    else:
        t0 = int(dt.datetime.fromisoformat(period).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        n = 1440
    lines = []
    price = 100.0
    for i in range(n):
        if i in drop:
            continue
        ot = t0 + i * 60_000
        price += np.sin(i / 50.0) * 0.05
        o, c = price, price + 0.01
        h, l = max(o, c) + 0.02, min(o, c) - 0.02
        if spike_at == i:
            h = o * 1.3
        ts = ot * 1000 if micro else ot
        lines.append(f"{ts},{o:.4f},{h:.4f},{l:.4f},{c:.4f},{10 + i % 5:.3f},{ts + 59999},{1000.0:.2f},{50 + i % 7},{5.0:.3f},{500.0:.2f},0")
        if dup and i < dup:
            lines.append(lines[-1])
    return "\n".join(lines) + "\n"


def make_zip(csv_text, name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name.replace(".zip", ".csv"), csv_text)
    return buf.getvalue()


class Mock:
    """Serves /data/spot/{monthly|daily}/klines/SYM/1m/SYM-1m-PERIOD.zip(.CHECKSUM). Behaviour switches for the tests."""

    def __init__(self):
        self.listed_from = {}          # symbol -> first month served (earlier months answer 404)
        self.storm = 0                 # first N requests answer 429
        self.bad_checksum = set()      # file names whose CHECKSUM is wrong
        self.truncate = set()          # file names whose body is cut in half
        self.options = {}              # symbol -> dict(drop=..., dup=..., spike_at=...)
        self.requests = 0
        self.cache = {}                # file name -> zip bytes (one zip per file: the CHECKSUM must describe the very bytes served)
        self.lock = threading.Lock()
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                with mock.lock:
                    mock.requests += 1
                    storm = mock.storm > 0
                    if storm:
                        mock.storm -= 1
                if storm:
                    self.send_response(429); self.send_header("Retry-After", "0"); self.end_headers(); return
                parts = self.path.split("/")
                fname = parts[-1]
                base = fname.replace(".CHECKSUM", "")
                import re
                mm = re.match(r"^(.+?)-(\d+[mhdw])-(\d{4}-\d{2}(?:-\d{2})?)\.zip$", base)
                sym, period = mm.group(1), mm.group(3)
                if period[:7] < mock.listed_from.get(sym, "0000-00"):
                    self.send_response(404); self.end_headers(); return
                opt = mock.options.get(sym, {})
                with mock.lock:
                    if base not in mock.cache:
                        mock.cache[base] = make_zip(make_csv(period, **opt), base)
                    body = mock.cache[base]
                if fname.endswith(".CHECKSUM"):
                    h = "0" * 64 if base in mock.bad_checksum else hashlib.sha256(body).hexdigest()
                    out = f"{h}  {base}\n".encode()
                else:
                    out = body[: len(body) // 2] if base in mock.truncate else body
                self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def mock():
    m = Mock()
    yield m
    m.close()


@pytest.fixture
def root(tmp_path):
    (tmp_path / "manifest").mkdir()
    (tmp_path / "logs").mkdir()
    return str(tmp_path)


def dl(root, mock, workers=3):
    return downloader.Downloader(root=root, workers=workers, base_url=mock.url, sleep=lambda s: None)


def test_happy_path_writes_verified_read_only_parquet_with_millisecond_time(root, mock):
    d = dl(root, mock)
    failed = d.run([("month", s, m) for s in ("AAAUSDT", "BBBUSDT") for m in ("2025-11", "2026-02")], "t")
    assert failed == []
    for s in ("AAAUSDT", "BBBUSDT"):
        for m in ("2025-11", "2026-02"):
            p = store.month_path("binance", s, m, root)
            assert os.path.exists(p) and not os.access(p, os.W_OK)             # finished = read-only
            t = store.to_arrays(store.read_table(p))
            assert len(t["open_time"]) == downloader.expected_minutes_month(m)
            assert t["open_time"][0] < 10 ** 14                                  # microseconds were converted to milliseconds
            assert np.all(np.diff(t["open_time"]) == 60_000)
            ent = d.manifest.get(f"{s}/{m}")
            assert ent["status"] == "ok" and ent["sha256"] == store.sha256_file(p) and ent["zip_verified"] is True
    assert d.progress()["done"] == 4 and d.progress()["percent"] == 100.0


def test_unlisted_month_is_absent_not_a_failure(root, mock):
    mock.listed_from["NEWUSDT"] = "2026-01"
    d = dl(root, mock)
    assert d.run([("month", "NEWUSDT", "2025-11"), ("month", "NEWUSDT", "2026-01")], "t") == []
    assert d.manifest.get("NEWUSDT/2025-11")["status"] == "absent" and d.manifest.get("NEWUSDT/2026-01")["status"] == "ok"
    assert not os.path.exists(store.month_path("binance", "NEWUSDT", "2025-11", root))


def test_429_storm_is_ridden_out_with_backoff(root, mock):
    mock.storm = 6
    d = dl(root, mock, workers=2)
    assert d.run([("month", "AAAUSDT", "2026-02"), ("month", "BBBUSDT", "2026-02")], "t") == []
    assert d.progress()["done"] == 2 and mock.requests > 6


def test_checksum_mismatch_and_truncated_download_leave_no_file(root, mock):
    mock.bad_checksum.add("AAAUSDT-1m-2026-02.zip")
    mock.truncate.add("BBBUSDT-1m-2026-02.zip")
    d = dl(root, mock)
    failed = d.run([("month", "AAAUSDT", "2026-02"), ("month", "BBBUSDT", "2026-02")], "t")
    assert len(failed) == 2
    for s in ("AAAUSDT", "BBBUSDT"):
        assert not os.path.exists(store.month_path("binance", s, "2026-02", root)) and d.manifest.get(f"{s}/2026-02") is None
    assert d.progress()["failed"] == 2 and d.progress()["last_error"]


def test_kill_during_write_leaves_no_corrupt_file_and_resume_finishes_it(root, mock, monkeypatch):
    import pyarrow.parquet as pq
    real = pq.write_table

    def dying(table, path, **k):
        real(table, path, **k)
        raise KeyboardInterrupt("simulated crash after the temporary file was written")

    monkeypatch.setattr(store.pq, "write_table", dying)
    d1 = dl(root, mock)
    with pytest.raises(KeyboardInterrupt):
        d1.run_task("month", "AAAUSDT", "2026-02")
    final = store.month_path("binance", "AAAUSDT", "2026-02", root)
    assert not os.path.exists(final) and os.path.exists(final + ".tmp") and d1.manifest.get("AAAUSDT/2026-02") is None
    monkeypatch.setattr(store.pq, "write_table", real)
    d2 = dl(root, mock)                                                          # a new process, same manifest on disk
    assert d2.run([("month", "AAAUSDT", "2026-02")], "t") == []
    assert os.path.exists(final) and not os.path.exists(final + ".tmp")
    d3 = dl(root, mock)
    n = mock.requests
    d3.run([("month", "AAAUSDT", "2026-02")], "t")
    assert d3.progress()["skipped_done"] == 1 and mock.requests == n             # resume = nothing downloaded twice


def test_finished_files_are_never_overwritten(root, mock):
    d = dl(root, mock)
    d.run_task("month", "AAAUSDT", "2026-02")
    p = store.month_path("binance", "AAAUSDT", "2026-02", root)
    with pytest.raises(FileExistsError):
        store.write_atomic(p, store.read_table(p))
    before = store.sha256_file(p)
    os.remove(os.path.join(root, "manifest", "manifest.json"))                    # manifest lost: file is adopted after re-verification, not rewritten
    d2 = dl(root, mock)
    n = mock.requests
    d2.run_task("month", "AAAUSDT", "2026-02")
    assert store.sha256_file(p) == before and mock.requests == n and d2.manifest.get("AAAUSDT/2026-02")["note"] == "adopted existing file"


def test_disk_guard_stops_the_job_before_writing(root, mock, monkeypatch):
    monkeypatch.setattr(downloader, "_free_bytes", lambda p: 1 << 30)            # 1 GB free < 5 GB guard
    d = dl(root, mock)
    d.run([("month", "AAAUSDT", "2026-02"), ("month", "BBBUSDT", "2026-02")], "t")
    assert d.stop.is_set() and "disk free" in d.stop_reason and not os.path.exists(store.month_path("binance", "AAAUSDT", "2026-02", root))
    assert d.write_progress()["stop_reason"]


def test_progress_json_is_written_atomically_and_has_eta(root, mock):
    d = dl(root, mock)
    d.run([("month", "AAAUSDT", "2026-02")], "pilot")
    p = d.write_progress({"phase": "pilot"})
    on_disk = json.load(open(os.path.join(root, "manifest", "progress.json")))
    assert on_disk["percent"] == 100.0 and on_disk["rows"] == p["rows"] > 0 and "eta_minutes" in on_disk and on_disk["pid"] == os.getpid()


def test_quality_flags_gaps_duplicates_and_spikes_without_inventing_candles(root, mock):
    mock.options["GAPUSDT"] = dict(drop=set(range(100, 160)) | {5000}, dup=3, spike_at=777)
    d = dl(root, mock)
    d.run([("month", "GAPUSDT", "2026-02"), ("month", "OKUSDT", "2026-02")], "t")
    rep = quality.check_dataset(["GAPUSDT", "OKUSDT"], ["2026-02"], base=root)
    g, ok = rep["coins"]["GAPUSDT"]["2026-02"], rep["coins"]["OKUSDT"]["2026-02"]
    assert g["missing_minutes"] == 61 and g["gap_count"] == 2 and g["largest_gap_minutes"] == 60 and g["spikes"] == 1
    assert d.manifest.get("GAPUSDT/2026-02")["duplicates_dropped"] == 3
    assert g["rows"] == downloader.expected_minutes_month("2026-02") - 61              # nothing was forward-filled
    assert ok["ok"] is True and ok["missing_minutes"] == 0 and ok["ohlc_violations"] == 0
    assert rep["summary"]["files_checked"] == 2


def test_pilot_gate_then_expansion_end_to_end(root, mock, monkeypatch):
    uni = {"date": "2026-11-04", "symbols": ["AAAUSDT", "BBBUSDT", "CCCUSDT"]}
    os.makedirs(os.path.join(root, "universe"))
    json.dump(uni, open(os.path.join(root, "universe", "universe_2026-11-04.json"), "w"))
    rc = run_download.main(["--root", root, "--workers", "2", "--pilot-coins", "2", "--pilot-months", "2", "--coins", "3", "--months", "3",
                            "--base-url", mock.url])
    assert rc == 0
    gate = json.load(open(os.path.join(root, "manifest", "pilot_gate.json")))
    prog = json.load(open(os.path.join(root, "manifest", "progress.json")))
    assert gate["verdict"] == "PASS" and prog["phase"] == "complete" and prog["failed"] == 0
    man = json.load(open(os.path.join(root, "manifest", "manifest.json")))
    assert sum(1 for k in man if k.count("-") == 1 and man[k]["status"] == "ok") == 9                # 3 coins x 3 months
    assert any(k.count("-") == 2 for k in man)                                                       # current-month daily files exist too


def test_failed_pilot_blocks_the_expansion(root, mock):
    mock.options["AAAUSDT"] = dict(drop=set(range(0, 20000)))                                        # a month with half of it missing
    uni = {"date": "2026-11-04", "symbols": ["AAAUSDT", "BBBUSDT"]}
    os.makedirs(os.path.join(root, "universe"))
    json.dump(uni, open(os.path.join(root, "universe", "universe_2026-11-04.json"), "w"))
    run_download.main(["--root", root, "--workers", "2", "--pilot-coins", "1", "--pilot-months", "1", "--coins", "2", "--months", "2", "--base-url", mock.url])
    gate = json.load(open(os.path.join(root, "manifest", "pilot_gate.json")))
    prog = json.load(open(os.path.join(root, "manifest", "progress.json")))
    assert gate["verdict"] == "FAIL" and prog["phase"] == "pilot_done_no_expansion"
    man = json.load(open(os.path.join(root, "manifest", "manifest.json")))
    assert "BBBUSDT/" + downloader.month_list(dt.datetime.now(dt.timezone.utc).strftime("%Y-%m"), 2)[0] not in man


def test_two_processes_must_not_share_one_manifest_and_replace_retries_on_windows_locks(root, mock, monkeypatch):
    a = downloader.Downloader(root=root, workers=1, base_url=mock.url, sleep=lambda s: None)
    b = downloader.Downloader(root=root, workers=1, base_url=mock.url, sleep=lambda s: None, manifest_name="native_manifest.json")
    a.run_task("month", "AAAUSDT", "2026-02")
    b.run_task("month:5m", "AAAUSDT", "2026-02")
    assert os.path.exists(os.path.join(root, "manifest", "manifest.json")) and os.path.exists(os.path.join(root, "manifest", "native_manifest.json"))
    assert "AAAUSDT/5m/2026-02" not in json.load(open(os.path.join(root, "manifest", "manifest.json")))
    calls = []
    real = os.replace

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("[WinError 32] file in use")
        return real(src, dst)

    monkeypatch.setattr(downloader.os, "replace", flaky)
    monkeypatch.setattr(downloader.time, "sleep", lambda s: None)
    a.manifest.put("X/2026-01", {"status": "absent"})
    assert len(calls) == 3 and a.manifest.get("X/2026-01")["status"] == "absent"


def test_recent_404_is_pending_not_absent_so_the_next_run_asks_again(root, mock, monkeypatch):
    import datetime as dt
    mock.listed_from["LATEUSDT"] = "2026-12"                               # everything before December answers 404
    monkeypatch.setattr(downloader, "_today", lambda: dt.date(2026, 11, 5))
    d = dl(root, mock)
    d.run([("day", "LATEUSDT", "2026-11-04"), ("month", "LATEUSDT", "2025-11"), ("day", "LATEUSDT", "2026-11-01")], "t")
    assert d.manifest.get("LATEUSDT/2026-11-04") is None                   # yesterday: not published yet -> nothing recorded
    assert d.manifest.get("LATEUSDT/2025-11")["status"] == "absent"        # a year ago: really absent
    assert d.manifest.get("LATEUSDT/2026-11-01")["status"] == "absent"     # older than the grace period: absent
    assert d.stats.get("pending") == 1
    mock.listed_from["LATEUSDT"] = "2026-01"                               # it gets published
    d2 = dl(root, mock)
    d2.run([("day", "LATEUSDT", "2026-11-04")], "t2")
    assert d2.manifest.get("LATEUSDT/2026-11-04")["status"] == "ok"


def test_recent_month_404_is_pending_for_three_days_after_month_end(monkeypatch):
    import datetime as dt
    monkeypatch.setattr(downloader, "_today", lambda: dt.date(2026, 11, 2))
    assert downloader._too_recent_to_be_absent("month", "2026-10") is True
    monkeypatch.setattr(downloader, "_today", lambda: dt.date(2026, 11, 5))
    assert downloader._too_recent_to_be_absent("month", "2026-10") is False
    assert downloader._too_recent_to_be_absent("month", "2026-12") is True       # a future month is never 'absent'
    assert downloader._too_recent_to_be_absent("day", "garbage") is False


def test_dry_run_reports_missing_files_without_touching_anything(tmp_path):
    import datetime as dt
    import json
    from data_platform import run_download
    (tmp_path / "manifest").mkdir()
    man = {"AUSDT/2026-10": {"status": "ok"}, "AUSDT/2026-09": {"status": "absent"}, "AUSDT/2026-11-01": {"status": "ok"}}
    (tmp_path / "manifest" / "manifest.json").write_text(json.dumps(man))
    before = (tmp_path / "manifest" / "manifest.json").read_bytes()
    rep = run_download.pending_report(str(tmp_path), {"symbols": ["AUSDT", "BUSDT"]}, 2, 2, dt.date(2026, 11, 3))
    assert rep["tasks_total"] == 2 * 2 + 2 * 2 and rep["already_done"] == 3
    assert rep["missing_days"] == ["2026-11-01", "2026-11-02"] and rep["missing_months"] == ["2026-09", "2026-10"]
    assert (tmp_path / "manifest" / "manifest.json").read_bytes() == before        # nothing written

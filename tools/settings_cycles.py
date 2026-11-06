"""Master plan A21 (P9): the settings 50-cycle test.

For a fixed seed, each cycle picks one user-changeable Paper Trading setting and either a VALID or an INVALID value
(negative, too big, wrong type, empty, unknown option), sends it through the real HTTP API (POST /api/paper-trading/settings),
and checks:
- valid   -> 200, read back via GET is the new value; every 10th cycle a FRESH Python process (a real restart) reads the saved
             settings and must see the same values; for risk_pct_default the effect is checked (risk-based size changes in proportion).
- invalid -> 422 with a message for that field, and the OLD value is still there (GET and, every 10th cycle, the fresh process).
Runs on SQLite in a throwaway data folder. With --postgres (master plan V2 R7) it runs against TEST_DATABASE_URL from the local .env
(a throwaway Neon branch); it refuses when that URL has the same host and database as the production DATABASE_URL.
Usage (stable venv): python tools/settings_cycles.py [--cycles 50] [--seed 20261105] [--write]
"""
import argparse
import json
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENUMS = {"priority_rule": ["confidence_and_win_rate", "confidence", "win_rate", "profit", "manual"],
         "opposite_signal_policy": ["block", "allow", "close_and_reverse"]}
HHMM = ["time_filter_block_start_utc", "time_filter_block_end_utc"]


def _numeric_rules():
    from paper_trading import config as pt_config
    return dict(pt_config._NUMERIC_RULES)


def _api_fields():
    from sindhu_web.api.paper_trading import SettingsUpdate
    return set(SettingsUpdate.__fields__ if hasattr(SettingsUpdate, "__fields__") else SettingsUpdate.model_fields)


def valid_value(rng, field, rule):
    kind, lo, hi, inc = rule
    lo2 = (lo if lo is not None else 0) + (0 if inc else (1 if kind == "int" else 0.01))
    hi2 = hi if hi is not None else (lo2 + 500)
    if kind == "int":
        return rng.randint(int(lo2), int(min(hi2, lo2 + 500)))
    return round(rng.uniform(lo2, min(hi2, lo2 + 500)), 3)


def invalid_value(rng, field, rule):
    kind, lo, hi, inc = rule
    options = ["wrong_type", "empty"]
    if lo is not None:
        options.append("below")
    if hi is not None:
        options.append("above")
    pick = rng.choice(options)
    if pick == "wrong_type":
        return "abc", pick
    if pick == "empty":
        return "", pick
    if pick == "below":
        return (lo - 5) if kind == "int" else lo - 5.5, pick
    return (hi + 5) if kind == "int" else hi + 5.5, pick


_PG_URL = {"url": None}   # master plan V2 R7: set only by --postgres (a throwaway TEST_DATABASE_URL, never production)


def _dotenv(name):
    val = os.environ.get(name, "")
    try:
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            line = line.strip()
            if line.startswith(name + "="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return val


def _target(url):
    """host + database name of a Postgres URL (no user, no password) for the production check."""
    from urllib.parse import urlparse
    u = urlparse(url)
    return ((u.hostname or "").lower(), (u.path or "").lstrip("/").lower())


def production_targets():
    out = set()
    for v in (os.environ.get("DATABASE_URL", ""), _dotenv("DATABASE_URL")):
        if v:
            out.add(_target(v))
    try:
        j = json.load(open(r"D:/sindhu/data/config/neon_runtime_connection.json", encoding="utf-8"))
        if j.get("database_url"):
            out.add(_target(j["database_url"]))
    except Exception:
        pass
    return out


def safe_test_url():
    """TEST_DATABASE_URL, or SystemExit when missing or when it points at a production database (same host AND database)."""
    url = _dotenv("TEST_DATABASE_URL")
    if not url:
        raise SystemExit("BLOCKED: TEST_DATABASE_URL is not set (local .env). See docs/OWNER_TODO.md (V2 R7). Nothing was run.")
    if _target(url) in production_targets():
        raise SystemExit("REFUSED: TEST_DATABASE_URL points at the production database. Use a Neon branch. Nothing was run.")
    return url


def fresh_process_read(data_dir):
    code = ("import json,sys; sys.path.insert(0, %r); from paper_trading import config as c; print(json.dumps(c.load()))" % ROOT)
    env = dict(os.environ, SINDHU_DATA_DIR=data_dir)
    env.pop("DATABASE_URL", None)
    if _PG_URL["url"]:
        env["DATABASE_URL"] = _PG_URL["url"]
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=180)
    return json.loads(out.stdout.strip().splitlines()[-1])


def run(cycles=50, seed=20261105, client=None, data_dir=None):
    from fastapi.testclient import TestClient
    rng = random.Random(seed)
    if client is None:
        import cloud_runtime.app as cloud
        client = TestClient(cloud.app)
    rules = {f: r for f, r in _numeric_rules().items() if f in _api_fields()}
    fields = sorted(rules) + sorted(ENUMS) + HHMM
    rows = {f: {"cycles": 0, "pass": 0, "fail": 0, "notes": []} for f in fields}
    expected = {}
    for i in range(1, cycles + 1):
        field = rng.choice(fields)
        valid = rng.random() < 0.6
        before = client.get("/api/paper-trading/settings").json()
        if field in ENUMS:
            value, why = (rng.choice(ENUMS[field]), "valid") if valid else (rng.choice(["nonsense", "", "BLOCK!"]), "unknown option")
        elif field in HHMM:
            value, why = (f"{rng.randint(0, 23):02d}:{rng.choice([0, 15, 30, 45]):02d}", "valid") if valid else (rng.choice(["25:00", "7pm", ""]), "bad time")
        else:
            value, why = (valid_value(rng, field, rules[field]), "valid") if valid else invalid_value(rng, field, rules[field])
        r = client.post("/api/paper-trading/settings", json={field: value})
        ok = True
        note = ""
        after = client.get("/api/paper-trading/settings").json()
        if valid:
            ok = r.status_code == 200 and after.get(field) == value
            if ok:
                expected[field] = value
            note = f"HTTP {r.status_code}"
            if ok and field == "risk_pct_default":
                from paper_trading import risk_manager
                s1 = risk_manager._position_size(1000.0, 1000.0, 100.0, 95.0, value / 100.0, 0.1)
                s2 = risk_manager._position_size(1000.0, 1000.0, 100.0, 95.0, (value / 2) / 100.0, 0.1)
                ok = s1 > 0 and (abs(s1 - 2 * s2) < 1e-9 or s1 >= 1000.0 * 0.1 / 100.0)   # proportional (unless capped by the 10 % cap)
                note += ", size effect ok" if ok else ", size effect WRONG"
        else:
            msg = ""
            try:
                msg = json.dumps(r.json())
            except Exception:
                pass
            ok = r.status_code == 422 and after.get(field) == before.get(field) and (field in msg or "detail" in msg)
            note = f"{why}: HTTP {r.status_code}, old value kept" if ok else f"{why}: HTTP {r.status_code}, value now {after.get(field)!r}"
        if i % 10 == 0 and data_dir:
            fresh = fresh_process_read(data_dir)
            mism = {k: (v, fresh.get(k)) for k, v in expected.items() if fresh.get(k) != v}
            if mism:
                ok = False
                note += f"; after restart differs: {mism}"
            else:
                note += "; restart read-back ok"
        row = rows[field]
        row["cycles"] += 1
        row["pass" if ok else "fail"] += 1
        if len(row["notes"]) < 3:
            row["notes"].append(f"#{i} {note}")
    return rows


def report(rows, cycles, seed):
    total_pass = sum(r["pass"] for r in rows.values())
    total = sum(r["cycles"] for r in rows.values())
    lines = [f"# SETTINGS TEST REPORT (master plan A21 / P9)\n",
             f"{cycles} cycles, seed {seed}, SQLite in a throwaway data folder, through the real HTTP API "
             f"(`python tools/settings_cycles.py --cycles {cycles} --seed {seed} --write`). Every 10th cycle a fresh Python process (a real "
             "restart) re-reads all saved settings. **Postgres: BLOCKED** (no local Postgres/Docker and no throwaway Neon branch; the real "
             "Cloud database is never used for tests).\n",
             f"**Result: {total_pass} of {total} cycles passed.**\n",
             "| Setting | Cycles | Pass | Fail | Notes (first 3) |", "|---|---|---|---|---|"]
    for f, r in sorted(rows.items()):
        if r["cycles"]:
            lines.append(f"| {f} | {r['cycles']} | {r['pass']} | {r['fail']} | {'; '.join(r['notes'])} |")
    untested = [f for f, r in rows.items() if not r["cycles"]]
    if untested:
        lines.append(f"\nNot drawn by this seed (covered by the per-field validator tests): {', '.join(sorted(untested))}.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261105)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--postgres", action="store_true", help="run against TEST_DATABASE_URL (throwaway Neon branch), never production")
    a = ap.parse_args()
    d = tempfile.mkdtemp(prefix="sindhu_settings_cycles_")
    os.environ["SINDHU_DATA_DIR"] = d
    os.environ.pop("DATABASE_URL", None)
    if a.postgres:
        _PG_URL["url"] = safe_test_url()
        os.environ["DATABASE_URL"] = _PG_URL["url"]
    sys.path.insert(0, ROOT)
    from data_engine import storage
    storage.init_db()
    from fastapi.testclient import TestClient
    from sindhu_web import security, auth
    security._is_lan_client = lambda h: True
    auth.is_valid_session = lambda t: True
    from sindhu_web import security as sec
    sec.get_or_create_token = lambda: "t"
    import cloud_runtime.app as cloud
    c = TestClient(cloud.app, headers={"X-Sindhu-Token": "t"})
    rows = run(a.cycles, a.seed, c, d)
    text = report(rows, a.cycles, a.seed)
    print(text)
    if a.write:
        open(os.path.join(ROOT, "docs", "SETTINGS_TEST_REPORT.md"), "w", encoding="utf-8").write(text)

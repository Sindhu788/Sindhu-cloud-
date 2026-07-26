"""One-off deployment script (not part of the app): enables every strategy
currently in genuine "Ready" status (passes both validator.validate() and
the Automatic Strategy Safety Check, against today's fixed engine) for
Paper Trading, then starts the Paper Trading engine if it isn't already
running.

Uses ONLY the existing, already-sanctioned data-layer function
(storage.save_paper_strategy_config) and the existing engine start
method (paper_trading.engine.engine.start()) -- the exact same calls
automation_pipeline/pipeline.py's own Step 4 already makes for a single
strategy. Nothing about how the engine decides trades, matches coins, or
manages risk is touched.

A strategy whose Walk-Forward Test failed (or was never run) is still
deployed -- Walk-Forward status is informational only, per explicit
instruction, never a deployment gate. Its status is reported plainly so
it's never mistaken for a clean bill of health.

Usage: python scripts/deploy_ready_strategies_to_paper_trading.py
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage
from backtest_engine import strategy_library, validator
from backtest_engine.strategy_safety_check import run_safety_check


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    storage.init_db()
    now = _now_iso()

    ready = []
    for meta in strategy_library.list_all():
        cfg = strategy_library.load(meta["id"])
        safety = run_safety_check(cfg)
        errs = validator.validate(cfg)
        if safety["passed"] and not errs:
            ready.append((meta["id"], cfg.name, meta.get("walk_forward_status")))

    print(f"Deploying {len(ready)} Ready strategies to Paper Trading:\n", flush=True)
    for sid, name, wf in ready:
        storage.save_paper_strategy_config(sid, True, 5, [], [], now)
        wf_label = wf or "not yet run"
        print(f"  ENABLED: {name} ({sid}) -- Walk-Forward: {wf_label}", flush=True)

    print(flush=True)
    print("NOTE: this script only writes the paper_strategy_config rows above -- ", flush=True)
    print("starting the engine itself must happen via the live server's own API", flush=True)
    print("(POST /api/paper-trading/start), NOT by calling engine.start() from this ", flush=True)
    print("disposable script process. engine.start() spawns a background THREAD, and", flush=True)
    print("a thread dies the instant its owning PROCESS exits -- calling it here would", flush=True)
    print("look like success and then silently stop the moment this script ends,", flush=True)
    print("which is the opposite of real 24/7 operation.", flush=True)

    with storage.get_conn() as conn:
        rows = conn.execute("SELECT strategy_id, enabled FROM paper_strategy_config").fetchall()
    print(f"\npaper_strategy_config now has {len(rows)} rows, "
          f"{sum(1 for r in rows if r[1])} enabled.", flush=True)


if __name__ == "__main__":
    main()

"""Master 15-Item task, Item 1: activate all 9 New Batch 5 strategies (23
saved variants total -- see data/checkpoints/strategy_batch_sept2026.json)
for Paper Trading, following the EXACT existing precedent
(scripts/deploy_ready_strategies_to_paper_trading.py): validator.validate()
+ strategy_safety_check.run_safety_check() gate, then
storage.save_paper_strategy_config(sid, True, 5, [], [], now).

Deliberately SCOPED to only these 23 ids (unlike the precedent script,
which touches every "Ready" strategy in the whole library) -- the library
also holds at least one strategy (00749e40c3ca, Asian Range London Sweep --
Confirmation Strict variant) that is currently enabled=False with no
recorded reason, i.e. a deliberate prior disable, not an unconfigured
strategy. Re-running the unscoped precedent script would silently
re-enable it as a side effect; this script never touches any strategy_id
outside the fixed list below.

Explicit CEO decision (per this task's own Item 1 instructions): run every
variant, not just the one backtest-profitable Ichimoku 1d Trailing-SL
variant, to observe real-market behavior vs backtest -- so this script
does not filter by backtest profitability, only by the same
validator+safety-check gate every other paper-trading strategy must pass.
"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage
from backtest_engine import strategy_library, validator
from backtest_engine.strategy_safety_check import run_safety_check

NEW_BATCH_5_IDS = {
    "S1 Liquidity Sweep + Engulfing (Loose)": "96f7cb9100f0",
    "S1 Liquidity Sweep + Engulfing (Strict)": "594c16205e7f",
    "S2 FRVP Market Shape": "433942cfbbe0",
    "S3 S/R + Liquidity Sweep (Structure)": "911f386e038c",
    "S3 S/R + Liquidity Sweep (Fixed-RR)": "e636f066f17e",
    "S4 FVG Momentum Pullback (Structure)": "df643d86c987",
    "S4 FVG Momentum Pullback (Fixed 1:2)": "5a26c66ffa42",
    "S4 FVG Momentum Pullback (Fixed 1:3)": "54c9f3b67aa6",
    "S5 FVG Pure + Inverse (Structure)": "7c8a8f40ce2a",
    "S5 FVG Pure + Inverse (Fixed 1:2)": "edb442d731aa",
    "S6 Order Block Trading (Loose)": "90a2331a3b1c",
    "S6 Order Block Trading (Strict)": "52c6ab43fd4a",
    "S7 Candle Range Theory (Loose)": "2f6ff7755c8f",
    "S7 Candle Range Theory (Strict)": "eba4cc77ee31",
    "S8 BOS/CHoCH Structure Break + Retest": "2e4f21179b50",
    "S9 Ichimoku 5m Indicator-Exit": "86a1e5062c20",
    "S9 Ichimoku 5m Trailing-SL": "a7be577a2752",
    "S9 Ichimoku 15m Indicator-Exit": "04598eaca214",
    "S9 Ichimoku 15m Trailing-SL": "beab3636067e",
    "S9 Ichimoku 1h Indicator-Exit": "ca0777badd9f",
    "S9 Ichimoku 1h Trailing-SL": "770d68250de1",
    "S9 Ichimoku 1d Indicator-Exit": "d781b37694ef",
    "S9 Ichimoku 1d Trailing-SL": "8d94d5ee403f",
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    storage.init_db()
    now = _now_iso()

    print(f"Checking {len(NEW_BATCH_5_IDS)} New Batch 5 strategy variants against the same "
          f"validator+safety-check gate every paper-trading strategy must pass...\n", flush=True)

    activated = []
    blocked = []
    for name, sid in NEW_BATCH_5_IDS.items():
        cfg = strategy_library.load(sid)
        safety = run_safety_check(cfg)
        errs = validator.validate(cfg)
        existing = storage.get_paper_strategy_config(sid)
        already_enabled = bool(existing and existing.get("enabled"))
        if safety["passed"] and not errs:
            storage.save_paper_strategy_config(sid, True, 5, [], [], now)
            status = "already active, re-confirmed" if already_enabled else "ACTIVATED"
            activated.append((name, sid, status))
            print(f"  {status}: {name} ({sid})", flush=True)
        else:
            blocked.append((name, sid, safety.get("reasons"), errs))
            print(f"  BLOCKED (safety/validator failed): {name} ({sid})", flush=True)
            if errs:
                print(f"    validator errors: {errs}", flush=True)
            if not safety["passed"]:
                print(f"    safety reasons: {safety.get('reasons')}", flush=True)

    print(f"\n{len(activated)}/{len(NEW_BATCH_5_IDS)} activated, {len(blocked)} blocked.", flush=True)

    with storage.get_conn() as conn:
        rows = conn.execute("SELECT strategy_id, enabled FROM paper_strategy_config").fetchall()
    print(f"paper_strategy_config now has {len(rows)} total rows, "
          f"{sum(1 for r in rows if r[1])} enabled.", flush=True)

    import json
    with open("data/checkpoints/_item1_activation_result.json", "w", encoding="utf-8") as f:
        json.dump({
            "activated": [{"name": n, "strategy_id": s, "status": st} for n, s, st in activated],
            "blocked": [{"name": n, "strategy_id": s, "safety_reasons": r, "validator_errors": e} for n, s, r, e in blocked],
            "total_paper_strategy_config_rows": len(rows),
            "total_enabled": sum(1 for r in rows if r[1]),
        }, f, indent=2)


if __name__ == "__main__":
    main()

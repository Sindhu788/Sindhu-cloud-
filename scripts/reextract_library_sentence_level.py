"""Batch 5, Task 1 -- re-processes every existing saved strategy through
the new sentence-level extraction pipeline (deterministic rule counting +
one small AI call per candidate statement + retry-until-reconciled),
replacing Batch 3's multi-pass whole-document approach.

For each strategy:
  1. Skip if it has no stored raw_text (nothing to re-extract from).
  2. Skip if the Governor reports CPU/RAM over limit -- this machine has
     8GB RAM and must not be overloaded; re-checked before EVERY strategy,
     not just once at the start.
  3. Run the deterministic candidate count (free, instant) and the real
     sentence-level extraction (real AI calls, real cost).
  4. Compare the new captured strategy's DNA (knowledge_compiler.quality.
     strategy_dna, the same fingerprint already used to detect duplicates)
     against the currently-saved version's DNA. If they differ, the
     config genuinely changed:
       - save_version() (bumps the strategy's version number)
       - storage.save_strategy_extraction_correction() records the
         boundary so Batch 5 Task 2's supersession warning can flag every
         pre-existing paper trade/signal for this strategy as superseded
       - a real quick backtest is run and reported before vs after
  5. Prints EVERY strategy's result the moment it finishes -- never
     batches results until the end.
  6. Respects the pre-AI dedup cache (data_engine.storage.
     get_ai_import_cache) is NOT used here on purpose: this is a one-time
     migration onto genuinely new extraction logic, and the cache holds
     results from the OLD (multi-pass) pipeline -- reusing it here would
     silently skip the very fix this script exists to apply. Normal
     future imports through ai_integration.importer.import_document()
     still use the dedup cache exactly as before; this script is a
     separate, explicit, one-time maintenance operation.

Usage: python scripts/reextract_library_sentence_level.py [--limit N]
"""
import sys
import os
import time
import json
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage
from backtest_engine import strategy_library, validator
from backtest_engine.strategy_safety_check import run_safety_check
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.verification_engine import run_verification
from backtest_engine.strategy_config import SLTPSpec
from ai_integration import sentence_level_extraction, strategy_builder
from knowledge_compiler import quality as kc_quality
from evolution_engine.governor import Governor

SETTINGS = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
            "slippage_pct": 0.05, "position_size_pct": 10.0}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _demo_backtest(cfg):
    demo = strategy_library.StrategyConfig.from_dict(cfg.to_dict())
    if demo.stop_loss.type == "unknown":
        demo.stop_loss = SLTPSpec(type="fixed_pct", value=2.0)
    if demo.take_profit.type == "unknown":
        demo.take_profit = SLTPSpec(type="rr", value=2.0)
    try:
        ctx = MultiTimeframeContext("binance", "BTCUSDT", demo.timeframes, None, None)
        if ctx.is_empty():
            return "no BTCUSDT data for this timeframe combination"
        report = run_verification(demo, ctx, dict(SETTINGS), symbol="BTCUSDT")
        return f"{report['trade_count']} trades, win_rate={report.get('win_rate')}, verification={report['overall_status']}"
    except Exception as exc:
        return f"backtest error: {exc!r}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="max strategies to process this run")
    args = parser.parse_args()

    governor = Governor()
    targets = [m for m in strategy_library.list_all() if not m.get("archived")]
    if args.limit:
        targets = targets[:args.limit]
    print(f"Found {len(targets)} active strategies to consider.\n", flush=True)

    results = []
    for i, meta in enumerate(targets):
        sid, name = meta["id"], meta["name"]
        print("=" * 78, flush=True)
        print(f"[{i+1}/{len(targets)}] {name}  ({sid})", flush=True)

        if not governor.resource_ok():
            print(f"  SKIPPED (this run): CPU/RAM over limit -- {governor._last_resource_check}", flush=True)
            results.append((name, sid, "skipped (resources)", None, None))
            time.sleep(5)
            continue

        before_cfg = strategy_library.load(sid)
        raw_text = before_cfg.raw_text
        if not raw_text or not raw_text.strip():
            print("  SKIPPED: no raw_text stored for this strategy.", flush=True)
            results.append((name, sid, "skipped (no raw_text)", None, None))
            continue

        before_dna = kc_quality.strategy_dna(before_cfg)
        before_bt = _demo_backtest(before_cfg)
        print(f"  BEFORE backtest: {before_bt}", flush=True)

        t0 = time.time()
        mp = sentence_level_extraction.run_sentence_level_extraction(raw_text, content_type="strategy")
        elapsed = time.time() - t0
        expected, captured = mp["comparison"]["expected_count"], mp["comparison"]["captured_count"]
        print(f"  Deterministic expected={expected}  captured={captured}  calls={mp['call_count']}  "
              f"retries={mp['retry_count']}  elapsed={elapsed:.1f}s  provider={mp['provider']}", flush=True)

        if mp["result"] is None or not mp["result"].get("strategy"):
            print(f"  RE-EXTRACTION PRODUCED NOTHING USABLE: {mp['error']}", flush=True)
            results.append((name, sid, "no usable result", before_bt, None))
            continue

        new_cfg = strategy_builder.build_strategy_config(mp["result"]["strategy"], name, raw_text)
        new_cfg.name = name
        new_dna = kc_quality.strategy_dna(new_cfg)
        new_errors = validator.validate(new_cfg)
        safety = run_safety_check(new_cfg)
        print(f"  AFTER validator errors: {len(new_errors)}  safety={safety['status']}", flush=True)

        if new_dna == before_dna:
            print("  NOT SAVED -- re-extraction produced the SAME config (no correction needed).", flush=True)
            results.append((name, sid, "unchanged", before_bt, before_bt))
            continue

        new_version = strategy_library.save_version(sid, new_cfg)
        now_iso = _now_iso()
        # This is the content_hash the fidelity report is keyed on for the
        # verification view -- same convention importer.py uses.
        import hashlib, re
        content_hash = hashlib.sha256(re.sub(r"\s+", " ", raw_text.strip().lower()).encode("utf-8")).hexdigest()
        storage.save_extraction_fidelity_report(
            content_hash, expected, captured, mp["call_count"], mp["comparison"]["rules"],
            mp["provider"], now_iso, retry_count=mp["retry_count"],
        )
        storage.set_extraction_fidelity_strategy_id(content_hash, sid)

        old_report = storage.get_extraction_fidelity_report_for_strategy(sid)
        prev_expected = old_report["expected_rule_count"] if old_report else None
        prev_captured = old_report["captured_rule_count"] if old_report else None
        storage.save_strategy_extraction_correction(
            sid, corrected_at_version=new_version,
            previous_expected_count=prev_expected, previous_captured_count=prev_captured,
            new_expected_count=expected, new_captured_count=captured,
            reason="Batch 5, Task 1 sentence-level re-extraction", now_iso=now_iso,
        )
        print(f"  SAVED as version {new_version}; supersession boundary recorded (Task 2).", flush=True)

        after_bt = _demo_backtest(new_cfg)
        print(f"  AFTER backtest: {after_bt}", flush=True)
        results.append((name, sid, f"captured {captured}/{expected}", before_bt, after_bt))

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for name, sid, outcome, before_bt, after_bt in results:
        print(f"{name:<48} {outcome:<28} before=[{before_bt}]  after=[{after_bt}]")


if __name__ == "__main__":
    main()

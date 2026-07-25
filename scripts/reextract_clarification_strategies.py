"""One-off maintenance script: re-runs GENUINE AI extraction (not the
deterministic regex parser) against every strategy currently sitting in
NEEDS_CLARIFICATION (unparseable type="raw" rules), using each strategy's
own already-stored raw_text.

Deliberately does NOT go through ai_integration.importer.import_document()
-- that orchestrator's pre-AI dedup cache (data_engine.storage.
get_ai_import_cache) would replay the ORIGINAL (broken) cached AI response
for unchanged text instead of calling the model again, defeating the
whole point of a re-extraction. This script explicitly clears that cache
entry first, then calls the same deep_understanding/strategy_builder
pieces import_document() uses, and saves directly onto the KNOWN
strategy_id via strategy_library.save_version() -- so a strategy is always
updated in place, never duplicated, even if the AI's own "name" field
comes back slightly different this time.

Every fix produced here still goes through the same automatic
self-correction pipeline (ai_integration.self_correction.self_correct)
that a live import gets, and is verified against real BTCUSDT data
afterwards -- not just checked for "no more raw conditions".

Usage: python scripts/reextract_clarification_strategies.py
"""
import sys
import os
import hashlib
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_engine import storage
from backtest_engine import strategy_library, validator
from backtest_engine.strategy_safety_check import run_safety_check
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.verification_engine import run_verification
from backtest_engine.strategy_config import SLTPSpec
from ai_integration import deep_understanding, strategy_builder, self_correction

_WHITESPACE_RE = re.compile(r"\s+")
SETTINGS = {"initial_balance": 1000.0, "risk_pct": 1.0, "commission_pct": 0.1,
            "slippage_pct": 0.05, "position_size_pct": 10.0}


def _content_hash(text):
    normalized = _WHITESPACE_RE.sub(" ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _clear_cache(raw_text):
    h = _content_hash(raw_text)
    with storage.get_conn() as conn:
        conn.execute("DELETE FROM ai_import_cache WHERE content_hash = ?", (h,))


def _rule_summary(cfg):
    n_entry = len(cfg.entry_conditions) + len(cfg.long_entry_conditions) + len(cfg.short_entry_conditions)
    n_groups = len(cfg.entry_rule_groups)
    n_raw = sum(1 for name in ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                                "exit_conditions", "confirmation_conditions")
                for c in getattr(cfg, name) if c.type == "raw")
    n_raw += sum(1 for g in cfg.entry_rule_groups for c in (g.get("conditions") or []) if c.type == "raw")
    return f"entry_conditions={n_entry} entry_rule_groups={n_groups} raw_conditions_remaining={n_raw}"


def _demo_backtest(cfg):
    """Real evidence, not just 'no more validator errors' -- proves the
    rules actually produce trades. A demo-only clone gets a placeholder
    SL/TP if genuinely unspecified so run_backtest can execute; the SAVED
    strategy is never touched by this."""
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
        return f"{report['trade_count']} trades, verification={report['overall_status']}"
    except Exception as exc:
        return f"backtest error: {exc!r}"


def main():
    targets = [meta for meta in strategy_library.list_all()
               if validator.validate(strategy_library.load(meta["id"]))]
    print(f"Found {len(targets)} strategies in NEEDS_CLARIFICATION\n")

    results = []
    for meta in targets:
        sid, name = meta["id"], meta["name"]
        before_cfg = strategy_library.load(sid)
        print("=" * 78, flush=True)
        print(f"{name}  ({sid})", flush=True)
        print(f"  BEFORE: {_rule_summary(before_cfg)}", flush=True)
        print(f"  BEFORE validator errors ({len(validator.validate(before_cfg))}):", flush=True)
        for e in validator.validate(before_cfg):
            print(f"    - {e[:140]}", flush=True)
        before_bt = _demo_backtest(before_cfg)
        print(f"  BEFORE backtest: {before_bt}", flush=True)

        raw_text = before_cfg.raw_text
        if not raw_text or not raw_text.strip():
            print("  SKIPPED: no raw_text stored for this strategy -- cannot re-extract.", flush=True)
            results.append((name, sid, "skipped (no raw_text)", before_bt, "n/a"))
            continue

        _clear_cache(raw_text)  # force a genuinely fresh AI call, not a replay of the old broken one
        understanding = deep_understanding.understand_document_structured(
            raw_text, use_ai=True, content_type="strategy",
        )
        if understanding["result"] is None or not understanding["result"].get("strategy"):
            print(f"  AI RE-EXTRACTION FAILED: {understanding['error']}", flush=True)
            results.append((name, sid, "AI call failed", before_bt, understanding["error"]))
            continue

        provider = understanding["provider"]
        new_cfg = strategy_builder.build_strategy_config(understanding["result"]["strategy"], name, raw_text)
        new_cfg.name = name  # force exact original name -- guarantees save_version updates this SAME entry

        correction = self_correction.self_correct(new_cfg, use_ai=True)
        new_errors = validator.validate(new_cfg)
        safety = run_safety_check(new_cfg)

        print(f"  AI provider: {provider}", flush=True)
        print(f"  AFTER:  {_rule_summary(new_cfg)}", flush=True)
        print(f"  self_correction level={correction['level']} status={correction['status']}", flush=True)
        for r in correction["repairs"]:
            print(f"    repaired: {r[:160]}", flush=True)
        print(f"  AFTER validator errors ({len(new_errors)}):", flush=True)
        for e in new_errors:
            print(f"    - {e[:140]}", flush=True)
        print(f"  AFTER safety_check: {safety['status']}", flush=True)

        improved = len(new_errors) < len(validator.validate(before_cfg))
        if improved or (not new_errors and safety["passed"]):
            new_version = strategy_library.save_version(sid, new_cfg)
            print(f"  SAVED as version {new_version}", flush=True)
        else:
            print("  NOT SAVED -- re-extraction did not improve on the current version.", flush=True)

        after_bt = _demo_backtest(new_cfg)
        print(f"  AFTER backtest: {after_bt}", flush=True)
        results.append((name, sid, f"{len(new_errors)} validator errors, safety={safety['status']}", before_bt, after_bt))

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for name, sid, outcome, before_bt, after_bt in results:
        print(f"{name:<48} before=[{before_bt}]  after=[{after_bt}]  ({outcome})")


if __name__ == "__main__":
    main()

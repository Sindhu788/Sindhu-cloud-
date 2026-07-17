"""Part 3 (pre-backtest sanity check): before committing to an expensive
full-universe backtest (whether triggered manually via /api/backtesting/run
or automatically via the automation pipeline), run the strategy against a
tiny sample -- a couple of coins, a short recent date range -- first.

If that sample produces 0 trades AND at least one entry/confirmation
condition never fired even once across the whole sample (the same
"structurally can never work" signature Part 1 fixed for specific known
bugs -- a missing timeframe, a concepts_used gap, a mathematically
impossible combination of thresholds), stop here instead of burning a full
50-coin run only to discover it was broken from the start.

If the sample produces 0 trades but every entry/confirmation condition DID
fire individually (just never all together on the same bar), that's a
legitimately strict combination, not a structural defect -- the strategy
proceeds to the full run as normal, since "few or no trades in a short
sample" is expected behavior for a selective strategy, not a bug.
"""
import time

from backtest_engine import diagnostics
from backtest_engine.mtf_worker import run_one_symbol

SAMPLE_SYMBOL_COUNT = 2
SAMPLE_WINDOW_DAYS = 14
SAMPLE_WINDOW_MS = SAMPLE_WINDOW_DAYS * 24 * 60 * 60 * 1000


def run_sanity_check(config_dict, exchange, symbols, settings):
    """Returns {"ok": bool, "reason": str|None, "diagnosis": str|None,
    "trades_found": int, "symbols_checked": list[str]}.

    Never raises -- a data/setup failure on the sample (e.g. no candle data
    for these specific coins yet) is not a verdict on the strategy's logic
    either way, so it's treated as inconclusive (ok=True) and left for the
    full run to surface properly per-coin, exactly like it already does."""
    sample_symbols = list(symbols[:SAMPLE_SYMBOL_COUNT]) if symbols else []
    if not sample_symbols:
        return {"ok": True, "reason": None, "diagnosis": None, "trades_found": 0, "symbols_checked": []}

    end_ms = settings.get("end_ms") or int(time.time() * 1000)
    start_ms = settings.get("start_ms")
    sample_start_ms = max(start_ms, end_ms - SAMPLE_WINDOW_MS) if start_ms else end_ms - SAMPLE_WINDOW_MS

    total_trades = 0
    structural_diagnosis = None
    for symbol in sample_symbols:
        try:
            result = run_one_symbol(config_dict, exchange, symbol, settings, sample_start_ms, end_ms)
        except Exception:
            continue
        if result.get("status") != "completed":
            continue

        trades = result.get("trades") or []
        total_trades += len(trades)
        if trades:
            continue

        report = result.get("condition_report")
        if not report:
            continue
        never_fired = [pc for pc in (report.get("per_condition") or []) if pc["true_bars"] == 0]
        if never_fired and report.get("total_bars", 0) > 0:
            structural_diagnosis = diagnostics.plain_language_diagnosis(report)

    if total_trades == 0 and structural_diagnosis:
        return {
            "ok": False,
            "reason": (
                f"Sanity check on {', '.join(sample_symbols)} (last {SAMPLE_WINDOW_DAYS} days) produced "
                f"0 trades because of a structural issue, not just a strict or rare setup -- stopping "
                f"before the full backtest."
            ),
            "diagnosis": structural_diagnosis,
            "trades_found": 0,
            "symbols_checked": sample_symbols,
        }

    return {
        "ok": True, "reason": None, "diagnosis": None,
        "trades_found": total_trades, "symbols_checked": sample_symbols,
    }

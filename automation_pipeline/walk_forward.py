"""Walk-Forward Testing: checks whether a strategy's parameters are
genuinely good, or just overfit to the historical data they were tuned
on.

WHY THIS EXISTS: automation_pipeline.optimizer already re-tunes a
strategy's own numeric parameters (Part 2.2), then validates the winner
on the FULL historical range. That full-range validation still doesn't
prove the parameters generalize -- a strategy tuned to fit whatever
happened in the past can look great on that same past without ever
proving it would have worked on data it hadn't seen yet. That is
"overfitting," and it's the single most common way a backtest lies.

HOW: the strategy's own historical data (for one representative symbol)
is split CHRONOLOGICALLY -- never shuffled, since this is specifically
checking behavior on FUTURE-relative-to-training data -- into a Training
Period (the first TRAIN_FRACTION, default 70%) and a Testing Period (the
remaining, most recent slice). Parameters are optimized (reusing
automation_pipeline.optimizer.optimize() exactly as-is, just pointed at
the Training Period's date range instead of "the last 30 days") using
ONLY the Training Period. Those exact winning parameters are then scored
on BOTH periods independently -- Training (in-sample) and Testing
(out-of-sample, data the optimizer never touched) -- and the two are
compared.

VERDICT RULE (a genuine judgment call, not a fact -- disclosed here for
the CEO to challenge or retune, not hidden inside the code):
  - FAIL if training itself wasn't profitable at all (nothing to confirm
    out-of-sample), or if either period traded too few times to judge
    (MIN_TRADES_FOR_VERDICT), or if the testing period lost money outright
    despite a profitable training period (the clearest overfitting
    signature).
  - Otherwise: "Walk-Forward Efficiency" = testing profit% / training
    profit%. PASS if WFE >= WFE_PASS_THRESHOLD (default 50% -- the
    testing period kept at least half of the training period's edge),
    FAIL otherwise.
These thresholds (MIN_TRADES_FOR_VERDICT=3, WFE_PASS_THRESHOLD=0.5) are
this module's own defaults, not numbers the CEO specified -- flagged
explicitly rather than silently assumed permanent.

SCOPE: reuses the existing Backtest Engine (via optimizer._run_in_memory,
itself a thin wrapper over ConfiguredStrategy + engine.run_backtest) and
the existing Auto-Optimizer completely unmodified -- this module adds a
new, independent check ON TOP of them, it does not change how either
works for anyone who isn't calling THIS module.
"""

from datetime import datetime, timezone

from automation_pipeline import optimizer
from data_engine import storage

TRAIN_FRACTION = 0.70
MIN_TRADES_FOR_VERDICT = 3
WFE_PASS_THRESHOLD = 0.5  # testing period must retain >= 50% of training period's return


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ms_to_iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def compute_split(exchange, symbol, train_fraction=TRAIN_FRACTION):
    """Chronological (never shuffled) train/test boundary for `symbol`'s
    OWN available 1-minute history. Returns None if no data exists yet."""
    min_ms, max_ms = storage.get_symbol_time_bounds(exchange, symbol)
    if min_ms is None or max_ms is None or max_ms <= min_ms:
        return None
    split_ms = min_ms + int((max_ms - min_ms) * train_fraction)
    return {
        "train_start_ms": min_ms, "train_end_ms": split_ms,
        "test_start_ms": split_ms, "test_end_ms": max_ms,
    }


def _metrics_summary(m):
    if m is None:
        return None
    return {
        "total_trades": m["total_trades"], "win_rate": m["win_rate"],
        "profit_pct": m["profit_pct"], "net_profit": m["net_profit"],
        "profit_factor": m["profit_factor"], "max_drawdown_pct": m["max_drawdown_pct"],
    }


def _verdict(training, testing):
    """Returns (status, reason). status is one of PASS/FAIL/INCONCLUSIVE."""
    if training is None or testing is None:
        return "INCONCLUSIVE", (
            "Could not compute results for one of the two periods (most likely no candle data covers "
            "that date range yet)."
        )
    if training["total_trades"] < MIN_TRADES_FOR_VERDICT or testing["total_trades"] < MIN_TRADES_FOR_VERDICT:
        return "INCONCLUSIVE", (
            f"Too few trades to judge robustness (training: {training['total_trades']}, "
            f"testing: {testing['total_trades']}; need at least {MIN_TRADES_FOR_VERDICT} in each)."
        )
    if training["profit_pct"] <= 0:
        return "FAIL", (
            f"Not profitable even in the training period ({training['profit_pct']}% return) -- there is no "
            f"real edge here to confirm out-of-sample in the first place."
        )
    if testing["profit_pct"] <= 0:
        return "FAIL", (
            f"Profitable in training ({training['profit_pct']}% return) but LOST money in testing "
            f"({testing['profit_pct']}% return) -- the classic overfitting signature: performance did not "
            f"survive on data the optimizer never saw."
        )
    wfe = testing["profit_pct"] / training["profit_pct"]
    if wfe >= WFE_PASS_THRESHOLD:
        return "PASS", (
            f"Testing period retained {wfe * 100:.0f}% of the training period's return "
            f"({testing['profit_pct']}% vs {training['profit_pct']}%) -- performance held up on unseen data."
        )
    return "FAIL", (
        f"Testing period only retained {wfe * 100:.0f}% of the training period's return "
        f"({testing['profit_pct']}% vs {training['profit_pct']}%), below the {WFE_PASS_THRESHOLD * 100:.0f}% "
        f"bar -- a big enough drop to suggest the parameters were tuned to fit the training period specifically."
    )


def run_walk_forward_test(config, exchange, symbol, settings, train_fraction=TRAIN_FRACTION,
                           log_fn=None, control=None):
    """Runs the full Training -> Testing walk-forward check for one
    strategy config against one symbol's own history. Never mutates
    `config` in place (the optimizer already clones candidates
    internally) and never writes anything to the strategy library --
    saving the result is the caller's job (see
    backtest_engine.strategy_library.save_walk_forward_result).

    Returns a fully self-describing result dict: {"status", "reason",
    "symbol", "exchange", "train_fraction", "optimized_params",
    "train_period": {"start","end"}, "test_period": {"start","end"},
    "training_metrics", "testing_metrics", "tested_at"}."""
    log = log_fn or (lambda msg: None)

    split = compute_split(exchange, symbol, train_fraction)
    if split is None:
        return {
            "status": "ERROR", "reason": f"No historical candle data is available for {symbol} on {exchange} yet.",
            "symbol": symbol, "exchange": exchange, "train_fraction": train_fraction,
            "tested_at": _now_iso(),
        }

    log(f"Walk-Forward Test: splitting {symbol}'s available history chronologically -- "
        f"first {train_fraction * 100:.0f}% for training, last {(1 - train_fraction) * 100:.0f}% for testing.")
    log(f"  Training period: {_ms_to_iso(split['train_start_ms'])} -> {_ms_to_iso(split['train_end_ms'])}")
    log(f"  Testing period:  {_ms_to_iso(split['test_start_ms'])} -> {_ms_to_iso(split['test_end_ms'])}")

    log("Optimizing parameters using ONLY the training period -- the testing period is never shown to the optimizer.")
    best_candidate, _tried, best_desc = optimizer.optimize(
        config, exchange, symbol, dict(settings),
        split["train_start_ms"], split["train_end_ms"],
        log_fn=log, control=control,
    )
    winning_config = best_candidate if best_candidate is not None else config
    if best_candidate is not None:
        log(f"Best training-period combination: {best_desc}")
    else:
        log("No combination beat the strategy's own original settings on the training period -- "
            "using the original settings for both periods.")

    log("Scoring the winning parameters on the TRAINING period (in-sample)...")
    training_metrics = optimizer._run_in_memory(
        winning_config, exchange, symbol, settings, split["train_start_ms"], split["train_end_ms"],
    )
    log("Scoring the SAME parameters on the TESTING period -- data the optimizer never saw (out-of-sample)...")
    testing_metrics = optimizer._run_in_memory(
        winning_config, exchange, symbol, settings, split["test_start_ms"], split["test_end_ms"],
    )

    training_summary = _metrics_summary(training_metrics)
    testing_summary = _metrics_summary(testing_metrics)
    status, reason = _verdict(training_summary, testing_summary)
    log(f"Walk-Forward verdict: {status} -- {reason}")

    return {
        "status": status, "reason": reason,
        "symbol": symbol, "exchange": exchange, "train_fraction": train_fraction,
        "optimized_params": best_desc,
        "train_period": {"start": _ms_to_iso(split["train_start_ms"]), "end": _ms_to_iso(split["train_end_ms"])},
        "test_period": {"start": _ms_to_iso(split["test_start_ms"]), "end": _ms_to_iso(split["test_end_ms"])},
        "training_metrics": training_summary,
        "testing_metrics": testing_summary,
        "tested_at": _now_iso(),
    }

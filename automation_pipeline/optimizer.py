"""Math-based, deterministic parameter optimizer (Part 2.2). Never calls
any AI provider and never consumes AI tokens -- it only re-runs the
existing, already-deterministic backtest engine against small variations
of a strategy's OWN already-configured numeric/tunable parameters
(indicator lookback periods, stop-loss %, take-profit RR, risk % per
trade, session filter, and confirmation "strictness" via concept
lookback_bars). It never touches entry/exit logic, adds/removes
indicators, or changes which concepts the strategy uses -- only the
numbers already present on those same fields.

Search strategy: one-dimension-at-a-time coordinate search (hold every
other field at the strategy's own baseline value, vary one dimension
across a small candidate grid), screened cheaply against ONE symbol over
a short recent window using in-memory backtests (no database writes --
see _run_in_memory below), then the single best-scoring candidate is
handed back to the caller for a full-dataset validation pass (every coin,
the same date range as the original backtest) before it's ever trusted,
specifically to avoid overfitting to the narrow fast-subset slice."""

from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.engine import run_backtest
from backtest_engine.metrics import compute_metrics
from backtest_engine.strategy_config import StrategyConfig

MIN_TRADES_FOR_SCORE = 5  # fewer trades than this on the fast subset -> not trusted, scored as -inf


def _clone_config(config):
    return StrategyConfig.from_dict(config.to_dict())


def _run_in_memory(config, exchange, symbol, settings, start_ms, end_ms):
    """One symbol, in-memory only -- no batch/results/trades rows written
    to the database. This is what makes fast-subset screening of a dozen-
    plus candidates actually fast; only the final full-dataset validation
    pass (done by the caller via the normal runner.run_mtf_batch) persists
    anything.

    backtest_engine.engine.run_backtest reads position-sizing risk % from
    the `settings` dict (settings["risk_pct"]), NOT from config.risk_pct --
    the same split sindhu_web/api/backtesting.py's manual "Run Backtest"
    bridges via `req.risk_pct or cfg.risk_pct`. Without re-deriving it here
    too, the risk_pct tunable dimension would silently vary a field the
    engine never actually reads, and every risk_pct candidate would score
    identically to the baseline."""
    run_settings = dict(settings)
    if config.risk_pct is not None:
        run_settings["risk_pct"] = config.risk_pct

    strategy = ConfiguredStrategy(config)
    ctx = MultiTimeframeContext(exchange, symbol, config.timeframes, start_ms, end_ms)
    if ctx.is_empty():
        return None
    merged = strategy.prepare_context(ctx)
    trades, equity_curve, _final_balance = run_backtest(merged, strategy, run_settings)
    return compute_metrics(trades, equity_curve, settings["initial_balance"])


def _score(metrics):
    """profit_pct (not raw pnl) so candidates are comparable regardless of
    position sizing quirks; a hard floor on trade count so a candidate
    that just happens to take 1-2 lucky trades on the fast subset can't
    look artificially great."""
    if metrics is None or metrics["total_trades"] < MIN_TRADES_FOR_SCORE:
        return float("-inf")
    return metrics["profit_pct"]


def tunable_dimensions(config):
    """Every numeric/tunable dimension found on this strategy's OWN
    already-configured fields, each as {id, description, baseline,
    candidates, apply(config, value)}. A strategy with none of these
    fields set (e.g. no period-based indicators, no fixed_pct SL, no rr
    TP) simply yields fewer dimensions -- never invents a parameter that
    wasn't already there."""
    dims = []

    for idx, ind in enumerate(config.indicators):
        period = (ind.get("params") or {}).get("period")
        if not period:
            continue
        base = int(period)
        candidates = sorted({max(2, round(base * f)) for f in (0.5, 0.75, 1.0, 1.5, 2.0)})
        if len(candidates) < 2:
            continue

        def _apply(cfg, value, _idx=idx):
            cfg.indicators[_idx]["params"]["period"] = value
            return cfg

        dims.append({
            "id": f"indicator_{ind['name']}_{idx}_period",
            "description": f"{ind['name']} lookback period (currently {base})",
            "baseline": base, "candidates": candidates, "apply": _apply,
        })

    if config.take_profit.type == "rr" and config.take_profit.value:
        base = round(config.take_profit.value, 3)
        candidates = sorted({v for v in (1.5, 2.0, 2.5, 3.0, base)})

        def _apply(cfg, value):
            cfg.take_profit.value = value
            cfg.risk_reward = value
            return cfg

        dims.append({"id": "take_profit_rr", "description": f"take-profit risk:reward (currently {base})",
                      "baseline": base, "candidates": candidates, "apply": _apply})

    if config.stop_loss.type == "fixed_pct" and config.stop_loss.value:
        base = round(config.stop_loss.value, 3)
        candidates = sorted({round(base * f, 3) for f in (0.5, 0.75, 1.0, 1.5, 2.0)})

        def _apply(cfg, value):
            cfg.stop_loss.value = value
            return cfg

        dims.append({"id": "stop_loss_pct", "description": f"stop-loss % (currently {base})",
                      "baseline": base, "candidates": candidates, "apply": _apply})

    if config.risk_pct:
        base = round(config.risk_pct, 3)
        candidates = sorted({v for v in (0.5, 1.0, 1.5, 2.0, base)})

        def _apply(cfg, value):
            cfg.risk_pct = value
            return cfg

        dims.append({"id": "risk_pct", "description": f"risk % per trade (currently {base})",
                      "baseline": base, "candidates": candidates, "apply": _apply})

    base_sessions = tuple(sorted(config.session_filter or []))
    session_options = [(), ("london",), ("ny",), ("asian",), ("london", "ny")]
    if base_sessions not in session_options:
        session_options.append(base_sessions)
    if len(session_options) > 1:
        def _apply(cfg, value):
            cfg.session_filter = list(value)
            return cfg

        dims.append({"id": "session_filter", "description": f"session filter (currently {list(base_sessions) or 'none'})",
                      "baseline": base_sessions, "candidates": session_options, "apply": _apply})

    all_conditions = config.entry_conditions + config.exit_conditions + config.confirmation_conditions
    concept_conditions = [c for c in all_conditions if c.type == "concept"]
    if concept_conditions:
        current = concept_conditions[0].lookback_bars or 10
        candidates = sorted({v for v in (5, 10, 15, 20, current)})
        if len(candidates) > 1:
            def _apply(cfg, value):
                for c in cfg.entry_conditions + cfg.exit_conditions + cfg.confirmation_conditions:
                    if c.type == "concept":
                        c.lookback_bars = value
                return cfg

            dims.append({"id": "confirmation_lookback_bars",
                          "description": f"confirmation strictness / lookback bars (currently {current})",
                          "baseline": current, "candidates": candidates, "apply": _apply})

    return dims


def optimize(config, exchange, screen_symbol, settings, start_ms, end_ms, log_fn=None):
    """Pure grid/coordinate search, deterministic, zero AI calls. Returns
    (best_candidate_config_or_None, tried_log, best_description_or_None).
    `tried_log` is a JSON-serializable list of every combination tried
    with its fast-subset score, for full transparency (Part 2.2's "clearly
    log what parameters were tried")."""
    log = log_fn or (lambda msg: None)
    dims = tunable_dimensions(config)
    if not dims:
        log("No tunable numeric parameters found on this strategy (no period-based indicators, "
            "fixed stop-loss %, RR take-profit, risk %, session filter, or concept lookback) -- skipping optimization.")
        return None, [], None

    tried = []
    baseline_metrics = _run_in_memory(config, exchange, screen_symbol, settings, start_ms, end_ms)
    baseline_score = _score(baseline_metrics)
    tried.append({
        "dimension": "baseline", "description": "original strategy, unmodified", "value": None,
        "score": baseline_score if baseline_score != float("-inf") else None,
        "trades": baseline_metrics["total_trades"] if baseline_metrics else 0,
    })
    log(f"Fast-subset baseline on {screen_symbol}: "
        f"{'score (profit%) = ' + str(baseline_score) if baseline_score != float('-inf') else 'not enough trades to score'} "
        f"({baseline_metrics['total_trades'] if baseline_metrics else 0} trades).")

    best_candidate, best_score, best_desc = None, baseline_score, None
    for dim in dims:
        for value in dim["candidates"]:
            if value == dim["baseline"]:
                continue
            candidate_config = _clone_config(config)
            dim["apply"](candidate_config, value)
            metrics = _run_in_memory(candidate_config, exchange, screen_symbol, settings, start_ms, end_ms)
            score = _score(metrics)
            tried.append({
                "dimension": dim["id"], "description": dim["description"], "value": value,
                "score": score if score != float("-inf") else None,
                "trades": metrics["total_trades"] if metrics else 0,
            })
            log(f"Tried {dim['id']} = {value}: "
                f"{'score (profit%) = ' + str(score) if score != float('-inf') else 'not enough trades to score'}.")
            if score > best_score:
                best_score, best_candidate, best_desc = score, candidate_config, f"{dim['description']} -> {value}"

    if best_candidate is None:
        log("No variation beat the baseline on the fast subset -- keeping the original strategy as-is.")
        return None, tried, None

    log(f"Best fast-subset candidate: {best_desc} (score {best_score} vs baseline "
        f"{baseline_score if baseline_score != float('-inf') else 'N/A'}). Validating on the full dataset next.")
    return best_candidate, tried, best_desc

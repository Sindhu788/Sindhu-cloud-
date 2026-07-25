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

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.mtf_context import MultiTimeframeContext
from backtest_engine.engine import run_backtest
from backtest_engine.metrics import compute_metrics
from backtest_engine.strategy_config import StrategyConfig

MIN_TRADES_FOR_SCORE = 5  # fewer trades than this on the fast subset -> not trusted, scored as -inf

# Part 4 (reliability): a single fast-subset candidate is normally a few
# seconds (one symbol, ~30 days). If one candidate's data/computation ever
# stalls (corrupt candle gap, pathological indicator params), this bounds
# how long the whole pipeline can be blocked by it -- the candidate is
# skipped (scored as unusable) and the optimizer moves on, rather than the
# CEO seeing the "optimizing" stage frozen forever with no way to tell if
# it's still working or dead.
_CANDIDATE_TIMEOUT_SECONDS = 90


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


def _run_in_memory_bounded(config, exchange, symbol, settings, start_ms, end_ms, log):
    """Same as _run_in_memory but wrapped with a hard wall-clock timeout
    (see _CANDIDATE_TIMEOUT_SECONDS) so one bad candidate can never silently
    hang the whole optimization stage. Returns None (treated as "not enough
    trades to score", i.e. skipped) on timeout or any unexpected error --
    never raises, since a single candidate failing is not a reason to abort
    the rest of the grid search.

    Deliberately does NOT use `with ThreadPoolExecutor(...) as executor:` --
    that context manager calls shutdown(wait=True) on exit, which would
    block until the timed-out thread actually finishes, silently defeating
    the whole point of the timeout. shutdown(wait=False) below lets a
    genuinely hung candidate's thread finish in the background (or leak
    harmlessly until process exit) while this function returns immediately."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_run_in_memory, config, exchange, symbol, settings, start_ms, end_ms)
    try:
        return future.result(timeout=_CANDIDATE_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        log(f"Candidate timed out after {_CANDIDATE_TIMEOUT_SECONDS}s on {symbol} -- skipped.")
        return None
    except Exception as exc:
        log(f"Candidate raised an error ({exc!r}) -- skipped.")
        return None
    finally:
        executor.shutdown(wait=False)


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

    # Candidate grids widened (Part 0) from ~5 values/dimension to ~10-11 so
    # a full-featured strategy's coordinate search tries roughly 50
    # combinations total instead of ~11 -- purely a wider net over the same
    # tunable fields, same one-dimension-at-a-time algorithm, same fast-
    # subset-then-full-validate safety pattern below (unchanged).
    _PERIOD_FACTORS = (0.4, 0.5, 0.6, 0.75, 0.85, 1.0, 1.15, 1.25, 1.5, 1.75, 2.0)

    for idx, ind in enumerate(config.indicators):
        period = (ind.get("params") or {}).get("period")
        if not period:
            continue
        base = int(period)
        ind_name, ind_role = ind["name"], ind.get("role")
        candidates = sorted({max(2, round(base * f)) for f in _PERIOD_FACTORS})
        if len(candidates) < 2:
            continue

        def _apply(cfg, value, _idx=idx, _name=ind_name, _role=ind_role, _old_period=base):
            cfg.indicators[_idx]["params"]["period"] = value
            # Real bug fixed live (found via a Walk-Forward Test run):
            # a Condition can carry its OWN period directly in its params
            # dict (e.g. price_compare: {"indicator": "ema", "params":
            # {"period": 50}, "role": "trend"}) rather than leaving it
            # None to inherit from this indicators-list entry --
            # ConfiguredStrategy._indicator_column() resolves the column
            # using the CONDITION's own params first. Mutating only
            # cfg.indicators[_idx] left every such condition still
            # pointing at the OLD period, silently resolving to a column
            # that was never computed (the new period was only declared
            # in `indicators`, not on the condition), so the condition's
            # _eval() always returned False -- EVERY candidate for this
            # dimension silently produced 0 trades and could never be
            # discovered as an improvement, no matter how good it
            # actually was. Confirmed live on EMA Trend-Pullback Strategy:
            # 20/20 period candidates showed "0 trades" until this fix.
            for bucket in (cfg.entry_conditions, cfg.long_entry_conditions, cfg.short_entry_conditions,
                           cfg.exit_conditions, cfg.confirmation_conditions):
                for cond in bucket:
                    if cond.indicator == _name and cond.role == _role and cond.params.get("period") == _old_period:
                        cond.params["period"] = value
                    if cond.indicator2 == _name and cond.role == _role and cond.params2.get("period") == _old_period:
                        cond.params2["period"] = value
            for group in cfg.entry_rule_groups:
                for cond in group.get("conditions") or []:
                    if cond.indicator == _name and cond.role == _role and cond.params.get("period") == _old_period:
                        cond.params["period"] = value
                    if cond.indicator2 == _name and cond.role == _role and cond.params2.get("period") == _old_period:
                        cond.params2["period"] = value
            return cfg

        dims.append({
            "id": f"indicator_{ind['name']}_{idx}_period",
            "description": f"{ind['name']} lookback period (currently {base})",
            "baseline": base, "candidates": candidates, "apply": _apply,
        })

    if config.take_profit.type == "rr" and config.take_profit.value:
        base = round(config.take_profit.value, 3)
        candidates = sorted({v for v in (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0, base)})

        def _apply(cfg, value):
            cfg.take_profit.value = value
            cfg.risk_reward = value
            return cfg

        dims.append({"id": "take_profit_rr", "description": f"take-profit risk:reward (currently {base})",
                      "baseline": base, "candidates": candidates, "apply": _apply})

    if config.stop_loss.type == "fixed_pct" and config.stop_loss.value:
        base = round(config.stop_loss.value, 3)
        candidates = sorted({round(base * f, 3) for f in _PERIOD_FACTORS})

        def _apply(cfg, value):
            cfg.stop_loss.value = value
            return cfg

        dims.append({"id": "stop_loss_pct", "description": f"stop-loss % (currently {base})",
                      "baseline": base, "candidates": candidates, "apply": _apply})

    if config.risk_pct:
        base = round(config.risk_pct, 3)
        candidates = sorted({v for v in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, base)})

        def _apply(cfg, value):
            cfg.risk_pct = value
            return cfg

        dims.append({"id": "risk_pct", "description": f"risk % per trade (currently {base})",
                      "baseline": base, "candidates": candidates, "apply": _apply})

    base_sessions = tuple(sorted(config.session_filter or []))
    session_options = [
        (), ("london",), ("ny",), ("asian",),
        ("london", "ny"), ("london", "asian"), ("ny", "asian"), ("london", "ny", "asian"),
    ]
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
        candidates = sorted({v for v in (3, 5, 7, 10, 12, 15, 18, 20, 25, 30, current)})
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


def _plain_score(score, trades):
    if score == float("-inf"):
        return f"not enough trades yet ({trades}) to judge this one"
    sign = "profit" if score >= 0 else "loss"
    return f"{trades} trades, {abs(round(score, 2))}% {sign}"


def optimize(config, exchange, screen_symbol, settings, start_ms, end_ms, log_fn=None, control=None, progress_cb=None):
    """Pure grid/coordinate search, deterministic, zero AI calls. Returns
    (best_candidate_config_or_None, tried_log, best_description_or_None).
    `tried_log` is a JSON-serializable list of every combination tried
    with its fast-subset score, for full transparency (Part 2.2's "clearly
    log what parameters were tried").

    `control` (Part 4, reliability): the same DownloadControl the pipeline
    job was created with -- checked between every candidate so hitting
    "Stop" on the job actually interrupts optimization promptly instead of
    grinding through the rest of the grid regardless. Each candidate itself
    is also individually bounded (_run_in_memory_bounded) so one pathological
    candidate can't hang the whole stage even without a Stop click.

    `progress_cb(tried_so_far, total_candidates)` (Part 4, plain-language
    live logs): called after every candidate (including the baseline) so
    the caller can show a live "(N/M combinations tried)" counter instead
    of a bare "optimizing" status with no sense of progress or whether it's
    still alive."""
    log = log_fn or (lambda msg: None)
    dims = tunable_dimensions(config)
    if not dims:
        log("This strategy has no tunable numeric settings to experiment with (no period-based "
            "indicators, fixed stop-loss %, risk:reward target, risk %, session filter, or "
            "confirmation strictness) -- skipping the optimization step and keeping it as-is.")
        return None, [], None

    total_candidates = 1 + sum(1 for dim in dims for value in dim["candidates"] if value != dim["baseline"])
    tried_so_far = 0

    def _report_progress():
        if progress_cb:
            progress_cb(tried_so_far, total_candidates)

    tried = []
    baseline_metrics = _run_in_memory_bounded(config, exchange, screen_symbol, settings, start_ms, end_ms, log)
    baseline_score = _score(baseline_metrics)
    tried.append({
        "dimension": "baseline", "description": "original strategy, unmodified", "value": None,
        "score": baseline_score if baseline_score != float("-inf") else None,
        "trades": baseline_metrics["total_trades"] if baseline_metrics else 0,
    })
    tried_so_far += 1
    _report_progress()
    log(f"Starting point (on {screen_symbol}, recent data only): "
        f"{_plain_score(baseline_score, baseline_metrics['total_trades'] if baseline_metrics else 0)}. "
        f"This is the score every other combination has to beat.")

    best_candidate, best_score, best_desc = None, baseline_score, None
    stopped_early = False
    for dim in dims:
        if control and control.should_stop():
            stopped_early = True
            break
        for value in dim["candidates"]:
            if value == dim["baseline"]:
                continue
            if control and control.should_stop():
                stopped_early = True
                break
            candidate_config = _clone_config(config)
            dim["apply"](candidate_config, value)
            metrics = _run_in_memory_bounded(candidate_config, exchange, screen_symbol, settings, start_ms, end_ms, log)
            score = _score(metrics)
            tried.append({
                "dimension": dim["id"], "description": dim["description"], "value": value,
                "score": score if score != float("-inf") else None,
                "trades": metrics["total_trades"] if metrics else 0,
            })
            tried_so_far += 1
            _report_progress()
            trades_n = metrics["total_trades"] if metrics else 0
            beat_note = " -- new best so far!" if score > best_score else ""
            log(f"[{tried_so_far}/{total_candidates}] Tried {dim['description']} -> {value}: "
                f"{_plain_score(score, trades_n)}{beat_note}")
            if score > best_score:
                best_score, best_candidate, best_desc = score, candidate_config, f"{dim['description']} -> {value}"
        if stopped_early:
            break

    if stopped_early:
        log(f"Stopped early by request after {tried_so_far}/{total_candidates} combinations -- "
            f"using the best one found so far, if any beat the original.")

    if best_candidate is None:
        log("None of the combinations tried beat the original -- keeping the strategy exactly as imported.")
        return None, tried, None

    log(f"Best combination found: {best_desc} ({round(best_score, 2)}% vs "
        f"{'N/A' if baseline_score == float('-inf') else round(baseline_score, 2)}% for the original). "
        f"Now double-checking it on the full history for every coin, not just the quick sample.")
    return best_candidate, tried, best_desc

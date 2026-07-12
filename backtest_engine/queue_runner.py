"""Runs multiple strategies one after another. Each queue item becomes its
own batch (via run_mtf_batch), so pausing/stopping/resuming works exactly
the same as a single strategy -- the queue itself just decides what to run
next."""

from data_engine.logging_setup import log as default_log
from backtest_engine.runner import run_mtf_batch


def run_queue(items, exchange, log=default_log, control=None,
              queue_progress_cb=None, progress_cb=None, trade_cb=None,
              use_multiprocessing=True):
    """items: list of dicts, each with keys:
        config (StrategyConfig), symbols (list[str]), settings (dict),
        start_ms, end_ms (optional), batch_id (optional, to resume one item)

    queue_progress_cb(index, total, strategy_name) reports queue-level
    position; progress_cb/trade_cb are forwarded into each item's batch run.

    Returns a list of {"strategy": name, "batch_id": ...} in run order.
    """
    results = []
    total = len(items)

    for i, item in enumerate(items, start=1):
        if control and control.should_stop():
            log("Queue stopped by user.")
            break

        config = item["config"]
        if queue_progress_cb:
            queue_progress_cb(i, total, config.name)
        log(f"Queue [{i}/{total}]: {config.name}")

        batch_id = run_mtf_batch(
            config, exchange, item["symbols"], item["settings"],
            start_ms=item.get("start_ms"), end_ms=item.get("end_ms"),
            batch_id=item.get("batch_id"), log=log, control=control,
            progress_cb=progress_cb, trade_cb=trade_cb,
            use_multiprocessing=use_multiprocessing,
        )
        results.append({"strategy": config.name, "batch_id": batch_id})

    return results

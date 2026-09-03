"""Master Task 3, Phase 0.8f: One-Click Health Check -- a small "Test
Everything" self-check the CEO can run from the dashboard without digging
through logs, especially useful on the cloud deploy where there is no
terminal to watch.

Deliberately reuses existing primitives only (storage.get_conn, the engine's
own status(), the same exchange client the engine's own tick loop already
uses) -- no new dependency, no new background thread, runs synchronously in
well under a second per check.
"""

from datetime import datetime, timezone

from data_engine import storage, config as base_config
from data_engine.exchanges.registry import get_exchange_client
from paper_trading.engine import engine, _default_exchange


def _check_database():
    try:
        with storage.get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"name": "Database connection", "ok": True, "detail": "reachable"}
    except Exception as e:
        return {"name": "Database connection", "ok": False, "detail": str(e)}


def _check_engine_state():
    try:
        status = engine.status()
        if not status["running"]:
            return {"name": "Paper Trading engine", "ok": True, "detail": "stopped (not an error -- CEO's own choice)"}
        return {"name": "Paper Trading engine", "ok": True, "detail": f"running, last tick at {status['last_tick_at']}"}
    except Exception as e:
        return {"name": "Paper Trading engine", "ok": False, "detail": str(e)}


def _check_last_candle_fetch():
    try:
        exchange = _default_exchange()
        client = get_exchange_client(exchange)
        coins_cfg = base_config.load_or_seed("coins.json", base_config.DEFAULTS["coins.json"])
        tickers = client.get_tickers(coins_cfg["quote_asset"])
        if not tickers:
            return {"name": "Live candle/ticker fetch", "ok": False, "detail": f"{exchange} returned no tickers"}
        return {"name": "Live candle/ticker fetch", "ok": True, "detail": f"{exchange} returned {len(tickers)} tickers"}
    except Exception as e:
        return {"name": "Live candle/ticker fetch", "ok": False, "detail": str(e)}


def run_health_check():
    checks = [_check_database(), _check_engine_state(), _check_last_candle_fetch()]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "all_ok": all(c["ok"] for c in checks),
        "checks": checks,
    }

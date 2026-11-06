"""Master plan A17 (P38 + P39): startup self-check and config validation, shown on the public /health/details (no secrets).

- Config validation: every saved paper-trading setting through the existing validator (paper_trading.config.validate_update, which only
  rejects nonsensical values) plus MAIN_WALLET limits. Invalid -> NEW trading is refused with a clear reason; the web app, /health and
  the dashboard keep working, open positions keep their stops (the existing monitor). Re-checked at most once a minute.
- Self-check (background thread at startup, then on demand): database reachable, exchange reachable and clock skew vs the exchange's
  server time, Telegram token valid (getMe: reads the bot's own name; NO message is sent), data folder writable.
- safe_config_summary(): whitelisted non-secret values only (numbers, on/off flags) and its SHA-256, for local/Cloud parity (A22).
Never raises.
"""
import hashlib
import json
import os
import tempfile
import threading
import time

_lock = threading.Lock()
_state = {"config_checked_at": 0.0, "config_errors": {}, "self_check": None, "self_check_at": None}
_SAFE_PT_KEYS = ("dry_run", "engine_enabled", "risk_pct_default", "commission_pct", "max_open_trades", "max_portfolio_risk_pct_per_coin",
                 "max_open_positions_per_coin", "cooldown_minutes", "opposite_signal_policy", "coin_filter_top_n", "coin_filter_mode",
                 "tick_interval_seconds", "lookback_days", "drawdown_pause_streak_threshold", "drawdown_pause_pct_threshold",
                 "account_drawdown_pause_pct_threshold", "cooling_off_loss_streak", "cooling_off_hours")
_SAFE_TG_KEYS = ("master_send_enabled", "auto_send_enabled", "auto_send_high_confidence_only", "auto_send_min_confluence_ratio",
                 "auto_send_min_confluence_count", "channel_group_filter")
_FLAG_ENVS = ("SINDHU_PUBLIC_SIGNALS", "SINDHU_RESEARCH_ONLY_TIMEFRAMES", "SINDHU_BLOCK_OPPOSITE_SIGNAL", "SINDHU_MAX_TARGET_STOP_RATIO",
              "SINDHU_HIDE_CONFIDENCE", "SINDHU_CANDLE_FINGERPRINT", "SINDHU_GATE_USE_POSITION_EXCHANGE", "SINDHU_WS_CANDLES",
              "SINDHU_WALLET", "SINDHU_MEMORY_TRIM")


def validate_config():
    """{field: error} for the saved settings; {} when everything is valid."""
    errors = {}
    try:
        from paper_trading import config as pt_config
        settings = pt_config.load()
        errors.update(pt_config.validate_update({k: v for k, v in settings.items()}) or {})
    except Exception as e:
        errors["paper_trading_config"] = f"could not be read: {type(e).__name__}"
    try:
        from paper_trading import wallet
        w = wallet.settings()
        if not 0 < float(w["risk_per_trade_pct"]) <= 2.0:
            errors["wallet.risk_per_trade_pct"] = "must be above 0 and at most 2 % per trade"
        if int(w["max_open_positions"]) < 1:
            errors["wallet.max_open_positions"] = "must be at least 1"
        if not 0 < float(w["daily_loss_limit_pct"]) <= 10.0:
            errors["wallet.daily_loss_limit_pct"] = "must be above 0 and at most 10 %"
    except Exception as e:
        errors["wallet"] = f"settings could not be read: {type(e).__name__}"
    return errors


def config_errors(max_age_s=60):
    now = time.time()
    with _lock:
        if now - _state["config_checked_at"] < max_age_s:
            return dict(_state["config_errors"])
    errs = validate_config()
    with _lock:
        _state["config_errors"], _state["config_checked_at"] = errs, now
    return dict(errs)


def trading_state():
    """'enabled', 'disabled_config_error' or 'kill_switch' (cheap)."""
    try:
        from paper_trading import kill_switch
        if kill_switch.is_active():
            return "kill_switch"
    except Exception:
        pass
    return "disabled_config_error" if config_errors() else "enabled"


def _check(name, fn):
    t = time.time()
    try:
        detail = fn()
        return {"name": name, "ok": True, "seconds": round(time.time() - t, 2), "detail": detail}
    except Exception as e:
        return {"name": name, "ok": False, "seconds": round(time.time() - t, 2), "detail": f"{type(e).__name__}: {str(e)[:120]}"}


def _db():
    from data_engine import storage
    with storage.get_conn() as conn:
        conn.execute("SELECT 1").fetchone()
    return "reachable"


def _exchange_and_clock():
    from data_engine import config as base_config
    from data_engine.exchanges.registry import get_exchange_client
    name = base_config.cloud_safe_exchange(base_config.DEFAULT_EXCHANGE)
    client = get_exchange_client(name)
    ex = getattr(client, "_exchange", None)
    if ex is None or not hasattr(ex, "fetch_time"):
        return {"exchange": name, "clock_skew_s": None, "note": "this client has no server-time call"}
    before = time.time()
    server_ms = ex.fetch_time()
    after = time.time()
    skew = server_ms / 1000 - (before + after) / 2
    if abs(skew) >= 2.0:
        raise RuntimeError(f"clock skew {skew:.2f}s vs {name} (limit 2 s)")
    return {"exchange": name, "clock_skew_s": round(skew, 3)}


def _telegram():
    from paper_trading import telegram_bot
    token = telegram_bot.load_settings().get("bot_token")
    if not token:
        return "no bot token configured (nothing checked)"
    import requests
    r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)      # read-only: sends NO message
    if r.status_code != 200 or not r.json().get("ok"):
        raise RuntimeError(f"token rejected (HTTP {r.status_code})")
    return "token valid (getMe)"


def _writable():
    d = os.environ.get("SINDHU_DATA_DIR") or tempfile.gettempdir()
    os.makedirs(d, exist_ok=True)
    fd, path = tempfile.mkstemp(dir=d, prefix=".selfcheck_")
    os.close(fd)
    os.remove(path)
    return "writable"


def run_self_check(network=True):
    checks = [_check("database", _db), _check("data_folder", _writable)]
    if network:
        checks += [_check("exchange_and_clock", _exchange_and_clock), _check("telegram_token", _telegram)]
    res = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ok": all(c["ok"] for c in checks), "checks": checks}
    with _lock:
        _state["self_check"] = res
    return res


def start_background_self_check(delay_s=20):
    """Called once at startup; does not delay serving requests."""
    def run():
        time.sleep(delay_s)
        try:                                     # master plan A9: create MAIN_WALLET once (idempotent) so its start time is fixed
            from paper_trading import wallet
            wallet.ensure()
        except Exception:
            pass
        run_self_check()
    threading.Thread(target=run, daemon=True, name="self-check").start()


def safe_config_summary():
    out = {"paper_trading": {}, "telegram": {}, "flags": {}}
    try:
        from paper_trading import config as pt_config
        s = pt_config.load()
        out["paper_trading"] = {k: s.get(k) for k in _SAFE_PT_KEYS}
    except Exception:
        pass
    try:
        from paper_trading import telegram_bot
        t = telegram_bot.load_settings()
        out["telegram"] = {k: t.get(k) for k in _SAFE_TG_KEYS}
        out["telegram"]["bot_token_set"] = bool(t.get("bot_token"))
        out["telegram"]["public_signals_allowed"] = telegram_bot.public_signals_allowed()
    except Exception:
        pass
    out["flags"] = {k: os.environ.get(k, "") not in ("", "0") for k in _FLAG_ENVS}
    blob = json.dumps(out, sort_keys=True, default=str)
    return out, hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def details():
    summary, h = safe_config_summary()
    try:
        from data_engine import db_backend
        breaker = db_backend.breaker_state()
        breaker.pop("last_error", None)                  # error text can contain host names: counts only
    except Exception:
        breaker = None
    with _lock:
        sc = _state["self_check"]
    try:
        from data_engine.resample import LIVE_CANDLES_ONLY
        from data_engine import live_candles
        candles = live_candles.freshness_counts() if LIVE_CANDLES_ONLY else None     # master plan A20 (local reads its own database)
    except Exception:
        candles = None
    try:
        from data_engine import live_candles
        refetch = live_candles.refetch_state()                                          # master plan V2 R2 (P27)
    except Exception:
        refetch = None
    try:
        from data_engine import coingecko_client
        top_coins = coingecko_client.disk_cache_info()                                  # master plan V2 R1 (P5)
    except Exception:
        top_coins = None
    return {"candles": candles, "trading": trading_state(), "config_errors": config_errors(), "self_check": sc, "config_hash": h,
            "config_summary": summary, "db_breaker": breaker, "refetch_queue": refetch, "top_coins_cache": top_coins}

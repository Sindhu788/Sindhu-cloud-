"""Master plan V2 PG3-PG7: small read endpoints for the new pages, plus the MAIN_WALLET settings save.

Read endpoints are light (in-memory state, a committed JSON file, or one small query) and cached where it matters.
POST /api/wallet/settings is the only write: it uses the SAME limits as paper_trading/self_check.py (risk <= 2 %, position cap 5-25 %,
daily loss limit <= 10 %, at least 1 open position), so a value the self-check would call a config error can never be saved."""
import json
import os
import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_lock = threading.Lock()
_cache = {}


def _cached(key, ttl, fn):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def _finite(v):
    """Infinity/NaN cannot be sent as JSON: they become null ("not defined")."""
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    if isinstance(v, dict):
        return {k: _finite(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_finite(x) for x in v]
    return v


def _load_json(rel):
    with open(os.path.join(_HERE, *rel.split("/")), encoding="utf-8") as f:
        return _finite(json.load(f))


# ---------------------------------------------------------------- strategies: validation classes (W6)
BENCHMARK_WHY = ("Passes 6 of 7 ROBUST rules; fails the false-discovery check over 44 tested strategies "
                 "(bootstrap p {p:.2f}, needs to pass Benjamini-Hochberg at q = 0.05). Not in the wallet.")


@router.get("/api/v2/validation")
def validation():
    def build():
        try:
            classes = _load_json("paper_trading/validation_classes.json").get("classes", {})
        except Exception:
            classes = {}
        bench = []
        try:
            for u in _load_json("paper_trading/benchmark_v2_summary.json")["units"]:
                if u.get("verdict"):
                    bench.append({"id": u["id"], "name": u["name"], "class": u["verdict"],
                                  "why": BENCHMARK_WHY.format(p=u.get("oos_block_bootstrap_p") or 0), "timeframe": "1d"})
        except Exception:
            pass
        return {"classes": classes, "benchmark_v2": bench}
    return _cached("validation", 600, build)


@router.get("/api/v2/benchmark")
def benchmark():
    try:
        return _cached("benchmark", 3600, lambda: _load_json("paper_trading/benchmark_v2_summary.json"))
    except Exception:
        raise HTTPException(404, "benchmark summary not available")


# ---------------------------------------------------------------- settings schema (W8): the same rules the server applies
HELP = {
    "risk_pct_default": ("Risk per research trade", "% of that book's balance lost if the stop is hit", "%"),
    "max_open_trades": ("Max open research trades", "per strategy book", "trades"),
    "max_open_positions_per_coin": ("Max positions per coin", "across all books (safety cap: 5)", "positions"),
    "max_portfolio_risk_pct_per_coin": ("Max risk per coin", "all open risk on one coin together", "%"),
    "cooldown_minutes": ("Cooldown after a trade", "same strategy, same coin", "min"),
    "coin_filter_top_n": ("Coins scanned", "top N by liquidity", "coins"),
    "tick_interval_seconds": ("Pause between scans", "the engine waits this long after a scan", "s"),
    "lookback_days": ("Candle history", "days of candles each strategy sees", "days"),
    "daily_goal_pct": ("Daily goal", "for the progress bar only, never trades more", "%"),
    "cooling_off_loss_streak": ("Cooling-off after losses", "losing trades in a row before a pause (0 = off)", "trades"),
    "cooling_off_hours": ("Cooling-off length", "how long the pause lasts", "h"),
    "initial_balance": ("Research book start balance", "each strategy book starts with this", "$"),
    "commission_pct": ("Commission", "per side", "%"),
}
WALLET_RULES = {
    "risk_per_trade_pct": {"label": "Wallet risk per trade", "help": "% of wallet equity lost if the stop is hit", "unit": "%",
                           "min": 0.05, "max": 2.0, "step": 0.05, "danger_up": True},
    "max_position_pct": {"label": "Max size of one position", "help": "% of wallet equity (stricter cap, V2 R4)", "unit": "%",
                         "min": 5.0, "max": 25.0, "step": 1, "danger_up": True},
    "max_open_positions": {"label": "Max open wallet positions", "help": "at the same time", "unit": "positions",
                           "min": 1, "max": 10, "step": 1, "int": True, "danger_up": True},
    "daily_loss_limit_pct": {"label": "Daily loss limit", "help": "no new entries for the rest of the UTC day once hit", "unit": "%",
                             "min": 0.5, "max": 10.0, "step": 0.5, "danger_up": True},
}


@router.get("/api/v2/settings-schema")
def settings_schema():
    from paper_trading import config as pt_config, wallet
    numeric = {}
    for k, (kind, lo, hi, lo_incl) in pt_config._NUMERIC_RULES.items():
        lab = HELP.get(k)
        numeric[k] = {"kind": kind, "min": lo, "max": hi, "min_inclusive": lo_incl, "label": lab[0] if lab else k.replace("_", " "),
                      "help": lab[1] if lab else "", "unit": lab[2] if lab else ""}
    return {"paper": numeric, "wallet": WALLET_RULES, "wallet_values": {k: wallet.settings().get(k) for k in WALLET_RULES},
            "danger_fields": ["risk_pct_default", "max_open_trades", "max_open_positions_per_coin", "max_portfolio_risk_pct_per_coin"]}


class WalletSettings(BaseModel):
    risk_per_trade_pct: Optional[float] = None
    max_position_pct: Optional[float] = None
    max_open_positions: Optional[int] = None
    daily_loss_limit_pct: Optional[float] = None


def validate_wallet(fields):
    errors = {}
    for k, v in fields.items():
        if v is None:
            continue
        r = WALLET_RULES[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            errors[k] = "must be a number"
        elif r.get("int") and int(v) != v:
            errors[k] = "must be a whole number"
        elif not r["min"] <= v <= r["max"]:
            errors[k] = f"must be between {r['min']:g} and {r['max']:g} {r['unit']}"
    return errors


@router.post("/api/wallet/settings")
def save_wallet_settings(req: WalletSettings):
    from paper_trading import wallet
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    errors = validate_wallet(fields)
    if errors:
        raise HTTPException(422, {"errors": errors})
    if not fields:
        return {"ok": True, "settings": wallet.settings()}
    with wallet._lock:
        try:
            saved = json.loads(wallet._get("settings") or "{}")
        except Exception:
            saved = {}
        before = {k: wallet.settings().get(k) for k in fields}
        saved.update(fields)
        wallet._set("settings", json.dumps(saved))
    try:
        wallet._journal("settings", "wallet settings changed by the owner: " +
                        ", ".join(f"{k} {before.get(k)} -> {v}" for k, v in fields.items()))
    except Exception:
        pass
    return {"ok": True, "settings": wallet.settings()}


# ---------------------------------------------------------------- system (W9)
@router.get("/api/v2/system")
def system():
    def build():
        out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        try:
            from paper_trading.engine import engine
            out["last_stages"] = getattr(engine, "_last_stages", None)
            out["engine"] = {"running": bool(getattr(engine, "_running", False)), "last_tick_at": getattr(engine, "_last_tick_at", None),
                             "last_tick_seconds": getattr(engine, "_last_tick_duration_seconds", None),
                             "progress": dict(getattr(engine, "_scan_progress", {}) or {})}
        except Exception:
            out["engine"] = None
        try:
            from paper_trading import memory_guard
            out["memory_history"] = memory_guard.history()
        except Exception:
            out["memory_history"] = []
        try:
            from data_engine import storage
            with storage.get_conn() as conn:
                rows = conn.execute("SELECT started_at, completed_at, kind, outcome, reason, coins_scanned, candidates, rejected, accepted, "
                                    "errors FROM paper_scan_log ORDER BY completed_at DESC LIMIT 20").fetchall()
            keys = ("started_at", "completed_at", "kind", "outcome", "reason", "coins_scanned", "candidates", "rejected", "accepted", "errors")
            out["scans"] = [dict(zip(keys, tuple(r))) for r in rows]
        except Exception:
            out["scans"] = []
        try:
            from sindhu_web import assets
            out["build"] = assets.build_tag()
        except Exception:
            out["build"] = None
        try:
            soak = os.path.join(_HERE, "docs", "SOAK_REPORT.md")
            out["soak_report"] = open(soak, encoding="utf-8").read()[:3000] if os.path.exists(soak) else None
        except Exception:
            out["soak_report"] = None
        return out
    return _cached("system", 15, build)

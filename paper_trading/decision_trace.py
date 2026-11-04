"""Decision trace: one compact row per scan decision so "why did / didn't X signal?" is answered in seconds.

Each row: time, exchange:symbol, strategy, timeframe, direction, outcome (opened / rejected / no_trade / dry_run),
the gate that stopped it (or none), the full reason text, the age of the newest candle used, and an ordered list of gate
results (pass / fail / not_reached). It is derived from the existing decision stream (engine._log_decision), so it adds
no new decision logic and cannot change a trading outcome.

Storage is bounded: db_size_guard prunes this table to the last 7 days / 20,000 rows. The table is created lazily
(CREATE TABLE IF NOT EXISTS, TEXT ids) so it works on SQLite and on the Cloud Postgres without a migration.
"""
import json
import re
import uuid

# canonical order in which a candidate meets the gates
GATE_ORDER = ["market_data", "entry_rule", "strategy_state", "kill_switch", "drawdown_breaker", "same_coin_cap",
              "max_coins", "position_lock", "opposite_signal", "sizing"]

_RULES = [
    ("market_data", re.compile(r"Stale closed|Market data is empty|OHLCV|Invalid OHLC|Gaps in|timestamps must|Future market|Non-finite|Unsupported live|No closed market|unavailable", re.I)),
    ("entry_rule", re.compile(r"No entry rule matched|No eligible strategies|Entry conditions", re.I)),
    ("kill_switch", re.compile(r"KILL SWITCH", re.I)),
    ("drawdown_breaker", re.compile(r"account-wide drawdown|Drawdown Protection|consecutive losses|cooling", re.I)),
    ("strategy_state", re.compile(r"strategy paused|paused|blacklist|demoted", re.I)),
    ("max_coins", re.compile(r"max coins for this strategy", re.I)),
    ("same_coin_cap", re.compile(r"per-coin|same coin|positions? on|portfolio risk|max_open_positions_per_coin|cross-strategy", re.I)),
    ("position_lock", re.compile(r"position lock", re.I)),
    ("opposite_signal", re.compile(r"opposite", re.I)),
    ("sizing", re.compile(r"no stop-loss|risk cannot be sized|size", re.I)),
]


def classify(decision, reason):
    """-> failed gate key or None."""
    if decision in ("opened", "dry_run"):
        return None
    text = reason or ""
    for key, rx in _RULES:
        if rx.search(text):
            return key
    return "other"


def gate_results(decision, failed_gate):
    if failed_gate is None:
        return [{"gate": g, "result": "pass"} for g in GATE_ORDER]
    out, reached = [], True
    for g in GATE_ORDER:
        if g == failed_gate:
            out.append({"gate": g, "result": "fail"}); reached = False
        else:
            out.append({"gate": g, "result": "pass" if reached else "not_reached"})
    if failed_gate == "other":
        out = [{"gate": g, "result": "unknown"} for g in GATE_ORDER]
    return out


def _data_age_s(snapshot):
    try:
        return round(float(((snapshot or {}).get("candle_receipt") or {}).get("age_ms")) / 1000.0, 1)
    except (TypeError, ValueError):
        return None


def build_rows(pending):
    """pending = engine decision dicts -> trace rows."""
    rows = []
    for d in pending:
        gate = classify(d.get("decision"), d.get("reason"))
        rows.append((uuid.uuid4().hex, d.get("created_at"), f'{d.get("exchange")}:{d.get("symbol")}', d.get("strategy_id"),
                     d.get("strategy_name"), d.get("timeframe"), d.get("direction"), d.get("decision"), gate,
                     (d.get("reason") or "")[:300], _data_age_s(d.get("market_snapshot")),
                     json.dumps(gate_results(d.get("decision"), gate))))
    return rows


_DDL = ("CREATE TABLE IF NOT EXISTS paper_decision_trace (id TEXT PRIMARY KEY, ts TEXT NOT NULL, coin TEXT, strategy_id TEXT, "
        "strategy_name TEXT, timeframe TEXT, direction TEXT, outcome TEXT, failed_gate TEXT, reason TEXT, data_age_s REAL, gates_json TEXT)")


def record(pending, conn=None):
    """Write trace rows for a batch of engine decisions. Never raises into the trading loop."""
    if not pending:
        return 0
    from data_engine import storage
    try:
        rows = build_rows(pending)
        if conn is None:
            with storage.get_conn() as c:
                return record(pending, c)
        conn.execute(_DDL)
        conn.executemany("INSERT INTO paper_decision_trace VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)
    except Exception:
        return 0


def query(coin=None, strategy=None, outcome=None, hours=24, limit=50):
    """The 'why' endpoint: newest first. `coin` matches loosely (BTC, BTCUSDT or BTC/USDT)."""
    from datetime import datetime, timedelta, timezone
    from data_engine import storage
    since = (datetime.now(timezone.utc) - timedelta(hours=max(1, min(int(hours), 24 * 7)))).isoformat()
    sql, args = "SELECT ts, coin, strategy_name, timeframe, direction, outcome, failed_gate, reason, data_age_s, gates_json FROM paper_decision_trace WHERE ts >= ?", [since]
    if coin:
        norm = re.sub(r"[^A-Za-z0-9]", "", coin).upper()
        sql += " AND REPLACE(REPLACE(UPPER(coin), '/', ''), ':', '') LIKE ?"; args.append(f"%{norm}%")
    if strategy:
        sql += " AND LOWER(strategy_name) LIKE ?"; args.append(f"%{strategy.lower()}%")
    if outcome:
        sql += " AND outcome = ?"; args.append(outcome)
    sql += " ORDER BY ts DESC LIMIT ?"; args.append(max(1, min(int(limit), 500)))
    try:
        with storage.get_conn() as c:
            rows = c.execute(sql, args).fetchall()
            tele = c.execute("SELECT sent_at, strategy_name, success, error FROM telegram_message_log WHERE sent_at >= ? "
                             "ORDER BY sent_at DESC LIMIT 20", (since,)).fetchall()
    except Exception:
        return {"decisions": [], "telegram": [], "note": "no trace recorded yet (table is created at the first scan)"}
    keys = ("ts", "coin", "strategy", "timeframe", "direction", "outcome", "failed_gate", "reason", "data_age_s")
    dec = []
    for r in rows:
        item = dict(zip(keys, r[:9])); item["gates"] = json.loads(r[9]) if r[9] else []
        dec.append(item)
    return {"decisions": dec, "telegram": [dict(zip(("sent_at", "strategy", "success", "error"), t)) for t in tele]}


def summary(hours=24):
    """Counts by outcome and by failed gate, for the daily summary and the dashboard."""
    from datetime import datetime, timedelta, timezone
    from data_engine import storage
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        with storage.get_conn() as c:
            by_outcome = dict(c.execute("SELECT outcome, COUNT(*) FROM paper_decision_trace WHERE ts >= ? GROUP BY 1", (since,)).fetchall())
            by_gate = dict(c.execute("SELECT COALESCE(failed_gate,'none'), COUNT(*) FROM paper_decision_trace WHERE ts >= ? GROUP BY 1", (since,)).fetchall())
        return {"by_outcome": by_outcome, "by_gate": by_gate}
    except Exception:
        return {"by_outcome": {}, "by_gate": {}}

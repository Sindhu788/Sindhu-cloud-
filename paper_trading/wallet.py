"""Master plan A9-A13 (P2, P30, P31, P32, P33, P34): ONE real-like paper wallet, MAIN_WALLET, $100.00, shared by all strategies.

How it works (the research books are untouched and keep feeding the learning statistics):
- A research position that the engine OPENED has already passed every existing gate (Wilson, confluence, freshness, risk manager,
  same-coin cap, kill switch, ...). The engine offers it to the wallet (`offer`). At the end of the scan the wallet decides (`settle`):
  highest backtest validation class first (ROBUST > FRAGILE > others), then first come.
- Wallet rules, all ADDING safety, never relaxing a gate:
  long-only (paper; shorting is not modelled), at most 4 open positions, at most 5 per coin (same-coin cap), risk <= 1 % of equity per
  trade sized from the stop distance, no leverage (size <= free cash), Binance minimum notional $5, fee 0.1 % per side + slippage
  0.05 % per side, no new entry after the day's equity fell 5 % below the UTC-midnight equity (A10), no second entry of the same coin
  and direction within 60 minutes (A11), strategies auto-paused for the wallet after >= 20 closed wallet trades with profit factor < 0.9
  or a drawdown contribution > 3 % of the wallet (A12; un-pause is manual only).
- When the research position closes, the wallet position closes at the same market price (minus its own slippage and fee).
- Every decision (entry, exit, rejection, pause) is one journal row with gates, sizes, fees and data sources (A13).
Tables are created on first use with portable SQL (SQLite and Postgres). Paper only: no order is ever sent anywhere.
"""
import json
import threading
import time
import uuid
from datetime import datetime, timezone

from data_engine import storage

WALLET_ID = "MAIN_WALLET"
START_BALANCE = 100.00
DEFAULTS = {
    "risk_per_trade_pct": 1.0, "max_open_positions": 4, "same_coin_cap": 5, "min_notional_usd": 5.0,
    "fee_pct": 0.10, "slippage_pct": 0.05, "daily_loss_limit_pct": 5.0, "duplicate_window_min": 60,
    "auto_pause_min_trades": 20, "auto_pause_pf_below": 0.9, "auto_pause_dd_contribution_pct": 3.0, "long_only": True,
}
DAILY_LOSS_LIMIT_HARD_MAX_PCT = 10.0      # A10: configurable, but never above 10 % without editing this constant
_CLASS_RANK = {"ROBUST": 0, "FRAGILE": 1}
_lock = threading.RLock()
_offers = []
_marks = {}                               # symbol -> last price seen this process
_ready = [False]

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS wallet_state (k TEXT PRIMARY KEY, v TEXT)""",
    """CREATE TABLE IF NOT EXISTS wallet_positions (
        id TEXT PRIMARY KEY, wallet_id TEXT, research_position_id TEXT, strategy_id TEXT, strategy_name TEXT, validation_class TEXT,
        exchange TEXT, symbol TEXT, timeframe TEXT, side TEXT, entry_price REAL, qty REAL, notional REAL, fee_entry REAL,
        stop_loss REAL, take_profit REAL, risk_usd REAL, opened_at TEXT, status TEXT, exit_price REAL, fee_exit REAL, pnl REAL,
        closed_at TEXT, close_reason TEXT)""",
    """CREATE TABLE IF NOT EXISTS wallet_journal (
        id TEXT PRIMARY KEY, wallet_id TEXT, created_at TEXT, event TEXT, strategy_id TEXT, strategy_name TEXT, symbol TEXT,
        timeframe TEXT, side TEXT, price REAL, qty REAL, notional REAL, fees REAL, stop_loss REAL, take_profit REAL, reason TEXT,
        gates TEXT, sources TEXT, research_position_id TEXT, wallet_position_id TEXT)""",
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _utc_day(ts=None):
    return datetime.fromtimestamp(ts if ts is not None else time.time(), timezone.utc).strftime("%Y-%m-%d")


def settings():
    s = dict(DEFAULTS)
    try:
        saved = json.loads(_get("settings") or "{}")
        s.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except Exception:
        pass
    s["daily_loss_limit_pct"] = min(float(s["daily_loss_limit_pct"]), DAILY_LOSS_LIMIT_HARD_MAX_PCT)
    return s


# ------------------------------------------------------------------ storage helpers
def ensure():
    """Create the tables and MAIN_WALLET once (idempotent: a second call changes nothing)."""
    with _lock:
        if _ready[0]:
            return
        with storage.get_conn() as conn:
            for stmt in _SCHEMA:
                conn.execute(stmt)
        if _get("created_at") is None:
            _set("created_at", _now_iso())
            _set("start_balance", f"{START_BALANCE:.2f}")
            _set("cash", f"{START_BALANCE:.8f}")
            _set("paused_strategies", "{}")
        _ready[0] = True


def _get(k):
    with storage.get_conn() as conn:
        row = conn.execute("SELECT v FROM wallet_state WHERE k = ?", (f"{WALLET_ID}:{k}",)).fetchone()
    return None if row is None else row[0]


def _set(k, v):
    key = f"{WALLET_ID}:{k}"
    with storage.get_conn() as conn:
        conn.execute("DELETE FROM wallet_state WHERE k = ?", (key,))
        conn.execute("INSERT INTO wallet_state (k, v) VALUES (?, ?)", (key, str(v)))


def _rows(sql, params=()):
    """Rows as dicts on both backends (SQLite and the Postgres wrapper both return plain tuples plus a cursor description)."""
    with storage.get_conn() as conn:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in rows]


def open_positions():
    ensure()
    return _rows("SELECT * FROM wallet_positions WHERE wallet_id = ? AND status = 'open' ORDER BY opened_at", (WALLET_ID,))


def closed_positions(strategy_id=None):
    ensure()
    if strategy_id is None:
        return _rows("SELECT * FROM wallet_positions WHERE wallet_id = ? AND status = 'closed' ORDER BY closed_at", (WALLET_ID,))
    return _rows("SELECT * FROM wallet_positions WHERE wallet_id = ? AND status = 'closed' AND strategy_id = ? ORDER BY closed_at",
                 (WALLET_ID, strategy_id))


def journal(limit=50):
    ensure()
    return _rows("SELECT * FROM wallet_journal WHERE wallet_id = ? ORDER BY created_at DESC LIMIT ?", (WALLET_ID, int(limit)))


def _journal(event, reason, pos=None, research=None, price=None, qty=None, notional=None, fees=None, gates=None, sources=None, wpid=None):
    research = research or {}
    with storage.get_conn() as conn:
        conn.execute(
            "INSERT INTO wallet_journal (id, wallet_id, created_at, event, strategy_id, strategy_name, symbol, timeframe, side, price, qty, "
            "notional, fees, stop_loss, take_profit, reason, gates, sources, research_position_id, wallet_position_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, WALLET_ID, _now_iso(), event, research.get("strategy_id"), research.get("strategy_name"), research.get("symbol"),
             research.get("timeframe"), research.get("direction"), price, qty, notional, fees, research.get("stop_loss"),
             research.get("take_profit"), reason, json.dumps(gates or {}, default=str), json.dumps(sources or {}, default=str),
             research.get("id"), wpid))


def cash():
    ensure()
    return float(_get("cash"))


def mark(symbol, price):
    """The engine passes every fresh price it sees; used for equity, the daily loss limit and the dashboard."""
    try:
        if price and price > 0:
            _marks[symbol] = float(price)
    except Exception:
        pass


def equity(prices=None):
    prices = prices or _marks
    total = cash()
    for p in open_positions():
        total += p["qty"] * float(prices.get(p["symbol"], p["entry_price"]))
    return total


def summary():
    ensure()
    s = settings()
    eq = equity()
    day_start = _day_start_equity(eq)
    closed = closed_positions()
    return {"wallet": WALLET_ID, "start_balance": START_BALANCE, "cash": round(cash(), 2), "equity": round(eq, 2),
            "day_pnl": round(eq - day_start, 2), "day_start_equity": round(day_start, 2), "open_positions": len(open_positions()),
            "closed_trades": len(closed), "realized_pnl": round(sum(p["pnl"] or 0 for p in closed), 2),
            "entries_blocked_today": eq <= day_start * (1 - s["daily_loss_limit_pct"] / 100),
            "paused_strategies": paused(), "created_at": _get("created_at"), "rules": s, "paper_only": True}


# ------------------------------------------------------------------ A10 daily loss limit
def _day_start_equity(current_equity=None):
    today = _utc_day()
    if _get("day") != today:
        _set("day", today)
        _set("day_start_equity", f"{(current_equity if current_equity is not None else equity()):.8f}")
    return float(_get("day_start_equity"))


def daily_limit_hit():
    s = settings()
    eq = equity()
    start = _day_start_equity(eq)
    return eq <= start * (1 - s["daily_loss_limit_pct"] / 100), eq, start


# ------------------------------------------------------------------ A12 auto-pause
def paused():
    try:
        return json.loads(_get("paused_strategies") or "{}")
    except Exception:
        return {}


def unpause(strategy_id):
    """Manual only (owner)."""
    p = paused()
    if p.pop(strategy_id, None) is not None:
        _set("paused_strategies", json.dumps(p))
        _journal("unpause", "un-paused manually by the owner", research={"strategy_id": strategy_id})
        return True
    return False


def _review_strategy(strategy_id, strategy_name):
    s = settings()
    closed = closed_positions(strategy_id)
    if len(closed) < s["auto_pause_min_trades"]:
        return None
    wins = sum(p["pnl"] for p in closed if p["pnl"] > 0)
    losses = -sum(p["pnl"] for p in closed if p["pnl"] <= 0)
    pf = wins / losses if losses > 0 else float("inf")
    cum, peak, worst = 0.0, 0.0, 0.0
    for p in closed:
        cum += p["pnl"]
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    dd_pct = -worst / START_BALANCE * 100
    why = []
    if pf < s["auto_pause_pf_below"]:
        why.append(f"profit factor {pf:.2f} < {s['auto_pause_pf_below']}")
    if dd_pct > s["auto_pause_dd_contribution_pct"]:
        why.append(f"drawdown contribution {dd_pct:.1f}% > {s['auto_pause_dd_contribution_pct']}% of the wallet")
    if not why:
        return None
    p = paused()
    if strategy_id in p:
        return None
    p[strategy_id] = {"at": _now_iso(), "why": "; ".join(why), "trades": len(closed)}
    _set("paused_strategies", json.dumps(p))
    reason = f"auto-paused for MAIN_WALLET after {len(closed)} trades: {'; '.join(why)} (research book continues; un-pause is manual)"
    _journal("pause", reason, research={"strategy_id": strategy_id, "strategy_name": strategy_name})
    try:
        storage.create_paper_alert("wallet_strategy_paused", strategy_id, strategy_name, reason, "warning", _now_iso())
    except Exception:
        pass
    return reason


# ------------------------------------------------------------------ offers and decisions
def offer(research_pos, candidate=None, snapshot=None):
    """Called right after a research position was opened (all gates passed). Decided in settle(). Never raises."""
    try:
        from paper_trading import telegram_bot
        cls = telegram_bot.validation_class(research_pos.get("strategy_id"))
        snap = snapshot or {}
        sources = {"exchange": research_pos.get("exchange"), "price": research_pos.get("entry_price"),
                   "candle_receipt": snap.get("candle_receipt"), "market_state": snap.get("market_state")}
        gates = {"research_gates": "all passed (position opened)", "confidence": research_pos.get("confidence"), "validation_class": cls}
        with _lock:
            _offers.append({"pos": dict(research_pos), "cls": cls, "seq": len(_offers), "gates": gates, "sources": sources})
    except Exception:
        pass


def settle(now=None):
    """Decide all offers of this scan: best validation class first, then arrival order. Returns the list of decisions."""
    with _lock:
        batch = sorted(_offers, key=lambda o: (_CLASS_RANK.get(o["cls"], 2), o["seq"]))
        _offers.clear()
    out = []
    for o in batch:
        try:
            out.append(_decide(o, now=now))
        except Exception as e:
            out.append({"decision": "error", "reason": repr(e)})
    return out


def _reject(o, reason):
    _journal("reject", reason, research=o["pos"], price=o["pos"].get("entry_price"), gates=o["gates"], sources=o["sources"])
    return {"decision": "rejected", "reason": reason, "research_position_id": o["pos"].get("id")}


def _decide(o, now=None):
    ensure()
    s = settings()
    pos = o["pos"]
    now = now if now is not None else time.time()
    from paper_trading import kill_switch
    if kill_switch.is_active():
        return _reject(o, "kill switch active")
    if s["long_only"] and pos.get("direction") != "long":
        return _reject(o, "wallet is long-only (paper spot account; shorting is not modelled)")
    if pos.get("strategy_id") in paused():
        return _reject(o, "strategy auto-paused for the wallet")
    hit, eq, start = daily_limit_hit()
    if hit:
        return _reject(o, f"daily loss limit: equity {eq:.2f} is {s['daily_loss_limit_pct']}% or more below today's start {start:.2f}")
    opens = open_positions()
    if len(opens) >= s["max_open_positions"]:
        return _reject(o, f"wallet full ({len(opens)} of {s['max_open_positions']} positions open)")
    same = [p for p in opens if p["symbol"] == pos["symbol"]]
    if len(same) >= s["same_coin_cap"]:
        return _reject(o, f"same-coin cap ({s['same_coin_cap']}) reached for {pos['symbol']}")
    window = s["duplicate_window_min"] * 60
    recent = _rows("SELECT opened_at FROM wallet_positions WHERE wallet_id = ? AND symbol = ? AND side = ?",
                   (WALLET_ID, pos["symbol"], pos.get("direction")))
    for r in recent:
        try:
            if now - datetime.fromisoformat(r["opened_at"]).timestamp() < window:
                return _reject(o, f"duplicate entry guard: same coin and direction within {s['duplicate_window_min']} min")
        except Exception:
            continue
    stop = pos.get("stop_loss")
    entry = float(pos.get("entry_price") or 0)
    if not stop or entry <= 0 or stop >= entry:
        return _reject(o, "no valid stop-loss below the entry: size cannot be risk-based")
    fill = entry * (1 + s["slippage_pct"] / 100)
    stop_dist = (fill - float(stop)) / fill
    risk_usd = eq * s["risk_per_trade_pct"] / 100
    fee_rate = s["fee_pct"] / 100
    notional = risk_usd / stop_dist
    free = cash()
    notional = min(notional, free / (1 + fee_rate), eq)              # no leverage
    if notional < s["min_notional_usd"]:
        return _reject(o, f"below the minimum notional (${notional:.2f} < ${s['min_notional_usd']:.2f})")
    qty = notional / fill
    fee = notional * fee_rate
    wpid = uuid.uuid4().hex
    with _lock:
        with storage.get_conn() as conn:
            conn.execute(
                "INSERT INTO wallet_positions (id, wallet_id, research_position_id, strategy_id, strategy_name, validation_class, exchange, symbol, "
                "timeframe, side, entry_price, qty, notional, fee_entry, stop_loss, take_profit, risk_usd, opened_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                (wpid, WALLET_ID, pos.get("id"), pos.get("strategy_id"), pos.get("strategy_name"), o["cls"], pos.get("exchange"), pos["symbol"],
                 pos.get("timeframe"), pos.get("direction"), fill, qty, notional, fee, float(stop), pos.get("take_profit"),
                 min(risk_usd, notional * stop_dist), datetime.fromtimestamp(now, timezone.utc).isoformat()))
        _set("cash", f"{free - notional - fee:.8f}")
    mark(pos["symbol"], entry)
    _journal("entry", f"opened: risk {s['risk_per_trade_pct']}% of equity {eq:.2f}, stop distance {stop_dist * 100:.2f}%",
             research=pos, price=fill, qty=qty, notional=notional, fees=fee, gates=o["gates"], sources=o["sources"], wpid=wpid)
    return {"decision": "opened", "wallet_position_id": wpid, "notional": notional, "qty": qty, "fee": fee}


def on_research_close(research_pos, raw_exit_price, reason):
    """The research position closed: close the wallet's mirror position (if any) at the same market price. Never raises."""
    try:
        ensure()
        s = settings()
        rows = _rows("SELECT * FROM wallet_positions WHERE wallet_id = ? AND research_position_id = ? AND status = 'open'",
                     (WALLET_ID, research_pos.get("id")))
        for w in rows:
            px = float(raw_exit_price) * (1 - s["slippage_pct"] / 100)
            proceeds = w["qty"] * px
            fee = proceeds * s["fee_pct"] / 100
            pnl = proceeds - fee - w["notional"] - w["fee_entry"]
            with _lock:
                with storage.get_conn() as conn:
                    conn.execute("UPDATE wallet_positions SET status = 'closed', exit_price = ?, fee_exit = ?, pnl = ?, closed_at = ?, close_reason = ? "
                                 "WHERE id = ? AND status = 'open'", (px, fee, pnl, _now_iso(), reason, w["id"]))
                _set("cash", f"{cash() + proceeds - fee:.8f}")
            mark(w["symbol"], raw_exit_price)
            _journal("exit", f"closed ({reason}): pnl {pnl:+.4f}", research=research_pos, price=px, qty=w["qty"], notional=proceeds, fees=fee,
                     wpid=w["id"])
            _review_strategy(w["strategy_id"], w["strategy_name"])
    except Exception:
        pass


def reconcile(prices=None):
    """cash + value of open positions == equity, to the cent; and cash == start - entries - fees + exits (from the rows)."""
    ensure()
    rows = _rows("SELECT * FROM wallet_positions WHERE wallet_id = ?", (WALLET_ID,))
    expected_cash = START_BALANCE
    for r in rows:
        expected_cash -= r["notional"] + r["fee_entry"]
        if r["status"] == "closed":
            expected_cash += r["qty"] * r["exit_price"] - r["fee_exit"]
    c = cash()
    prices = prices or _marks
    value = sum(r["qty"] * float(prices.get(r["symbol"], r["entry_price"])) for r in rows if r["status"] == "open")
    return {"ok": abs(expected_cash - c) < 0.005 and abs((c + value) - equity(prices)) < 0.005,
            "cash": round(c, 2), "expected_cash": round(expected_cash, 2), "open_value": round(value, 2), "equity": round(c + value, 2)}


def _reset_for_tests():
    with _lock:
        _offers.clear()
        _marks.clear()
        _ready[0] = False

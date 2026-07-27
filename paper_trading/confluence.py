"""Confluence Scoring (Confidence & Signal Quality Group, item 8): when a
trade signal fires, counts how many independent, already-existing safety/
quality signals currently support it, and attaches a simple plain-language
label ("Strong -- 4/4 factors aligned" down to "Weak -- 1/4"). This is
purely a display/ranking signal -- it never blocks a trade itself (Risk
Manager remains the only real gate); it's meant to feed the Manual
Override / Telegram-readiness decision a person makes.

The four factors, each already computed by an existing, verified feature:
  1. Market regime not conflicting (paper_trading.regime) -- e.g. firing a
     trend-following signal while the coin is actually ranging is a weaker
     setup than firing it while genuinely trending.
  2. Strategy not currently paused by Drawdown Protection (drawdown_guard).
  3. No active Correlation Warning already involving this symbol
     (correlation.py) -- opening into an already-flagged concentrated
     position is weaker confluence.
  4. Positive recent pattern memory for this EXACT (strategy, symbol,
     market_state, session) combination (the same Coin-Specific Pattern
     Memory auto_avoid/lesson_auto_apply already read) -- degrades to
     "neutral" (not counted against) when there's too little history yet,
     since punishing a brand-new pattern for lacking history would be a
     false negative, not a real quality signal.
"""

from data_engine import storage
from paper_trading import regime as regime_mod


def score_confluence(strategy_id, symbol, exchange, market_state, session, direction):
    factors = []

    # Factor 1: regime alignment
    try:
        r = regime_mod.classify_regime(exchange, symbol)
    except Exception:
        r = None
    if r is None:
        regime_ok = None  # not enough data -- neutral, not counted against
    elif r["regime"] == "high_volatility":
        regime_ok = False  # a whipsaw-prone coin is a weaker setup regardless of direction
    elif r["regime"] == "trending" and market_state in ("trending_up", "trending_down"):
        regime_ok = True
    elif r["regime"] == "ranging" and market_state not in ("trending_up", "trending_down"):
        regime_ok = True
    else:
        regime_ok = False  # regime and the signal's own market_state disagree
    factors.append({"name": "Market condition supports this signal", "result": regime_ok})

    # Factor 2: not paused
    paused, _, _ = storage.is_strategy_paused(strategy_id)
    factors.append({"name": "Strategy not paused for safety", "result": not paused})

    # Factor 3: no active correlation conflict for this symbol
    with storage.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM paper_positions WHERE status='open' AND symbol=? LIMIT 1", (symbol,)
        ).fetchone()
    # A lightweight proxy for "would this create/extend a flagged concentration":
    # true correlation-warning detection needs the full pairwise scan (expensive,
    # already cached elsewhere) -- here we only check whether ANY other open
    # position already exists on this exact symbol, a cheap, always-fresh signal
    # that a new entry here is adding to an already-crowded coin.
    factors.append({"name": "No existing position already crowding this coin", "result": row is None})

    # Factor 4: positive pattern memory for this exact situation (neutral if too little data)
    patterns = storage.list_paper_coin_pattern_memory(strategy_id=strategy_id)
    match = next((p for p in patterns if p["symbol"] == symbol and p["market_state"] == market_state
                  and p["session"] == session), None)
    if match is None or match["trades"] < 5:
        pattern_ok = None
    else:
        pattern_ok = match["win_rate"] >= 50.0
    factors.append({"name": "Positive history for this exact coin/condition", "result": pattern_ok})

    counted = [f for f in factors if f["result"] is not None]
    passed = sum(1 for f in counted if f["result"])
    total = len(counted)
    if total == 0:
        label = "Unrated -- not enough data for any factor yet"
    else:
        ratio = passed / total
        strength = "Strong" if ratio >= 0.75 else "Moderate" if ratio >= 0.5 else "Weak"
        label = f"{strength} -- {passed}/{total} factors aligned"

    return {"label": label, "passed": passed, "total": total, "factors": factors}

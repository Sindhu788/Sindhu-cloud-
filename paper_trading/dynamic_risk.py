"""Dynamic Risk Sizing (Additional Features, B1): adjusts the risk % used
to size a NEW Paper Trading position based on the coin's current Market
Regime (paper_trading.regime, already verified) -- built entirely on that
existing classifier, no new market analysis.

Documented adjustment logic (simple, transparent, no hidden model):
  - high_volatility regime: risk halved (HIGH_VOLATILITY_RISK_MULTIPLIER =
    0.5) -- a whipsaw-prone coin makes stop-loss distance a less reliable
    risk boundary, so less capital per trade is the conservative response.
  - trending / ranging: full configured risk_pct_default, unchanged --
    these are the "normal" conditions the base risk setting was designed for.
  - No regime data yet (new symbol, insufficient history): full configured
    risk_pct_default, unchanged -- degrades gracefully rather than guessing.
"""

HIGH_VOLATILITY_RISK_MULTIPLIER = 0.5


def compute_risk_pct(exchange, symbol, base_risk_pct):
    """Returns (adjusted_risk_pct, note_or_None). note is a plain-language
    explanation, only populated when an adjustment was actually applied --
    used to make a risk reduction visible (logged), never silent."""
    from paper_trading import regime as regime_mod

    try:
        r = regime_mod.classify_regime(exchange, symbol)
    except Exception:
        r = None

    if r is None:
        return base_risk_pct, None

    if r["regime"] == "high_volatility":
        adjusted = base_risk_pct * HIGH_VOLATILITY_RISK_MULTIPLIER
        note = (f"{symbol} is in a high-volatility market condition (ATR {r['atr_pct']}% of price) -- "
                f"risk automatically reduced from {base_risk_pct:.2f}% to {adjusted:.2f}% for this trade.")
        return adjusted, note

    return base_risk_pct, None

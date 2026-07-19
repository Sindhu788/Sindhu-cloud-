"""A.10 -- DNA block system. Every BOT strategy is decomposed into a set of
reusable, named building blocks (Trend, Momentum, Liquidity, Volume,
Breakout, Session, Risk) purely from its own StrategyConfig -- which
indicators/concepts/filters it actually uses -- so the mutator and the
SINDHU Strategy Generator's deterministic builder can recombine blocks
across strategies without re-deriving what each concept "means" every time.

Pure lookup + set logic. No AI, no learned embeddings, no randomness here --
just a fixed, auditable mapping from the existing concept vocabulary
(backtest_engine.validator._KNOWN_INDICATORS) to DNA categories.
"""

DNA_CATEGORIES = ["trend", "momentum", "liquidity", "volume", "breakout", "session", "risk"]

# Which DNA categories a given indicator/concept name (as it appears in
# StrategyConfig.indicators[].name or concepts_used) belongs to. Concepts can
# legitimately belong to more than one category (e.g. "aggression" is both a
# volume-spike concept and a momentum/strength signal) -- DNA extraction
# below takes the union, it never forces a single label.
_CONCEPT_DNA = {
    "ema": {"trend"}, "sma": {"trend"}, "vwap": {"trend"}, "macd": {"trend", "momentum"},
    "rsi": {"momentum"}, "atr": {"risk"}, "volume": {"volume"},
    "support": {"liquidity"}, "resistance": {"liquidity"},
    "bos": {"liquidity", "breakout"}, "choch": {"liquidity", "breakout"},
    "fvg": {"breakout", "liquidity"}, "imbalance": {"breakout"},
    "order_block": {"liquidity"}, "breaker_block": {"liquidity"}, "mitigation_block": {"liquidity"},
    "liquidity_sweep": {"liquidity"}, "equal_highs_lows": {"liquidity"},
    "pdh": {"liquidity"}, "pdl": {"liquidity"}, "pdh_sweep": {"liquidity"}, "pdl_sweep": {"liquidity"},
    "candle_break": {"breakout"}, "swing_high": {"breakout", "liquidity"}, "swing_low": {"breakout", "liquidity"},
    "inside_bar": {"breakout"}, "engulfing": {"momentum", "breakout"}, "pin_bar": {"momentum"},
    "poc": {"volume"}, "value_area": {"volume"}, "lvn": {"volume"}, "hvn": {"volume"},
    "aggression": {"volume", "momentum"},
    "session_high_low": {"session"}, "session_open": {"session"},
}


def extract_dna(config):
    """config: a backtest_engine.strategy_config.StrategyConfig (or its
    .to_dict() form). Returns a sorted list of DNA category tags actually
    present in this strategy -- indicators, concepts_used, session/day/trend
    filters, and any configured risk-management field all contribute."""
    is_dict = isinstance(config, dict)

    def _get(name, default=None):
        return config.get(name, default) if is_dict else getattr(config, name, default)

    tags = set()
    for ind in _get("indicators", []) or []:
        name = ind.get("name") if isinstance(ind, dict) else getattr(ind, "name", None)
        tags |= _CONCEPT_DNA.get((name or "").lower(), set())
    for name in _get("concepts_used", []) or []:
        tags |= _CONCEPT_DNA.get((name or "").lower(), set())
    if _get("session_filter"):
        tags.add("session")
    if _get("day_filter"):
        tags.add("session")
    if _get("trend_filter"):
        tags.add("trend")
    stop_loss = _get("stop_loss")
    take_profit = _get("take_profit")
    sl_type = (stop_loss.get("type") if isinstance(stop_loss, dict) else getattr(stop_loss, "type", None)) if stop_loss else None
    tp_type = (take_profit.get("type") if isinstance(take_profit, dict) else getattr(take_profit, "type", None)) if take_profit else None
    if sl_type not in (None, "unknown") or tp_type not in (None, "unknown"):
        tags.add("risk")
    if _get("breakeven_at_rr"):
        tags.add("risk")
    if _get("risk_pct") or _get("risk_reward"):
        tags.add("risk")
    return sorted(tags)


def concepts_for_dna(tag):
    """Every known concept/indicator name tagged with this DNA category --
    the pool the deterministic builder draws from when assembling a new
    candidate around this block."""
    return sorted(name for name, tags in _CONCEPT_DNA.items() if tag in tags)


def dna_overlap(dna_a, dna_b):
    """Shared DNA tags between two strategies -- used by the mutator to
    decide whether two BOT strategies are similar enough that recombining
    them is meaningful, and by the deterministic builder to avoid producing
    a near-duplicate of an existing lineage."""
    return sorted(set(dna_a) & set(dna_b))

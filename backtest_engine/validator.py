"""Validates a parsed StrategyConfig before it's allowed to run. Every
check here maps directly to a spec requirement: missing timeframe, missing
entry/exit, missing SL/TP, invalid indicator, invalid RR, invalid risk.
Never guesses a fix -- only reports what's wrong so the dashboard can ask
the CEO to clarify.
"""

_KNOWN_INDICATORS = {
    "ema", "sma", "vwap", "rsi", "macd", "atr", "volume",
    "support", "resistance", "bos", "choch", "fvg",
    "order_block", "breaker_block", "liquidity_sweep",
    "pdh", "pdl", "pdh_sweep", "pdl_sweep",
}

_KNOWN_CONDITION_TYPES = {"indicator_compare", "price_compare", "concept", "session", "trend"}


def validate(config):
    """Returns a list of human-readable error strings. Empty list = valid,
    safe to run. Does not mutate `config`."""
    errors = []

    if "entry" not in config.timeframes:
        errors.append("Missing entry timeframe. Specify which timeframe entries are evaluated on.")

    if not config.entry_conditions:
        errors.append("Missing entry rules. No entry conditions were detected.")
    else:
        unclear = [c for c in config.entry_conditions if c.is_unclear()]
        if unclear:
            for c in unclear:
                errors.append(f'Unclear entry rule, needs clarification: "{c.text}"')

    if not config.exit_conditions and config.stop_loss.type == "unknown":
        errors.append("Missing exit rules. No exit conditions or stop-loss were detected.")
    else:
        unclear = [c for c in config.exit_conditions if c.is_unclear()]
        for c in unclear:
            errors.append(f'Unclear exit rule, needs clarification: "{c.text}"')

    if config.stop_loss.type == "unknown":
        errors.append("Missing stop loss. Specify a fixed %, an ATR multiple, or a structure-based SL.")

    if config.take_profit.type == "unknown":
        errors.append("Missing take profit. Specify a fixed %, or a risk:reward ratio.")

    if config.risk_pct is None:
        errors.append("Missing risk %. Specify how much of the balance to risk per trade.")
    elif not (0 < config.risk_pct <= 100):
        errors.append(f"Invalid risk %: {config.risk_pct}. Must be between 0 and 100.")

    if config.risk_reward is not None and config.risk_reward <= 0:
        errors.append(f"Invalid risk:reward ratio: {config.risk_reward}. Must be greater than 0.")

    for bucket_name in ("entry_conditions", "exit_conditions", "confirmation_conditions"):
        for cond in getattr(config, bucket_name):
            if cond.type not in _KNOWN_CONDITION_TYPES:
                continue
            if cond.type == "indicator_compare" and cond.indicator not in _KNOWN_INDICATORS:
                errors.append(f"Invalid indicator in {bucket_name.replace('_', ' ')}: {cond.indicator!r}")
            if cond.type == "concept" and cond.name not in _KNOWN_INDICATORS:
                errors.append(f"Invalid indicator/concept in {bucket_name.replace('_', ' ')}: {cond.name!r}")

    return errors


def is_valid(config):
    return len(validate(config)) == 0

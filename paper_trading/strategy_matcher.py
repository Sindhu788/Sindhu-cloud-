"""Strategy Engine: strategies are completely independent of each other
and of lessons. Each strategy in the library gets a small Paper-Trading-
only metadata record (enabled, priority, supported coins, supported
market types) stored separately from the StrategyConfig itself (via
paper_strategy_config) so the Backtesting Engine's schema never has to
change. "Required Timeframes"/"Required Indicators" already live on the
StrategyConfig (timeframes/indicators) -- no need to duplicate them.
"""

from backtest_engine import strategy_library as lib


def relevant_strategies(symbol, market_state):
    """Every saved strategy whose Paper Trading metadata says it's enabled
    and (if restricted) supports this coin and this market state. No
    restriction on either field means "supports everything" -- the bot
    auto-detects relevance from these declared fields, it doesn't guess.

    Multiple strategies can be enabled and trading simultaneously -- each
    gets its own independent book (balance/positions/guards, see
    paper_trading.guards.book_key), so there is no "only run this one"
    scoping here; the automation pipeline's Paper Trading handoff enables a
    strategy's config instead of narrowing this function."""
    from data_engine import storage

    configs = storage.list_paper_strategy_configs()
    matches = []
    for meta in lib.list_all():
        strategy_id = meta["id"]
        # Opt-in: a strategy with no config row has never been deliberately
        # activated -- see storage.get_paper_strategy_config()'s matching
        # default, which this mirrors.
        cfg_meta = configs.get(strategy_id, {"enabled": False, "priority": 5,
                                              "supported_coins": [], "supported_market_types": []})
        if not cfg_meta.get("enabled", False):
            continue
        supported_coins = cfg_meta.get("supported_coins") or []
        if supported_coins and symbol not in supported_coins:
            continue
        supported_types = cfg_meta.get("supported_market_types") or []
        if supported_types and market_state not in supported_types:
            continue

        try:
            config = lib.load(strategy_id)
        except FileNotFoundError:
            continue

        matches.append({
            "strategy_id": strategy_id,
            "strategy_name": meta["name"],
            "priority": cfg_meta.get("priority", 5),
            "config": config,
        })

    matches.sort(key=lambda m: -m["priority"])
    return matches

from data_engine.exchanges.binance import BinanceClient
from data_engine.exchanges.ccxt_client import CCXTClient

# ccxt exchange ids for our preferred exchanges. Gate.io's ccxt id is "gate",
# not "gateio".
CCXT_EXCHANGE_IDS = {"okx", "bybit", "bitget", "gate"}

ALL_EXCHANGE_IDS = ["binance"] + sorted(CCXT_EXCHANGE_IDS)

_cache = {}


def get_exchange_client(exchange_id):
    if exchange_id in _cache:
        return _cache[exchange_id]

    if exchange_id == "binance":
        client = BinanceClient()
    elif exchange_id in CCXT_EXCHANGE_IDS:
        client = CCXTClient(exchange_id)
    else:
        raise ValueError(
            f"Unsupported exchange {exchange_id!r}. Choose from {ALL_EXCHANGE_IDS}"
        )

    _cache[exchange_id] = client
    return client


# Urgent bug fix, 2026-09-08: Binance 451-blocked Render's Oregon servers
# (fixed 2026-09-07 by switching the cloud default to bybit), and now bybit
# ITSELF started 403-ing every single request from the same servers
# ("The Amazon CloudFront distribution is configured to block access from
# your country") -- confirmed live in the cloud paper-trading engine's tick
# logs, 100% of ticks failing at the very first exchange call for 3+ hours
# straight, so zero symbols were ever picked and zero trades could ever be
# evaluated. A crypto exchange's regional geo-block is decided entirely on
# their end and has now changed twice under this project without any code
# change here -- hardcoding a second "currently safe" exchange would just
# risk repeating the exact same failure a third time. Instead, this tries
# a short list of candidate exchanges in order and uses whichever one
# actually answers, remembering the last one that worked so almost every
# tick after the first only ever calls one exchange (same cost as before
# this fix) -- and falls through to the rest of the list again the moment
# that cached choice starts failing, without needing a code change or a
# redeploy the next time some exchange flips its policy.
_last_good_exchange = {"id": None}


def get_working_exchange_client(candidates, quote, log=None):
    """Try `candidates` (exchange ids) in order -- last-known-good first --
    and return (exchange_id, client, tradeable_symbols_dict) for the first
    one whose get_tradeable_symbols(quote) AND a one-symbol get_ohlcv probe
    both succeed. Raises RuntimeError with every candidate's failure reason
    if all of them fail."""
    ordered = list(candidates)
    last_good = _last_good_exchange["id"]
    if last_good in ordered:
        ordered.remove(last_good)
        ordered.insert(0, last_good)

    errors = []
    for exchange_id in ordered:
        try:
            client = get_exchange_client(exchange_id)
            tradeable = client.get_tradeable_symbols(quote)
            if not tradeable:
                raise RuntimeError("empty tradeable-symbols result")
            probe_symbol = next(iter(tradeable.values()))
            probe = client.get_ohlcv(probe_symbol, "1m", limit=2)
            if not probe:
                raise RuntimeError(f"empty OHLCV probe for {probe_symbol}")
            _last_good_exchange["id"] = exchange_id
            return exchange_id, client, tradeable
        except Exception as e:
            errors.append(f"{exchange_id}: {e!r}")
            if log:
                log(f"[exchange-failover] {exchange_id} unavailable: {e!r}")

    raise RuntimeError("all candidate exchanges failed: " + "; ".join(errors))


def last_known_working_exchange():
    """The exchange id get_working_exchange_client last confirmed actually
    answers, or None if no tick has run yet this process. Used by manual
    debug entry points (e.g. paper_trading.engine.run_single_coin_scan_now)
    that want the same currently-working exchange the real tick loop is
    using, without paying for their own failover probe."""
    return _last_good_exchange["id"]

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

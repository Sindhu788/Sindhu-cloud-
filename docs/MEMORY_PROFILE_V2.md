# MEMORY PROFILE V2 (master plan V2 R3, P11)

Target: Cloud RSS <= 400 MB steady, never > 450 MB. Before (F2): app RSS 409-415 MB in warm scans, Render metric max 431 MB.

## Where the memory goes (measured locally, stable venv, Windows; Linux on Render differs a little)
| Item | RSS | How measured |
|---|---|---|
| Python + `import cloud_runtime.app` (everything the Cloud service imports) | 141 MiB | psutil RSS after import |
| ... of which `import ccxt` (its `__init__` imports all 104 exchange classes) | 56 MiB | psutil delta, `import ccxt` alone |
| ... `ccxt` with only okx loaded | 21-22 MiB | same, okx only |
| ... `pandas` | 50 MiB | psutil delta |
| Live candle cache, one 20-day 1m series (28,800 rows x 7 float64 columns + index) | 1.76 MiB | DataFrame.memory_usage(deep) |
| ... x 50 coins, 1m only | ~88 MiB | arithmetic (1m dominates; 5m is 1/5 of it, 15m 1/15) |

The Cloud instance itself cannot be profiled from the laptop (no shell on Render free); the scan-time RSS comes from the
`[scan-coin] ... rss` log lines. tracemalloc was not run on Cloud: NOT VERIFIED which Python objects make up the rest.

## Changes (no strategy result changes)
1. **Lazy ccxt** (`data_engine/exchanges/lazy_ccxt.py`): the `ccxt` package is built from its real `__init__.py` without the 104
   per-exchange import lines; an exchange is imported the first time it is used. Cloud uses okx only. Off with `SINDHU_LAZY_CCXT=0`.
   Any problem falls back to the normal import. Measured: import RSS **141 -> 106 MiB (-35 MiB)**. Tests: `tests/test_lazy_ccxt.py`.
2. **Unused candle columns as float32** (`live_candles._compact`): `quote_volume` (okx: volume x close) and `trades` (okx: 0) are not
   read by any strategy; open/high/low/close/volume stay float64, so signals are identical. About **-11 MiB** for 50 coins of 1m.

Rejected: float32 for prices (changes indicator values and so signals), dropping columns (callers expect them), lowering the
20-day lookback (changes strategy warm-up).

## Before / after on Cloud
| | Before (3eabeac) | After (G1) |
|---|---|---|
| RSS warm scans | 409-415 MB | filled in after G1 |
| Render metric max | 431 MB | filled in after G1 |

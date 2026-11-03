# Fix log
- 2026-11-03 live candle paging (OKX 300 rows/request): fetch loop now pages until now. Tests: tests/test_live_candles_pagination.py. Result on Cloud: signals sent at 21:33Z.
- 2026-11-03 coin selection: optional coin_filter_mode=liquidity (Cloud set via Neon settings). Result: scans on majors.

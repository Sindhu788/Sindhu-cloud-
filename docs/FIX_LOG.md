# Fix log
- 2026-11-03 live candle paging (OKX 300 rows/request): fetch loop now pages until now. Tests: tests/test_live_candles_pagination.py. Result on Cloud: signals sent at 21:33Z.
- 2026-11-03 coin selection: optional coin_filter_mode=liquidity (Cloud set via Neon settings). Result: scans on majors.
- 2026-11-03 Step 6: /health reports version, commit and engine flag with no database access (test: p95 < 200 ms).
- 2026-11-03 Step 7: Lite layer (request queue, cache, dedupe, deferred heavy calls, waking-up state); polling slowed; dead catalog calls removed.
- 2026-11-04 Steps 8+18: owner-chat watchdog + daily summary; engine log no longer says "sent" for withheld signals.
- 2026-11-04 Step 17: decision trace and /api/ops/why; decisions flushed in batches of 10.
- 2026-11-04 Step 21: reconciliation (local and Cloud clean). Step 20: backup/restore scripts (45 tables ok). Step 19: CI workflow.
- 2026-11-04 QA fixes: version-history handler and four Settings loaders no longer throw after navigating away.
- 2026-11-04 Step 26: balance reset to $100 on Cloud and Local (archive 1,132 trades, counters kept, reconciliation OK after).

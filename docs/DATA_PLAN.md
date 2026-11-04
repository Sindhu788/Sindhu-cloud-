# Data plan (Day 5, 4 Nov 2026) - a clean, verified, protected 1-minute candle dataset

## Why
The owner's earlier backtest candles and backups were lost when Windows data was deleted. Backtests need fresh, checked, reproducible candles. Candles are used LOCALLY only: they are never written to Postgres and Cloud never needs them (Cloud fetches live candles from OKX in memory).

## Source decision
| Fact (checked on 4 Nov 2026 from this laptop, HTTP status only) | Result |
|---|---|
| `api.binance.com` ping / 1m klines | 200 / 200 |
| `data.binance.vision` (Binance's public bulk archive): monthly and daily 1m kline zip files and `.CHECKSUM` | 200 (e.g. BTCUSDT 2026-09 = 2.05 MB zip, 2025-11 = 2.17 MB) |
| OKX `/market/history-candles` | not reachable from this laptop (connection fails at once; OKX server-time endpoint answers) |
| Bybit | reachable from the laptop, but blocked from Render (Day 5 root cause) |
**Chosen source: Binance public archive.** It is the exchange's own bulk download (no API key, no scraping, no workaround): 1 request per coin-month instead of about 44 paged REST calls, and every file has a published sha256 that the downloader verifies. Cloud trades on OKX, so backtest candles differ slightly from live ones; the size of the difference is measured in docs/DATA_QUALITY.md (Step 13 comparison of the top coins).
Format facts handled by the code: spot archives from 2025-01-01 use MICROSECOND timestamps (converted to milliseconds); a coin that was not listed yet has no file (HTTP 404 -> recorded as "absent", never as an error); duplicate minutes are dropped (counted in the manifest); nothing is ever forward-filled.

## Universe (Step 7)
Rule: the 50 most liquid USDT spot pairs by **30-day quote volume at the build date** (sum of 30 daily candles), taken from the 120 largest by 24 h volume; stablecoins, fiat and leveraged tokens excluded; **tokenized stocks/ETFs (SNDKB, SPCXB, SOXLB, CRCLB, MSTRB, MUB, INTCB, GOOGLB, NVDAB, SKHYB) and gold tokens (XAUT, PAXG) excluded** (the first build on 4 Nov wrongly contained them; that file `universe_2026-11-04.json` is kept untouched and superseded by `universe_2026-11-04_v2.json`). Files: `D:\sindhu_data\universe\`.
Caveats: survivorship (pairs delisted before the build date are absent); ranking is as of today, not each historical date; a volume ranking favours coins that were hot in the last 30 days; young listings have fewer than 12 months (their earlier months are "absent").

## Size, disk and time
- One coin-month = 43,200 rows (30 days). Zip about 2.1 MB; stored as zstd Parquet about 2-3 MB (the first real file will confirm). 50 coins x 12 months = 600 files = **about 1.5 GB**; with the daily files of the current month and the resampled timeframes a safe upper bound is 5 GB.
- Free space: **D: 53 GB**, C: 63 GB (4 Nov). The plan keeps the 3x rule (needs under 18 GB): satisfied with a wide margin. The downloader stops by itself below 5 GB free.
- Requests: about 1,200 (600 zips + 600 checksums) + 50 daily files per day of the current month. 4 workers, exponential back-off with jitter, honours Retry-After. Expected duration: minutes to under 1 hour on this connection (the pilot measures it).

## Storage layout (outside git, never deleted)
`D:\sindhu_data\candles\binance\<SYMBOL>\1m\YYYY-MM.parquet` (finished months, read-only), `...\1m_daily\YYYY-MM-DD.parquet` (closed days of the current month, immutable), `manifest\manifest.json` (rows, sha256 of the file and of the zip, first/last timestamp, source URL), `manifest\progress.json` (every 30 s), `universe\`, `logs\`. `.gitignore` lists `/D:\sindhu_data`-style paths via the folder being outside the repo; every cleanup script excludes it; the code refuses to overwrite a finished file (`store.write_atomic` raises FileExistsError).

## Process
Pilot first: 20 coins x 6 months -> quality checks (docs/DATA_QUALITY.md) -> only if PASS expand to 50 x 12 months + current-month days. Runs as an independent detached process at below-normal CPU priority, keeps the laptop awake only while it runs (`SetThreadExecutionState`, no power plan is changed), resumes from the manifest after any stop.
Start: `D:\sindhu_venv_data\Scripts\python.exe -m data_platform.run_download --detach` (run from `D:\sindhu_clean`). Check: `type D:\sindhu_data\manifest\progress.json`.

## Environments (Windows Smart App Control)
Newly installed pandas files are blocked by Windows (same block as before; not worked around). `pyarrow` and `numpy` load fine, so the downloader runs in `D:\sindhu_venv_data` (pyarrow + numpy + requests, no pandas). The backtester runs in `D:\sindhu_venv_bt`, a copy of the trusted venv with pyarrow added (pandas 3.1.0 + pyarrow 21 round trip tested).

## Risks
Binance archive could be unreachable or change layout (the downloader fails loudly, resumes later); Binance prices are not OKX prices (measured in Step 13); 12 months is a limited sample (one market regime); survivorship caveats above.

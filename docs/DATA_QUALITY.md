# Data quality report (Day 5, 4-5 Nov 2026)

Dataset: Binance spot 1-minute candles, 50 coins (universe `universe_2026-11-04_v2.json`), 12 complete months (Nov 2025 - Oct 2026) plus the closed days of Nov 2026, in `D:\sindhu_data` (outside git). Source and plan: docs/DATA_PLAN.md. Policy: **candles are never fabricated or forward-filled**; incomplete windows are flagged and dropped by the resampler.

## Integrity audit (re-hash of every file)

- Files on disk: **700** (monthly + daily); manifest 'ok' entries: **700**; entries without a file: **0**; files whose sha256 differs from the manifest: **0**.
- Every monthly zip was verified against Binance's published sha256 before parsing; microsecond timestamps (spot archives from 2025) were converted to milliseconds; exact duplicate minutes would be dropped and counted (none needed).

## Pilot gate (20 coins x 6 months)

Verdict **PASS**: 109 of 110 coin-month files ok (99.09 %), 0 OHLC violations, 33,780 missing minutes (all from one young listing, see below). Rule: PASS = at least 90 % of present coin-month files have <= 0.5 % missing minutes, no OHLC violations, monotonic UTC-aligned time, and at least 80 % of coins have all but at most one month.

## Full dataset (50 coins x 12 months)

- Monthly files checked: **556**, ok: **552** (99.28 %). Verdict **PASS**.
- Rows: **24,311,220**; missing minutes: 42,060; OHLC violations: **0**; extreme-spike candles flagged for review: 49 (1-minute close/open move above 10 % or high/low range above 15 %).
- Coins with (nearly) full 12-month history: 45 of 50; the others were listed later (earlier months are 'absent' = the exchange has no file, which is correct, not an error).

### Files that did not pass (more than 0.5 % of minutes missing)

| Coin | Month | Rows | Expected | Missing minutes | Missing % | Gaps | Largest gap (min) |
|---|---|---|---|---|---|---|---|
| HYPEUSDT | 2026-09 | 9,420 | 43,200 | 33,780 | 78.194 | 0 | 0 |
| TONUSDT | 2026-06 | 41,940 | 43,200 | 1,260 | 2.917 | 0 | 0 |
| GRAMUSDT | 2026-07 | 42,720 | 44,640 | 1,920 | 4.301 | 0 | 0 |
| MARSCOINUSDT | 2026-09 | 38,100 | 43,200 | 5,100 | 11.806 | 0 | 0 |

These are first (partial) months of young listings or exchange maintenance gaps; the resampler drops every window that touches a missing minute, and backtests simply have no candles there.

### Per coin

| Coin | Months present | First month | Rows | Missing min | Gaps | Largest gap (min) | Zero-volume min | Spikes | Status |
|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 0 | 0 | ok |
| ETHUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 0 | 0 | ok |
| SOLUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 0 | 0 | ok |
| ZECUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 72 | 2 | ok |
| NEARUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 5,341 | 0 | ok |
| XRPUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 0 | 0 | ok |
| BNBUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 0 | 0 | ok |
| PEPEUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 2,491 | 0 | ok |
| DOGEUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 13 | 0 | ok |
| UNIUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 4,472 | 1 | ok |
| SUIUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 202 | 0 | ok |
| ENAUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 9,828 | 1 | ok |
| WLDUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 644 | 2 | ok |
| TRXUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 1 | 0 | ok |
| HYPEUSDT | 2 | 2026-09 | 54,060 | 33,780 | 0 | 0 | 181 | 0 | see below |
| RNDRUSDT | 0 | - | 0 | 0 | 0 | 0 | 0 | 0 | ok |
| AVAXUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 5,111 | 0 | ok |
| ADAUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 860 | 0 | ok |
| PUMPUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 9,239 | 1 | ok |
| LINKUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 2,816 | 0 | ok |
| STRKUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 61,784 | 0 | ok |
| TONUSDT | 8 | 2025-11 | 347,220 | 1,260 | 0 | 0 | 724 | 0 | see below |
| TAOUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 2,592 | 0 | ok |
| QNTUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 91,859 | 2 | ok |
| AAVEUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 1,484 | 0 | ok |
| LTCUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 3 | 0 | ok |
| ONDOUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 4,382 | 1 | ok |
| INJUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 15,986 | 3 | ok |
| FETUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 7,990 | 1 | ok |
| ARBUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 18,984 | 0 | ok |
| ZROUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 42,374 | 0 | ok |
| FILUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 24,703 | 1 | ok |
| TIAUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 12,366 | 2 | ok |
| HBARUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 4,116 | 0 | ok |
| TRUMPUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 9,482 | 1 | ok |
| XLMUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 5,665 | 2 | ok |
| APTUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 35,924 | 0 | ok |
| BCHUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 14,174 | 0 | ok |
| DOTUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 18,247 | 0 | ok |
| GTCUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 331,084 | 6 | ok |
| XPLUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 7,724 | 3 | ok |
| ASTERUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 55,366 | 1 | ok |
| BMTUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 186,656 | 6 | ok |
| GRAMUSDT | 4 | 2026-07 | 175,200 | 1,920 | 0 | 0 | 404 | 1 | see below |
| ERAUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 86,105 | 5 | ok |
| OPUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 35,347 | 0 | ok |
| PENGUUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 1,179 | 3 | ok |
| ICPUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 17,531 | 2 | ok |
| MARSCOINUSDT | 2 | 2026-09 | 82,740 | 5,100 | 0 | 0 | 1,496 | 2 | see below |
| DASHUSDT | 12 | 2025-11 | 525,600 | 0 | 0 | 0 | 16,521 | 0 | ok |

Zero-volume minutes are normal for thin coins (no trade in that minute) and are kept as they are.

## Resampled vs native candles (Step 11)

Method: for 5 coins (BTCUSDT, ETHUSDT, SOLUSDT, ZECUSDT, NEARUSDT) and 3 months (2026-08, 2026-09, 2026-10) the exchange's NATIVE candles of each interval were downloaded and compared with candles resampled from our 1-minute data (open = first open, high = max, low = min, close = last close, volume = sum; a window is built only when all its minutes exist; UTC alignment, weeks start Monday 00:00 UTC).

| Timeframe | coin-months | native windows | matched | only native | only resampled | OHLC identical | volume identical | max OHLC rel. diff | max volume rel. diff |
|---|---|---|---|---|---|---|---|---|---|
| 5m | 15 | 132,480 | 132,480 | 0 | 0 | 99.919 % | 100.000 % | 6.33e-04 | 3.97e-16 |
| 15m | 15 | 44,160 | 44,160 | 0 | 0 | 99.930 % | 100.000 % | 6.22e-04 | 6.21e-16 |
| 1h | 15 | 11,040 | 11,040 | 0 | 0 | 99.955 % | 100.000 % | 6.20e-04 | 4.94e-16 |
| 4h | 15 | 2,760 | 2,760 | 0 | 0 | 99.964 % | 100.000 % | 6.20e-04 | 4.35e-16 |
| 1d | 15 | 460 | 460 | 0 | 0 | 100.000 % | 100.000 % | 0.00e+00 | 3.69e-16 |

Reading: no window exists in only one of the two sets (so the window rules and alignment are right); volume matches to rounding; **99.92-99.96 % of OHLC values are bit-identical** and the largest relative difference is 0.06 % (daily candles: 100 % identical). The few differing candles are consistent with Binance's native candles being finalised from the trade stream slightly differently from the 1-minute archive (late-reported trades); NOT VERIFIED which exact trades differ (the archive does not carry trade-level data).
**Decision per timeframe:** backtests use candles **resampled from the verified 1-minute data for every timeframe**. Reasons: one single source of truth, identical rules for all timeframes, differences far below the 0.1 % trading cost, and native files exist only for some intervals. Native files stay in `candles_native/` for audits.

## What this dataset cannot tell you
Survivorship (delisted pairs absent); Binance prices differ slightly from OKX (the venue Cloud trades on; OKX history is not reachable from this PC); 12 months is one market regime; the universe is ranked on the last 30 days of volume.

## Binance vs another exchange (Step 13): how much do venues differ?
OKX (where Cloud trades) cannot be reached from this PC (its history endpoint fails at connection level), so Bybit's public spot klines are the stand-in. 1h candles, October 2026 (744 hours), top 10 coins of the universe, close prices of the same hour:
| Coin | common 1h candles | mean abs close diff (bps) | max (bps) | mean range diff (bps) | return correlation | median volume Binance/Bybit |
|---|---|---|---|---|---|---|
| BTCUSDT | 744 | 0.85 | 9.2 | 1.06 | 0.99975 | 1.77 |
| ETHUSDT | 744 | 0.77 | 7.9 | 1.23 | 0.99983 | 2.8 |
| SOLUSDT | 744 | 1.32 | 11.5 | 1.27 | 0.99962 | 5.69 |
| ZECUSDT | 0 | not listed on Bybit spot | | | | |
| NEARUSDT | 744 | 3.01 | 23.1 | 4.47 | 0.99953 | 5.67 |
| XRPUSDT | 744 | 1.21 | 8.0 | 1.85 | 0.99958 | 4.93 |
| BNBUSDT | 744 | 1.92 | 17.6 | 1.82 | 0.99858 | 26.99 |
| PEPEUSDT | 744 | 15.89 | 238.2 | 17.49 | 0.9885 | 4.96 |
| DOGEUSDT | 744 | 1.48 | 7.7 | 2.81 | 0.99942 | 7.09 |
| UNIUSDT | 744 | 4.35 | 45.1 | 4.06 | 0.99899 | 12.55 |
Reading: for the large coins the venues agree to about 1 basis point (0.01 %) on average, far below the 0.1 % commission; for thin coins (PEPE) the mean close difference is 16 bps with a worst hour of 238 bps and return correlation 0.9885, i.e. signals on thin coins will not transfer one-to-one between venues. This is a Binance-vs-Bybit number; the Binance-vs-OKX difference is NOT VERIFIED (not reachable from here) and should be measured once from Render (the Cloud process can fetch OKX candles) before trusting thin-coin results.
Daily incremental updates: `python -m data_platform.run_download --detach --no-expand` adds the newly closed days (finished files are skipped via the manifest); scheduling it is an owner step (docs/OWNER_TODO.md).

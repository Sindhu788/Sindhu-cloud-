# Weekly review routine (15 minutes, every Monday)

1. **Is Cloud alive?** Open `https://sindhu-cloud-1.onrender.com/health` (wakes it) - then the dashboard warning banner at the bottom must be empty. Banner items mean: engine OFF, signals BLOCKED (lists why), stale scan, skipped candle frames, database nearly full.
2. **Settings parity:** Local dashboard -> `/api/ops/settings-parity` should show 0 unexpected differences (engine_enabled / telegram send flags / token flags differ by design).
3. **Scorecard:** run `python scripts/weekly_scorecard.py docs/SCORECARD_<date>.md` on Local (reads the local DB) and on Cloud (set `DATABASE_URL` to Neon; read-only). Read: overall PF, Profitable+Challenge expectancy, worst coins, "Recommended pauses".
4. **Signals:** count messages sent this week (Telegram dashboard) vs. withheld (Paper Trading -> decision log reasons). Zero signals is acceptable if nothing qualified; it is NOT acceptable if the banner shows a blocker.
5. **Pauses:** for each strategy in "Recommended pauses" (>= 25 trades and win-rate upper bound below break-even) decide pause / keep. The system never pauses anything by itself except through its existing guards.
6. **Confidence check:** once >= 100 trades exist after 17 Sep, read the calibration table. AUC near 0.5 = the score is noise; do not trust high-confidence labels.
7. **Housekeeping:** DB size warning, Render free hours (shared across all free services), pending secret rotations, Definition-of-Done table (`docs/DEFINITION_OF_DONE.md`).
8. **Write down** any change you made in `docs/DECISIONS.md` (date, what, why).
9. **Pinger and scans (added Day 3):** `GET /api/ops/pinger` -> `pinger_active` true; Render log has `scan finished: complete` lines; `paper_scan_log` has `complete` rows and few `interrupted` ones; `/api/ops/warnings` has no `no_pinger` or `no_owner_chat`.


---
# Review of the week to 5 Nov 2026 - facts only

Everything here was read from a log, a file, a database export, a test or a command in the Day 5-7 sessions. "NOT VERIFIED" means I could not read it. The Day 6 scorecard (docs/WEEKLY_SCORECARD.md) is the shorter companion.

## 1. What was built (all with tests or a recorded run)
| Area | Built | Evidence |
|---|---|---|
| Cloud stability | exchange circuit breaker (Bybit geo-block), per-thread exchange clients, housekeeper thread, memory guard | Render logs: complete scans of 702-1,047 s, 0 errors; docs/SCAN_PROFILE.md |
| Candle data | protected Binance 1-minute dataset: 748 files, 24,587,700 rows, 47 coins with data in the test window; loader that serves closed candles only; full re-hash tool; second copy | `tools/verify_dataset.py`: 0 mismatches on D: and on the C: copy |
| Data upkeep | incremental updater with a dry run; unpublished files are "pending", not "absent" (fixed 5 Nov) | 15 downloader tests; docs/RUNBOOK.md section 12 |
| Backtest protocol | position-level metrics, cost model x1/x1.5/x2, 8 walk-forward windows, cluster bootstrap, random-entry null model, 3 baselines, false-discovery control | tests `test_metrics`, `test_rigor`, `test_cost_model`, `test_experiments` |
| New-idea testing | sandboxed candidate tool (no credentials, no network) with dossier and claim template | 7 isolation tests; demo run in about 2 minutes |
| Forward test | pre-registration, report (counts only before 5 Jan 2027) and append-only registration tool | 10 tests; first report: 0 forward positions |
| Signal safeguards (all OFF) | opposite-direction block, target-to-stop cap, hide confidence, disclaimer line, research-only timeframes, candle fingerprint logger, gate-uses-real-exchange | tests; simulations on the 12 sent signals (docs/OWNER_DECISIONS.md) |
| Backups | read-only Cloud export (retrying, now redacting secrets) + throwaway restore | 51 tables / 14,817 rows exported; restore: 49 tables OK, 0 mismatched |

## 2. What was measured
- **42 enabled strategies, 47 coins, 10 months, costs included:** 0 ROBUST, 1 FRAGILE, 36 FAILED, 5 INSUFFICIENT_DATA. 2 strategies beat random entries but still lose after costs. The one FRAGILE strategy (Ichimoku 1d Indicator-Exit) earns everything in one 5-week window, flips to a loss if its periods change by 10 %, and does worse than random shorts in a market where the average coin fell 43 %.
- **Public signals sent: 12** (not 11). All 12 came from strategies labelled FAILED; 10 of 12 from 1m/5m strategies; 5 closed (1 win, net -$1.08), 7 open. Confidence figure: AUC 0.463 (no information). None of the 12 messages had a disclaimer.
- **Why "Strong, 2/2":** the send gate scores confluence on Bybit (blocked from Cloud), so the market-regime factor silently drops out; the engine's own score at open (OKX) was 1.0 for only 3 of 12. With the real exchange 9 of 12 would have been withheld.
- **Paper trading since the 3 Nov reset:** 34 closed trades, 7 wins, net -$11.26, profit factor 0.17; 61 positions open. Very small sample.
- **Cloud:** complete scans 1,046 s / 702 s / 1,047 s (cold / warm / cold), 0 errors; memory per instance 389-470 MB (identical code ranged 389-459 MB, so no regression); the warm coin loop takes about 670 s and CPU plus candle download do not explain it (database round trips are the open hypothesis, NOT VERIFIED).
- **Instance behaviour:** 10 process starts in 11 hours (about 5-6 deploys, 4 wake-ups from sleep); no pinger yet.

## 3. What failed or turned out wrong
- Every strategy test: no edge after costs.
- My Day 6 statements that were wrong: "at least 11 signals" (12), "memory regression" (none), "Cloud time is mostly waiting for exchange pages" (not for warm scans). Corrected in docs/DAY7_BASELINE.md and docs/SCAN_PROFILE.md.
- I overwrote the Day 4 signal-quality document by mistake on Day 6 and restored it from git.
- The first Cloud export attempts of Day 7 failed twice (Neon closed the connection); the export is now retry-safe.
- Sleep/wake of the local app: NOT VERIFIED (not tested on purpose).

## 4. What was fixed (small, tested)
Metric defect (legs counted as trades); downloader recording unpublished files as permanently absent; backup files holding the Cloud API token and sync secret in plain text (new exports redact; the old folders still contain them); symbol/period names validated before they become file paths; ignore rules for data and backup folders.

## 5. Incidents
| When (UTC) | What | Effect |
|---|---|---|
| 4-5 Nov | free instance sleeps without a pinger, restarts on every request after idle | scans only complete while something keeps it awake; signals are irregular |
| 5 Nov 03:57 | a scan made no progress for 182 s inside a database commit (Neon) | one slow scan; recovered |
| every session end | the local app stops (processes started inside the assistant's session do not survive it) | start it again with `OPEN_SINDHU.cmd` |

## 6. Risks register
| # | Risk | Likelihood | Impact | Mitigation / owner |
|---|---|---|---|---|
| R1 | A member of the public groups trades real money on signals from failed strategies, with no disclaimer in the message | unknown (group membership NOT VERIFIED) | high | pause automatic signals (decision pack question 0) and/or switch on the disclaimer; owner |
| R2 | The send gate is easier to pass than designed (regime factor invisible) | certain (12 of 12) | medium | gate fix flag; owner |
| R3 | Cloud memory within 60 MB of the limit; spread of 70 MB between instances | medium | medium (guard drops optional work; a real OOM restart would lose a scan) | research-only 1m flag (-30 MB); log RSS per phase; owner/assistant |
| R4 | No owner alerts (chat id not configured): failures are silent | certain | medium | owner enters the chat id |
| R5 | Old Render services may hold the bot token | unknown (NOT VERIFIED) | medium | owner checks the 8 other services |
| R6 | Backups on disk contain two Cloud secrets (old folders) | present | medium | keep the folder private; rotate when rotation is decided; owner |
| R7 | Single copy of the candle data on one laptop (plus a copy on C:, possibly the same disk) | medium | low (rebuildable in about 30 minutes from Binance) | copy to another disk/cloud monthly; owner |
| R8 | Conclusions rest on 10 months of a falling market; Sep-Oct 2026 holdout contaminated | certain | medium | more history (24+ months), forward test; assistant |
| R9 | Cloud uses OKX, tests use Binance candles (1 bp apart on large coins, up to 15 bps on thin ones) | certain | low | fingerprint logger (OFF), comparison tool |

## 7. Open decisions (owner), with dates
| Decision | Where | Needed by |
|---|---|---|
| Pause or continue automatic public signals; which protections to switch on | docs/OWNER_DECISIONS.md (Day 7 pack) | **before the next signals go out** (today is best) |
| Start a pinger / choose hosting | docs/OWNER_TODO.md | this week (every scan statistic depends on it) |
| Enter the owner chat id | docs/OWNER_TODO.md | this week |
| Check the old Render services for the token variable | docs/OWNER_TODO.md | this week |
| Schedule the daily candle update | docs/RUNBOOK.md section 12 | this week |
| Approve 24+ more months of candle history for the top 20 coins | section 8 below | week 2 |
| Rotate the two Cloud secrets | docs/SECURITY_REVIEW.md #1 | when you decide on rotation |

## 8. Plan for the next 2-4 weeks
**Week 1 (stability first):** pinger and owner chat id; decide the signal question; set the first protections one at a time (disclaimer, gate fix, research-only); the assistant adds three small Cloud logging lines (RSS per phase, database seconds per scan, shortlist) to turn the open hypotheses into measurements.
**Week 2 (data):** with approval, download 24 more months for the top 20 coins (about 0.8 GB, additive) and re-run the whole protocol with a second market regime; schedule the daily update; copy the dataset to a second physical disk.
**Weeks 3-4 (candidates):** any new idea goes through `data_platform.candidate_eval` with a filled claim; only a ROBUST label is registered for the forward test (`tools/forward_register.py`); the forward report is produced weekly and shows counts only until 5 Jan 2027.
**Throughout:** no strategy parameter changes, no promotion, no real money.

## 9. Go-live status
See docs/GO_LIVE_CRITERIA.md (Day 7 table): 0 of 15 gates fully met.

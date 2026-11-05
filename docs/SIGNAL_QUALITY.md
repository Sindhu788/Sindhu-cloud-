# Signal quality, correctness and delivery (Day 4, 4 Nov 2026)

All numbers are read-only queries on the Cloud database (Neon) at about 16:30 UTC on 4 Nov 2026 unless stated. Nothing was changed. Small samples are labelled; none of this is proof of quality.

## 1. Signal funnel (Step 10)
Data limits: `paper_decision_log` keeps only the newest 2,000 rows (10 Sep - 4 Nov, mostly 10 Sep and 16 Oct, and 3-4 Nov), so it is a sample, not the whole history. `near_miss_log` is complete from 4 Sep (665 rows).

**A. What happens to candidates (decision log, 2,000 rows; "candidate" = a strategy whose entry rule fired on a coin)**
| Stage / gate | Rows | Share of the 1,446 candidates |
|---|---|---|
| Entry rule matched (candidate created) | 1,446 | 100 % |
| Rejected: `max coins for this strategy reached (5)` | 898 | 62.1 % |
| Rejected: strategy paused by Drawdown Protection (7 consecutive losses) | 326 | 22.5 % |
| Rejected: position lock (identical position already open) | 88 | 6.1 % |
| Rejected: duplicate signal (unchanged market condition) | 48 | 3.3 % |
| Rejected: opposite position already open (policy = block) | 29 | 2.0 % |
| Rejected: max positions per coin (5) | 20 | 1.4 % |
| Rejected: no stop-loss could be computed | 17 | 1.2 % |
| Rejected: cooldown 15 min | 2 | 0.1 % |
| **Opened (paper trade)** | **18** | **1.2 %** |
Not candidates: 554 "no_trade" rows (419 "No entry rule matched", 77 "Stale closed market candles rejected", 58 "Market data is empty").
**The single most rejecting gate is the per-strategy coin cap "max coins for this strategy (5)": 62 % of all rejected candidates**, followed by Drawdown Protection (22 %). Caveat: 1,278 of the rejections come from one day (10 Sep), so the proportions describe that period, not now. Trace since the 3 Nov restart (`paper_decision_trace`, 90 rows): drawdown_breaker 45, other 21, position_lock 12, opened 10, opposite_signal 1, sizing 1 (small sample).

**B. From an opened trade to a Telegram signal (near-miss log, 665 trades that did NOT qualify to be sent, 4 Sep - 4 Nov)**
| Reason it was not sent | Count | Share |
|---|---|---|
| Confluence not met (2 of 3 required: 354, 1 of 3: 278, 0 of 3: 5, other 2 of 2: 13) | 629 | 94.6 % |
| Strategy's live P&L negative | 28 | 4.2 % |
| Strategy paused by Drawdown Protection | 8 | 1.2 % |
Pattern reliability status was `insufficient_data` in **all 665** rows (every pattern has fewer than the 25 trades the Wilson gate needs). Since the 3 Nov restart there are 13 near misses, all "confluence 2 of 2, need 3": the check had only 2 factors available and requires 3, so that signal could not pass at that moment. Why only 2 factors are available on Cloud is NOT VERIFIED (needs a code read of `confluence.py`; gate not touched).
Of the 10 trades opened since the restart: 5 belong to the Losing group (not sent: correct), 5 to Profitable/Challenge; those sent: see section 2. Total automatic signals ever sent: 6.

## 2. Audit of the 6 signals actually sent (Step 11)
Checks done from the database only. NOT VERIFIED against exchange candles (OKX is blocked from this PC and the candle cache of the Cloud process cannot be read).
| # | Time (UTC) | Coin / side | Group | Entry | Stop | Target | R:R | Conf. | Stop on right side | Target on right side | Sent within 15 min | In message = DB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 56 | 3 Nov 19:12 | PUMP long | profitable | 0.004274 | 0.003927 | 0.007708 | **9.9** | 37.3 | yes | yes | yes (72 s) | yes |
| 57 | 3 Nov 21:33 | BTC long | profitable | 77,944.32 | 76,377.30 | 92,929.01 | **9.6** | 46.3 | yes | yes | yes (73 s) | yes |
| 60 | 3 Nov 21:38 | BTC short | profitable | 77,833.30 | 79,065.66 | 74,385.43 | 2.8 | 44.7 | yes | yes | yes (73 s) | yes |
| 65 | 4 Nov 03:46 | ETH long | challenge | 2,243.73 | 2,208.73 | 2,341.57 | 2.8 | 44.7 | yes | yes | yes (73 s) | yes |
| 68 | 4 Nov 08:42 | ETH short | profitable | 2,324.77 | 2,362.99 | 2,217.55 | 2.8 | 44.7 | yes | yes | yes (72 s) | yes |
| 70 | 4 Nov 08:55 | ZEC short | profitable | 1,290.46 | 1,312.67 | 1,227.95 | 2.8 | 44.7 | yes | yes | yes (73 s) | yes |
Group eligibility: 5 profitable + 1 challenge, 0 Losing (pass). Format: every message has symbol, direction, entry, stop, target, duration and confidence (pass).
**Anomalies**
1. Signals 56 and 57 have a target far away: BTC target is +19.2 % from entry (92,929 vs 77,944), PUMP +80 %, while the message says "a few hours to 1 day". A 9.6 reward/risk on a 15m strategy is not realistic for that duration. (Strategy: Ichimoku 15m indicator-exit - the target is likely a placeholder, the real exit is an indicator exit.) Severity: medium (misleading message), not a gate failure.
2. Signals show "Confidence 37-46 %" yet were graded "A" in the log. A grade A with confidence below 50 is inconsistent for a reader. Severity: low.
3. **Opposite-direction pairs:** BTC long 21:33 then BTC short 21:38 (5 min); ETH long 03:46 (still open) and ETH short 08:42 (both open at the same time). 2 pairs in 6 signals. Severity: medium (owner decision pending, docs/OWNER_DECISIONS.md section 3).
4. The send delay is a constant 72-73 s after position entry in all six cases (fresh, but suspiciously uniform: it is the sweep cadence plus processing; fine).
5. PUMP/USDT is a new, thin token; ZEC at 1,290 USDT and PUMP at 0.004 are what the Cloud feed reported; not checked against a second source (NOT VERIFIED).

## 3. Outcomes of the sent signals (Step 12) - sample size 6, too small to judge anything
| # | Coin / side | Status on 4 Nov ~16:30 | Result |
|---|---|---|---|
| 56 | PUMP long | still open (since 3 Nov 19:12) | unresolved |
| 57 | BTC long | closed at 76,316.21 (stop zone) | **loss -0.62** (1 trade) |
| 60 | BTC short | open | unresolved |
| 65 | ETH long | open | unresolved |
| 68 | ETH short | open | unresolved |
| 70 | ZEC short | open | unresolved |
1 closed trade (a loss), 5 open. Nothing can be concluded from 6 signals (the 25-trade rule is 4x larger).

## 4. Confidence calibration (Step 13) - history of all 1,142 closed trades that have a confidence score
Reliability table (confidence as "probability" vs actual win rate; wins = pnl > 0):
| Confidence bin | Trades | Mean confidence | Actual win rate | Gap (pts) |
|---|---|---|---|---|
| 50-55 | 14 | 52.0 | 57.1 % | +5.1 |
| 55-60 | 100 | 57.6 | 43.0 % | -14.6 |
| 60-65 | 172 | 62.3 | 41.9 % | -20.4 |
| 65-70 | 233 | 65.9 | 33.9 % | -32.0 |
| 70-75 | 202 | 70.5 | 30.2 % | -40.3 |
| 75-100 | 410 | 83.0 | 35.6 % | -47.4 |
| below 50 | 11 | 36-48 | 0 % (all 11 lost) | n < 25 per bin |
**Verdict: higher confidence does NOT mean a higher win rate; it is slightly the opposite.** Brier score 0.369 (always predicting the base rate 35.8 % gives 0.230, so the score is worse than a constant guess). AUC 0.471 (0.5 = no information; below 0.5 = slightly inverted). Same for the signal-eligible groups only (315 trades): AUC 0.464, the 70-75 bin wins 24 %. Sample sizes are large for the middle bins (100-410), so this is a firm finding for the old sample (29 Aug - 16 Sep).
**Post-17-Sep check: NOT VERIFIED.** Only 10 trades closed since (all losses, 0 wins), bins of 3-4. The system has since changed how confidence is scored (values now 33-48 % instead of 55-90 %), so the old table may not apply to it; at least 25 closed trades per bin are needed.

## 5. Telegram delivery audit (Step 14)
Whole log 27 Jul - 4 Nov (112 rows): automatic 6 sent / 53 not sent; daily report 32 sent / 7 failed; manual 3 sent / 9 failed; weekly digest 1 sent.
| Question | Answer | Evidence |
|---|---|---|
| Did a Losing-group trade ever produce a public signal? | **No: 0 messages** | join message log to groups: 0 rows with group = losing; 47 automatic attempts refused with "Telegram sending is withheld for strategies in the Losing group" |
| Other refusals (automatic) | 3 duplicate-guard refusals ("already sent a long ... within 15 min"), the rest "turned off"/gates | error text |
| Network failures | 10 "failed after 3 attempts: ConnectionError", 1 ProxyError, 2 ReadTimeout - **all between 28 Jul and 29 Aug** (local runs through the proxy); **none on Cloud since 3 Nov** | dates of failures |
| Retry queue now | empty (0 rows) | table count |
| Ordering | one send path, messages carry no sequence number; the 6 signals were sent in time order (checked by timestamp) | log |
| Which destinations | Cloud holds one bot token and one channel id (env vars; cannot be read from here). The channel fingerprint was NOT compared with the Profitable/Challenge group ids: NOT VERIFIED (the Losing-group filter works on the strategy's group, not on a destination) | - |
**Leak paths found:** (1) The daily report "Roz Ki Report" (32 messages sent so far) goes to the same public channel: it is not a trade signal but public (already in OWNER_TODO 12). (2) The `manual` trigger (dashboard "send") can send any position's message and bypasses the group filter by design (3 sent on 29 Jul, all on one position). Both are intentional owner features.

## 6. Duplicate and restart safety (Step 16)
The "already sent" memory is the database table `telegram_message_log` in Neon (not process memory): `sweep_unsent_qualifying_signals` skips every open position that already has a logged signal (`storage.has_telegram_signal_for_position`), and `duplicate_signal_check` blocks the same strategy+coin+direction inside the freshness window. A restart, redeploy or sleep/wake therefore cannot re-send an already logged signal; the freshness gate (15 min) also blocks late first sends. Proof: tests `test_telegram_hourly_sweep.py`, `test_signal_congestion_filter.py`, `test_telegram_freshness_gate.py` (all pass in the Day 4 full run); live: the 6 signals have exactly one automatic row each (the only position messaged more than once is a manual test on 29 Jul).
**Gap (low):** if the process dies in the second between Telegram accepting a message and the log row being written, that signal could be sent again by the next sweep (only inside the 15-minute window). Not reproduced.


---
# Day 6 additions (5 Nov 2026)


## D6-1. Confluence-gate fix flag `SINDHU_GATE_USE_POSITION_EXCHANGE` (Step 13) - OFF, not turned on
**What the gate reads today (flag OFF, unchanged behaviour).** `paper_trading/telegram_bot.py::_gate_exchange` returns `exchanges.json "default"`. In Cloud mode that is `bybit`. `score_confluence(strategy, symbol, exchange, market_state, session, direction)` then uses the exchange in two of its four factors:
1. *Market condition supports this signal* (`regime.classify_regime(exchange, symbol)` -> 72 h of 1h candles from that exchange). On Cloud Bybit is geo-blocked, the call fails or returns nothing, so the factor is `None` = "neutral, not counted".
2. *No other strategy already crowding this coin* (`storage.get_open_paper_positions(exchange, symbol)`): positions are stored under the exchange they trade on (OKX on Cloud), so asking for `bybit` finds none and the factor is always **True**.
Factors 3 (strategy not paused) and 4 (pattern memory, neutral below 5 samples) do not depend on the exchange.
**What the fix reads (flag ON):** the exchange stored on the position (`pos["exchange"]`, OKX on Cloud), so factor 1 is really computed and factor 2 really looks at open positions on that coin.
**Effect on the label (arithmetic from the code, factors 3 true and 4 neutral):** OFF = 2 of 2 counted factors true = "Strong" always. ON: regime true -> 3/3 Strong; regime false -> 2/3 = 0.67 = "Moderate"; regime false AND crowding false -> 1/3 = "Weak". So the fix can only lower labels, never raise them.
**How often would the regime factor be unfavourable?** The REAL `classify_regime` code was run on 18,040 72-hour windows (every 4th hour, 10 coins, 1 Nov 2025 - 31 Aug 2026, Binance 1h candles as a stand-in for OKX; script `tools/regime_distribution.py`): **ranging 74.2 %, trending 23.7 %, high_volatility 2.1 %**. `high_volatility` is always unfavourable (2.1 %). A trending regime is unfavourable when the signal's market_state is not trending, and ranging when it is trending; the signal's market_state is not in my data, so the exact unfavourable share is **NOT VERIFIED**; the lower bound is 2.1 %, the upper bound is 100 %.
**How many of the past candidates / sent signals would change: NOT VERIFIED.** (a) The 6 signals are described in section 2 above (Day 4, from Cloud queries) but without the candle history needed to replay the gate at send time; the local database only has 3 manual sends of an old DEXE position. (b) The crowding factor depends on which positions were open at each moment, which is not recoverable offline. What the owner can do after enabling the flag: nothing changes for public delivery of signals that were Strong with all factors true unless regime or crowding turns false, and then Strong -> Moderate/Weak (which only matters if `auto_send_high_confidence_only` is ON).
**Recommendation (not applied):** leave OFF until the Cloud-side fingerprint logger (Step 15) and the forward test are running; turning it on changes which signals count as "high confidence", which is an owner decision.

## D6-3. Prepared signal rules, OFF by default (Step 17)
Code: `paper_trading/signal_rules.py`, wired into `send_signal_for_position` right after the congestion check; tests `tests/test_signal_rules.py` (6 tests). With no environment variable set nothing is ever blocked (tested). They only withhold a Telegram message; the paper trade is untouched. Both are owner decisions (not applied):
| Rule | Switch (environment variable on Render) | Default |
|---|---|---|
| (a) block a second OPPOSITE-direction signal on the same coin within N minutes | `SINDHU_BLOCK_OPPOSITE_SIGNAL=1`, window `SINDHU_OPPOSITE_SIGNAL_WINDOW_MIN` (default 30) | OFF |
| (b) cap target distance at N times the stop distance | `SINDHU_MAX_TARGET_STOP_RATIO=5` (any number > 0) | OFF |
**Simulation on the 6 signals actually sent (rows from section 2 above, tested in `test_signal_rules.py`):** cap 5 would have withheld **#56 PUMP (9.9) and #57 BTC (9.6)** = 2 of 6; the 30-minute opposite rule would have withheld **#60 BTC short** (5 minutes after the BTC long #57) = 1 of 6; the ETH long/short pair is 4 h 56 min apart, so it needs a window of about 5 hours (a 360-minute window withholds #68). Together at the defaults: **3 of 6 signals (56, 57, 60) would not have been sent**, leaving ETH long 65, ETH short 68 and ZEC short 70. Sample size 6, so this shows what the rules do, not that they improve results (the 6 outcomes are too few: docs/SIGNAL_QUALITY.md section 3).

## D6-2. Why the confidence score does not predict wins (Step 16)
**Data:** local database `paper_positions`, 1,132 closed trades with a stored confidence, entries 29 Aug - 11 Sep 2026 (all BEFORE the 17 Sep recalibration, i.e. the old raw heuristic), base win rate 36.1 %. Script `tools/confidence_analysis.py` (read-only, numpy). Chronological split: train = older 60 % (679 trades), test = newer 40 % (453 trades). These trades are September paper results (see the contamination note in docs/BACKTEST_PROTOCOL.md section 8); here they are used only to study the score, not to pick strategies.
| Measure | Result |
|---|---|
| AUC of stored confidence, all 1,132 trades | **0.463** (bootstrap 95 % interval 0.428-0.497; 0.5 = coin flip) |
| AUC on the newer 40 % | 0.442 (interval 0.388-0.491) |
| Brier score on the test part | 0.363 vs **0.228** for always guessing the base rate (worse than a constant guess) |
| Offline recalibration (10-point buckets learned on the older 60 %, applied to the newer 40 %) | AUC 0.559, Brier 0.226 (about the base rate 0.228) - essentially no probability information gained |
| Logistic regression on confidence + direction + market_state + session (trained older 60 %) | test AUC 0.410 (0.355-0.464), Brier 0.241 - worse than no model |
**Reading:** out of sample no version I tried predicts wins better than the base rate; the stored confidence is, if anything, slightly anti-predictive (its interval lies below 0.5). Sample caveat: 1,132 trades from only two weeks of one market regime and 40-odd strategies, so the numbers describe that regime.
**Causes (what the evidence supports):**
1. *Not fitted to outcomes* (verified by reading `paper_trading/confidence.py`): 50 points + hand-picked bonuses (strategy version x 2, up to +20; number of lessons x 2; +15 when the trend agrees with the direction; -5 when ranging; a running win-rate term). None was ever fitted to results; the module's own docstring says so.
2. *Mostly ranks strategies, not setups:* the strategy alone explains **29 %** of the variance of the score (measured), through the constant version bonus; but strategy identity does not predict wins here either.
3. *Blind to direction, which dominated the outcome:* in the older 60 % longs won 40.7 % and shorts 33.5 %; in the newer 40 % longs won **18.6 %** and shorts **55.5 %**. The score only sees direction through the +15 trend-agreement bonus, so it cannot track this swing. **Regime shift** between train and test is the main reason offline models do not transfer.
4. *Leakage:* none found; the strategy running win rate is backward-looking at decision time. Regression to the mean of that term is NOT tested.
5. *Scaling / labels:* the score is clipped to 0-100 and the display after 17 Sep is replaced by the bucket's real win rate once a bucket has 25 trades (`confidence_calibration.py`); that cannot add information that the inputs do not contain. Label used here: win = position pnl > 0.
**Prepared (not enabled):** `SINDHU_HIDE_CONFIDENCE=1` removes the "Confidence: x %" line from outgoing Telegram messages (default OFF, so messages are unchanged); `tests/test_hide_confidence.py` (3 tests). Recommendation for the owner: until a calibrated model beats the base rate in the forward test, do not rely on the number; hiding it is an owner decision.

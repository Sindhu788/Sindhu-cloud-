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

---
# Day 7 additions (5 Nov 2026)

## D7-1. Why every public signal says "Strong, 2/2 factors" (Step 9) - root cause, with evidence
**Evidence 1 (Cloud database export, `telegram_message_log`):** all 12 automatic signals sent so far say "2/2 confluence factors match", the two being "Strategy not paused for safety" and "No other strategy already crowding this coin". The regime factor ("Market condition supports this signal") and the pattern-history factor ("0/25 trades so far") are in none of them.
**Evidence 2 (same export, `confluence_score_log` = the engine's own score when the position was opened, using the real trading exchange OKX):** for the SAME 12 positions the engine logged ratio **1.0 for 3**, **0.667 for 7** and **0.333 for 2**. So at open time the regime factor WAS counted (and was against the signal in 9 of 12), but the message sent about a minute later said 2/2. (Positions: a89fdb35 1.0, df69e9f9 1.0, 3d47a044 0.667, 50f02d29 0.667, 62e68847 0.333, 61f19ceb 0.667, 268bb395 0.667, 476e7aba 0.667, f11c5d5d 0.333, 90d82276 1.0, 9f464453 0.667, 40df27e7 0.667.)
**Code path (file and function):**
1. `paper_trading/telegram_bot.py::_gate_exchange(pos, exchanges_cfg)` (line 891) returns `exchanges.json "default"`, which is `bybit` in Cloud mode; the position itself is stored under `okx`.
2. It is used by the send gates `evaluate_auto_send` (~1729), the standard-tier gate (~1806), the near-miss logger (~1884) and `send_signal_for_position` (~1615) when they call `paper_trading/confluence.py::score_confluence(strategy, symbol, exchange, ...)`.
3. `score_confluence` lines 36-41: `regime_mod.classify_regime(exchange, symbol)` sits inside `try / except Exception: r = None`. For `bybit` on Cloud the chain `regime.classify_regime -> data_engine.resample.get_ohlcv -> live_candles.get_ohlcv_live -> get_exchange_client("bybit")` raises (Bybit answers HTTP 403 to Render; the Day 5 circuit breaker logs `[exchange-breaker] bybit OPEN for 900s: geo-block ... 403`). The exception is swallowed, `regime_ok = None` = "neutral, not counted".
4. Factor 3 ("no other strategy crowding") calls `storage.get_open_paper_positions("bybit", symbol)`; positions are stored under `okx`, so it finds none and is always True.
5. Factors 2 (not paused) and 4 (pattern memory, neutral below 5 samples, none yet) do not depend on the exchange. Result: only 2 of 4 factors are ever counted, both pass, ratio = 1.0.
**Why it matters:** the standard-tier gate (`evaluate_auto_send_standard`, line ~1812) sends when `ratio >= auto_send_min_confluence_ratio` (default 1.0 = every counted factor must pass). Because the regime factor is invisible to the gate, the bar is much easier to pass than designed. The engine's own number at open time (OKX) shows how much easier.
**Cloud setting that lets the standard tier reach the public:** Cloud `telegram_settings` holds only `master_send_enabled=True` and `auto_send_enabled=True`; `auto_send_high_confidence_only` is not set there, so the default **False** applies (the local copy has True). That is why signals labelled "tier=low" (not statistically confirmed by the 25-trade gate) were sent.
**The fix already exists, OFF:** `SINDHU_GATE_USE_POSITION_EXCHANGE=1` makes `_gate_exchange` return `pos["exchange"]` (OKX). No new code was needed and nothing was changed today.
**Simulated effect of that flag on the 12 sent signals (using the engine's OKX-based ratio as the stand-in for what the gate would compute with the flag ON; the gate runs about 70 s after the engine, so this is close, not exact):** the standard gate would still have passed **3 of 12** (ratio 1.0); **9 of 12 would have been withheld** (7 at 0.667, 2 at 0.333) because the ratio is below 1.0. Across all positions the engine scored since the Day 5 restart (3-5 Nov, 95 scores) only 10 (10.5 %) had ratio 1.0. Limits: n = 12 sent / 95 scored; ratios of 2/2 versus 3/3 cannot be told apart in the log; other gates (Losing group, target distance, duplicate guard) are unchanged.
**Not done, on purpose:** no gate was changed. A visible warning when the regime check fails (instead of silent "neutral") would help the owner, but it would live inside `score_confluence`; it is listed as a recommendation in docs/OWNER_DECISIONS.md.

## D7-2. Audit of every public signal sent so far (Step 10)
Source: Cloud database export of 5 Nov 2026 (`telegram_message_log` automatic + success, joined to `paper_positions`, `paper_strategy_groups`, `confluence_score_log`) and the Day 6 labels (`protocol_results.json` + `protocol_rigor.json`). Generated by `tools/signal_audit.py`. "Fresh" = seconds between position open and send. "Engine score at open" = confluence ratio the engine logged with the real exchange (OKX). "Regime tag shown" = what the message displayed about the market regime: nothing (the factor was not counted, see D7-1).

| # | Sent (UTC) | Coin | Side | Strategy | TF | Day 6 label | Group | Conf. | Target/stop | Fresh (s) | Engine score at open | Opposite signal same coin | Regime tag shown | Outcome so far |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-03 19:12 | PUMP/USDT | long | Ichimoku 15m Indicator-Exit [Manua | 15m | FAILED | profitable | 37.3 | 9.9 | 72 | 1.000 | - | none (not counted) | open |
| 2 | 2026-11-03 21:33 | BTC/USDT | long | Ichimoku 15m Indicator-Exit [Manua | 15m | FAILED | profitable | 46.29 | 9.6 | 73 | 1.000 | short 0.1 h later | none (not counted) | closed stop_loss -0.62 |
| 3 | 2026-11-03 21:38 | BTC/USDT | short | Daily Liquidity Scalping Strategy  | 1m | FAILED | profitable | 44.7 | 2.8 | 73 | 0.667 | long 0.1 h earlier | none (not counted) | closed stop_loss -0.70 |
| 4 | 2026-11-04 03:46 | ETH/USDT | long | Laxman Rekha 5-EMA Trigger-Candle  | 5m | FAILED | challenge | 44.7 | 2.8 | 73 | 0.667 | short 4.9 h later | none (not counted) | closed take_profit +1.57 |
| 5 | 2026-11-04 08:42 | ETH/USDT | short | Daily Liquidity Scalping Strategy  | 1m | FAILED | profitable | 44.7 | 2.8 | 72 | 0.333 | long 4.9 h earlier | none (not counted) | closed stop_loss -0.67 |
| 6 | 2026-11-04 08:55 | ZEC/USDT | short | Daily Liquidity Scalping Strategy  | 1m | FAILED | profitable | 44.7 | 2.8 | 73 | 0.667 | - | none (not counted) | closed stop_loss -0.66 |
| 7 | 2026-11-04 19:44 | SOL/USDT | long | Laxman Rekha 5-EMA Trigger-Candle  | 5m | FAILED | challenge | 44.7 | 2.7 | 4 | 0.667 | - | none (not counted) | open |
| 8 | 2026-11-04 20:21 | ETH/USDT | long | Laxman Rekha 5-EMA Trigger-Candle  | 5m | FAILED | challenge | 33.3 | 2.7 | 4 | 0.667 | short 11.6 h earlier | none (not counted) | open |
| 9 | 2026-11-04 20:27 | HYPE/USDT | long | Laxman Rekha 5-EMA Trigger-Candle  | 5m | FAILED | challenge | 37.3 | 2.8 | 4 | 0.333 | - | none (not counted) | open |
| 10 | 2026-11-04 20:29 | XRP/USDT | long | Laxman Rekha 5-EMA Trigger-Candle  | 5m | FAILED | challenge | 44.7 | 2.8 | 4 | 1.000 | - | none (not counted) | open |
| 11 | 2026-11-04 20:32 | DOGE/USDT | long | Laxman Rekha 5-EMA Trigger-Candle  | 5m | FAILED | challenge | 44.7 | 2.8 | 3 | 0.667 | - | none (not counted) | open |
| 12 | 2026-11-04 20:41 | NEAR/USDT | short | Liquidity Sweep + Engulfing Candle | 5m | FAILED | profitable | 33.3 | 1.8 | 4 | 0.667 | - | none (not counted) | open |

**Summary (n = 12 signals):**
- by Day 6 label: {'FAILED': 12}
- by entry timeframe: {'15m': 2, '1m': 3, '5m': 7}
- 1-minute timeframe: 3 of 12; 1m or 5m: 10 of 12
- by strategy: {'Ichimoku 15m Indicator-Exit [Manua': 2, 'Daily Liquidity Scalping Strategy ': 3, 'Laxman Rekha 5-EMA Trigger-Candle ': 6, 'Liquidity Sweep + Engulfing Candle': 1}
- by group now: {'profitable': 6, 'challenge': 6}
- target-to-stop above 5: 2 of 12; freshness at send (s): min 3, max 73
- outcome so far: 5 closed (wins 1, net -1.08), 7 still open
- engine score at open: 1.0 for 3, below 1.0 for 9

**Reading and limits:**
- **All 12 public signals came from strategies that Day 6 labelled FAILED** (profit factor below 1 after costs over 10 months and 47 coins; none is even FRAGILE). 10 of 12 came from 1-minute or 5-minute strategies, which the Cloud scan cannot serve on time (docs/STRATEGY_FORENSICS.md timeframe table); 3 came from the single 1m strategy. Laxman Rekha 5-EMA alone sent 6 (PF 0.78 in the backtest).
- Group labels (profitable / challenge) come from short live results, not from the backtest; the two do not agree.
- 2 of 12 have a target 9.6-9.9 times the stop (both Ichimoku 15m Indicator-Exit); 4 of 12 have an opposite-direction signal on the same coin (BTC 0.1 h apart, ETH 4.9 h and 11.6 h).
- 9 of 12 would NOT have been sent if the gate had used the real exchange (engine score below 1.0), see D7-1.
- Outcomes so far: 5 closed (1 win, net -$1.08), 7 still open. **Sample size 12 signals / 5 closed outcomes: far too small to judge profitability either way**; the evidence against these strategies is the 10-month backtest, not these 12 trades.
- Cloud currently has `auto_send_high_confidence_only` unset (default False): standard-tier ("tier=low", not confirmed by the 25-trade gate) signals are public. The local copy has it True.

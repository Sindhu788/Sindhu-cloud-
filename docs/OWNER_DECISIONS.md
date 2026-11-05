# Owner decisions pack (prepared 4 Nov 2026 - NOTHING below has been applied)

Three decisions are yours. Each section: current value, how to change it, evidence, pros/cons, my recommendation. Numbers come from read-only queries on the Cloud database (Neon) and from docs/PERFORMANCE_RECONCILIATION.md; "NOT VERIFIED" marks what could not be checked.

**Important context for all three:** the old sample is 1,132 closed trades from 29 Aug to 16 Sep (all strategies, PF 0.75, net -87.96 paper dollars). Since the engine restarted on 3 Nov, **8 trades have closed (all 8 were losses, total about -5.4)**. That is far below the 25-trade Wilson rule, so no new conclusion can be drawn from the new trades. **Confidence calibration after 17 Sep is therefore still NOT VERIFIED** (8 closed trades; the 25-trade gate is not met).

---
## 1. `auto_send_high_confidence_only` (send only High-tier signals?)
- **Current value:** not stored on Cloud = default **False** (Low-tier signals ARE sent). Read from the Cloud `telegram_settings` row on 4 Nov (null = default). The old local file reportedly has it ON (OWNER_TODO).
- **Change:** dashboard Settings > Telegram (auto-send options), or `POST /api/paper-trading/telegram/settings {"auto_send_high_confidence_only": true}`. Takes effect on the next signal; no redeploy.
- **What it does** (`telegram_bot.evaluate_auto_send_tier`): High tier = real confluence + the 25-trade Wilson gate. Low tier = qualifies on the lower bar. ON = Low-tier signals are generated and logged ("near-miss" log) but never reach Telegram.
- **Evidence:** 6 automatic signals have been sent so far (3 Nov 19:12 -> 4 Nov 08:55 UTC): Ichimoku 15m x2, Daily Liquidity Scalping x3, Laxman Rekha x1. Which tier each had: NOT VERIFIED (the message text did not contain a tier marker I could count). In the old sample the confidence number did not predict wins: confidence 50-60 -> 44.7 % wins (114 trades), 60-70 -> 37.3 % (405), 70+ -> 33.8 % (612).
- **Pros of ON:** fewer, better-evidenced signals; protects the channel's reputation. **Cons:** very few signals (the system already sends only a handful per day); fewer samples to learn from.
- **Recommendation:** keep **OFF while this is paper trading** (you need volume to learn which strategies work); switch **ON before any real-money use**. Re-decide when >= 25 post-17-Sep closed trades exist.

## 2. Strategy pauses (which strategies to stop trading)
- **Current value:** nothing paused by me. Groups: 12 profitable / 46 losing / 4 challenge; only profitable + challenge send to Telegram.
- **Change:** dashboard Paper Trading > strategy configs > Pause, or `POST /api/paper-trading/strategy-config/{strategy_id}/pause`; list with `GET /api/paper-trading/paused-strategies`. Reversible any time.
- **Evidence (old sample, trades to 16 Sep; weekly scorecard, Wilson-aware):** strategies with >= 25 trades: 16. **8 recommended pauses** (n >= 25 and the 95 % upper bound of the win rate is below break-even): FVG Pure + Inverse FVG (PF 0.49, net -3.66), Fair Value Gap Reversal (0.28, -3.82), Order Block Trading Strict (0.43, -4.35), Equal Highs/Lows Reversal (0.28, -4.55), HTF-LTF FVG/OB Confluence Entry (0.24, -5.41), Liquidity Sweep + CISD Pure Swing (0.47, -5.81), Fibonacci Golden Zone Retracement (0.24, -6.00), Market Structure Shift Reversal (0.15, -7.36). **8 watch:** Sniper Headshot Entry, FRVP POC Reversal, Candle Range Theory Loose, Range Breakout Volume Confirmation, Liquidity Sweep Reversal, Support/Resistance + Liquidity Sweep, Candlestick Pattern Reversal, HTF Key Level Engulfing Reversal. **38 strategies have < 25 trades: no conclusion possible.** All 8 pause candidates are already in the losing group (they never send signals).
- **Keep list (old sample, profitable/challenge, PF > 1):** Laxman Rekha 5-EMA (PF 1.80, 29 trades), Daily Liquidity Scalping (1.36, 38), Liquidity Sweep Multi-Confirmation (1.20, 42), Previous High/Low Reversal (1.05, 51).
- **Walk-forward warning (Sept = in-sample, Oct = out-of-sample, same 10 strategies, 3 coins, current engine):** no strategy was profitable in both months. Liquidity Sweep Multi-Confirmation PF 1.34 -> 0.40 and Daily Liquidity Scalping PF 1.00 -> 0.72 **collapsed**; Previous High/Low Reversal was 0.67 / 0.64. So three of the four "keep" names do not hold up out of sample (Laxman Rekha was not in that backtest: NOT VERIFIED). 60-day backtest: all 10 most-traded lost money.
- **Pros of pausing the 8:** stops paper losses from dragging the book and the drawdown breaker; less data to download per scan (likely faster scans on the free plan - NOT VERIFIED). **Cons:** a paused strategy gets no new trades, so it can never prove itself or recover; the evidence is from a short, old window (17 days).
- **Recommendation:** (a) **pause the 8** (their Wilson upper bound is below break-even - the evidence is as strong as this data allows, and none of them sends signals anyway); (b) leave the 8 "watch" strategies running until they reach 25+ new trades; (c) keep the four "keep" strategies **but treat them as unproven** - three failed walk-forward; consider that the public channel currently publishes only their signals; (d) revisit after 25 new closed trades per strategy.

## 3. Opposite-direction signal policy (long and short on the same coin close together)
- **Current value:** no rule exists - the system can open (and publish) a long and then a short on the same coin from different strategies. Example seen live: BTC long, then BTC short 5 minutes later.
- **Change:** there is **no setting for this today** - it needs a small code change (e.g. a setting "block opposite-direction public signal on the same coin for N minutes"). Not built, because it is your decision.
- **Evidence (1,161 positions in the Cloud database, entry times):**
  | Population | Opposite-direction pairs on the same coin within 15 min | within 30 min |
  |---|---|---|
  | all positions (1,161) | 180 | 236 |
  | signal-eligible groups only, profitable + challenge (325 positions) | **14** | **20** |
  A "pair" is two positions on one coin with opposite directions whose entries are that close; one position can be in several pairs. Among the 6 signals actually sent there is **one** such pair: BTC/USDT long at 21:33 UTC and short at 21:38 UTC on 3 Nov (Ichimoku 15m vs Daily Liquidity Scalping; docs/OWNER_TODO.md item 7). Whether the other 4 had an opposite signal on the same coin within 30 min: NOT VERIFIED.
- **Pros of blocking (public signals only):** followers never see "long BTC" and "short BTC" minutes apart; less confusion and fees. **Cons:** the paper trades still happen, so the public record and the paper record differ; a real reversal could be missed.
- **Recommendation:** block the **second, opposite** public signal on the same coin for **30 minutes** (paper trading unchanged). The 14-20 pairs in 325 signal-eligible positions (about 4-6 %) show it is rare, so the cost is small. I will implement it as an off-by-default setting if you say yes.

---
## Day 4 evidence added (4 Nov 2026)
- Strategy pauses: backtest windows (docs/STRATEGY_FORENSICS.md section 19) agree with the 8 recommended pauses; 7 of the 10 most-traded strategies lose in almost every 17-day window; none is robust. Recommendation unchanged and stronger: pause the 8 (no public signal changes), keep the rest as unproven.
- auto_send_high_confidence_only: confidence has AUC 0.47 over 1,142 trades (docs/SIGNAL_QUALITY.md section 4), so the "High confidence" label did not predict wins in the old sample. Turning the switch ON would not by itself select better trades; keep OFF while paper trading.
- Opposite-direction policy: two opposite pairs among the 6 sent signals (BTC 21:33/21:38 on 3 Nov, ETH 03:46 long still open + 08:42 short on 4 Nov) = 33 % of sent signals had an opposite twin within 6 hours. Recommendation unchanged (block the second opposite public signal for 30 min).
- New observation: 2 of 6 signals carried a take-profit 9.6x-9.9x the stop distance (BTC +19 % away) under the text "a few hours to 1 day"; please judge whether such signals should be sent (docs/SIGNAL_QUALITY.md section 2).



## Day 6: shortlist - recommendation only, nothing applied (Step 11)

Rules: **KEEP** = label ROBUST. **WATCH** = INSUFFICIENT_DATA with PF x1 > 1 (not enough trades to say anything, do not trust the number) or FRAGILE. **PAUSE** = FAILED with the upper end of the 95 % PF interval below 1 (a loss that is statistically clear after costs). FAILED strategies whose interval still touches 1 stay in the 'FAILED, not yet clear-cut' list. Groups below are from the LOCAL database copy (last assigned 16 Sep 2026); the Cloud groups may differ: NOT VERIFIED.

**KEEP: 0**

| Strategy | TF | Group (local copy) | Positions | PF x1 [95 % CI] | Label |
|---|---|---|---|---|---|

**WATCH: 4**

| Strategy | TF | Group (local copy) | Positions | PF x1 [95 % CI] | Label |
|---|---|---|---|---|---|
| Ichimoku 1d Trailing-SL [Manual Build] | 1d | profitable | 121 | 1.79 [0.00-5.80] | INSUFFICIENT_DATA |
| Ichimoku 15m Trailing-SL [Manual Build] | 15m | losing | 509 | 1.44 [0.00-5.08] | INSUFFICIENT_DATA |
| Ichimoku 1h Trailing-SL [Manual Build] | 1h | losing | 299 | 1.28 [0.00-4.12] | INSUFFICIENT_DATA |
| Ichimoku 1d Indicator-Exit [Manual Build] | 1d | losing | 576 | 1.09 [0.71-1.61] | FRAGILE |

**PAUSE (clear loss after costs): 36**

| Strategy | TF | Group (local copy) | Positions | PF x1 [95 % CI] | Label |
|---|---|---|---|---|---|
| Supply/Demand Zone Strategy [Manual Build] | 1h | losing | 494 | 0.78 [0.61-0.96] | FAILED |
| Laxman Rekha 5-EMA Trigger-Candle Strategy [Manual Build] | 5m | challenge | 13165 | 0.76 [0.71-0.82] | FAILED |
| Dumb Money Concepts -- Confirmation Entry [Manual Build] | 4h | losing | 1605 | 0.75 [0.56-0.96] | FAILED |
| Heikin Ashi Trend Reversal [Manual Build] | 15m | losing | 1313 | 0.75 [0.63-0.89] | FAILED |
| Kotegawa Bear Market Reversal Strategy [Manual Build] | 15m | profitable | 4288 | 0.73 [0.57-0.95] | FAILED |
| 4-Hour Range Breakout-Retest [Manual Build] | 5m | losing | 11813 | 0.73 [0.67-0.79] | FAILED |
| Asian Range London Sweep [Manual Build] | 5m | losing | 2715 | 0.71 [0.62-0.81] | FAILED |
| Daily Liquidity Scalping Strategy [Manual Build] | 1m | profitable | 28287 | 0.69 [0.63-0.76] | FAILED |
| Liquidity Sweep Reversal Strategy [Manual Build] | 15m | losing | 23212 | 0.69 [0.63-0.76] | FAILED |
| 9-20 EMA SMC Hybrid [Manual Build] | 15m | losing | 1766 | 0.67 [0.57-0.77] | FAILED |
| Liquidity Sweep Multi-Confirmation [Manual Build] | 5m | profitable | 7424 | 0.67 [0.56-0.79] | FAILED |
| Order Block Trading (Strict) [Manual Build] | 1h | losing | 4002 | 0.66 [0.51-0.86] | FAILED |
| Dumb Money Concepts -- Combined Confirmation [Manual Build] | 4h | losing | 1356 | 0.66 [0.46-0.88] | FAILED |
| Fibonacci Golden Zone Retracement [Manual Build] | 1h | losing | 17377 | 0.66 [0.61-0.70] | FAILED |
| PDH/PDL Multi-Timeframe Reversal [Manual Build] | 5m | challenge | 8495 | 0.65 [0.58-0.73] | FAILED |
| Market Structure Shift Reversal [Manual Build] | 15m | losing | 9570 | 0.65 [0.57-0.76] | FAILED |
| Liquidity Sweep + Engulfing Candle (Loose) [Manual Build] | 5m | profitable | 26935 | 0.64 [0.59-0.70] | FAILED |
| OTE Liquidity Sweep Reversal [Manual Build] | 15m | profitable | 13685 | 0.64 [0.58-0.70] | FAILED |
| Candle Range Theory (Loose) [Manual Build] | 1h | losing | 17679 | 0.63 [0.60-0.67] | FAILED |
| Liquidity Sweep + Engulfing Candle (Strict) [Manual Build] | 5m | losing | 17647 | 0.63 [0.59-0.67] | FAILED |
| Previous High/Low Reversal [Manual Build] | 15m | profitable | 15035 | 0.61 [0.55-0.69] | FAILED |
| Support/Resistance + Liquidity Sweep (Fixed-RR) [Manual Build] | 1h | losing | 6983 | 0.61 [0.54-0.70] | FAILED |
| Candle Range Theory (Strict) [Manual Build] | 1h | losing | 2953 | 0.60 [0.53-0.69] | FAILED |
| Equal Highs/Lows Reversal [Manual Build] | 15m | losing | 16803 | 0.60 [0.50-0.77] | FAILED |
| Ichimoku 1h Indicator-Exit [Manual Build] | 1h | losing | 13466 | 0.60 [0.51-0.71] | FAILED |
| Candlestick Pattern Reversal Strategy [Manual Build] | 15m | losing | 17792 | 0.60 [0.56-0.64] | FAILED |
| Liquidity Sweep + CISD (Pure Swing Variant) [Manual Build] | 5m | losing | 8967 | 0.60 [0.55-0.64] | FAILED |
| FVG Pure + Inverse FVG (Fixed 1:2) [Manual Build] | 1h | losing | 18695 | 0.59 [0.56-0.63] | FAILED |
| HTF-LTF FVG/OB Confluence Entry [Manual Build] | 15m | losing | 12360 | 0.59 [0.43-0.86] | FAILED |
| Fixed Range Volume Profile -- Market Shape [Manual Build] | 1h | losing | 19966 | 0.58 [0.55-0.62] | FAILED |
| FVG Momentum Pullback (Structure) [Manual Build] | 1h | losing | 8706 | 0.58 [0.50-0.67] | FAILED |
| Range Breakout Volume Confirmation [Manual Build] | 15m | losing | 3278 | 0.56 [0.40-0.86] | FAILED |
| FVG Pure + Inverse FVG (Structure) [Manual Build] | 1h | losing | 17026 | 0.55 [0.47-0.66] | FAILED |
| Donchian LWTI Volume Confluence [Manual Build] | 15m | losing | 5740 | 0.53 [0.38-0.76] | FAILED |
| Ichimoku 15m Indicator-Exit [Manual Build] | 15m | profitable | 48161 | 0.51 [0.43-0.59] | FAILED |
| Ichimoku 5m Indicator-Exit [Manual Build] | 5m | profitable | 134525 | 0.36 [0.31-0.41] | FAILED |

**FAILED or INSUFFICIENT, not yet clear-cut (no action recommended beyond watching): 2**

| Strategy | TF | Group (local copy) | Positions | PF x1 [95 % CI] | Label |
|---|---|---|---|---|---|
| SMA-Alignment Strategy (Approximate - ZIP Indicator Excluded) [Manual Build] | 1h | losing | 1696 | 0.74 [0.55-0.98] | INSUFFICIENT_DATA |
| SAR + SMC (CISD Entry) [Manual Build] | 5m | losing | 254 | 0.36 [0.23-0.54] | INSUFFICIENT_DATA |

**Expected effect on public signals:** only strategies in the Profitable or Challenge group can send Telegram signals (the Losing group sends none). Of the 36 PAUSE strategies, 10 are in those groups (local copy): Ichimoku 15m Indicator-Exit [Manual Build], OTE Liquidity Sweep Reversal [Manual Build], Laxman Rekha 5-EMA Trigger-Candle Strategy [Manual Build], Previous High/Low Reversal [Manual Build], Kotegawa Bear Market Reversal Strategy [Manual Build], PDH/PDL Multi-Timeframe Reversal [Manual Build], Ichimoku 5m Indicator-Exit [Manual Build], Liquidity Sweep + Engulfing Candle (Loose) [Manual Build], Daily Liquidity Scalping Strategy [Manual Build], Liquidity Sweep Multi-Confirmation [Manual Build]. Pausing them would remove their signals; strategies in the Losing group change nothing publicly. Of the 42 strategies, 11 are in the public groups (local copy).
Nothing was paused or changed. The decision belongs to the owner (docs/OWNER_DECISIONS.md).

---
# DAY 7 DECISION PACK (5 Nov 2026) - for each switch: what it does, what it would have changed, risks, my recommendation
Nothing below was changed. All numbers come from the 12 public signals actually sent (Cloud database export), the local scan tests, and Render logs. Small samples: 12 signals, 5 closed outcomes.

## 0. The big question first: should public signals continue while no strategy is validated?
**Facts (docs/SIGNAL_QUALITY.md D7-1, D7-2):**
- 12 signals were sent in 2 days. **All 12 came from strategies that failed the 10-month test** (profit factor below 1 after costs); 10 of the 12 from 1-minute / 5-minute strategies.
- The message said "Strong, 2/2 factors" in all 12 because the market-regime check is not seen by the send gate; the engine's own score at open was full (1.0) for only 3 of 12.
- Cloud sends the "standard tier" (not confirmed by the 25-trade gate) because `auto_send_high_confidence_only` is not set there (default False); your laptop copy has it True.
- **None of the 12 messages contains any disclaimer** (no "paper trading", no "not financial advice"): 0 of 12.
- Outcomes so far: 5 closed (1 win, net -$1.08), 7 open. Paper P&L since the reset: 34 closed trades, net -$11.26, profit factor 0.17 (2.3 days; very small sample).
- Who is in the groups: **NOT VERIFIED** (only you can see it in the Telegram app; steps in docs/OWNER_TODO.md, Day 7 readiness).
**Options:** (A) **Pause automatic public signals** until at least one strategy is ROBUST and passes the forward test: dashboard > Telegram > turn OFF `auto_send_enabled` (automatic signals only; daily reports keep working) or `master_send_enabled` (everything). No Render restart, takes effect at once, undo by turning it back ON. (B) Keep signals but switch on the protections below (research-only 1m,3m,5m + gate fix + target cap + disclaimer): of the 12 past signals this leaves 0. (C) Leave as is.
**My recommendation: A now.** Reason: the evidence shows the public bar is much easier to pass than designed and every signal came from a failed strategy; if even one member trades real money on these messages, the harm is real and the system itself says it has no proven edge. Revisit when the forward test (earliest 5 Jan 2027) says otherwise. This is your decision (it is an owner-decision setting, so I did not touch it).

## 1. What each switch would have changed (simulation on the 12 signals)
|---|---|---|
| today (nothing changed) | 12 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| research-only 1m | 9 | 1, 2, 4, 7, 8, 9, 10, 11, 12 |
| research-only 1m,3m,5m | 2 | 1, 2 |
| gate fix (real exchange) | 3 | 1, 2, 10 |
| target cap 5 | 10 | 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| opposite block 30 min | 11 | 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| opposite block 360 min | 10 | 1, 2, 4, 6, 7, 8, 9, 10, 11, 12 |
| hide confidence | 12 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 |
| gate fix + research-only 1m,3m,5m | 2 | 1, 2 |
| ALL: research-only + gate + cap 5 + opposite 30 | 0 | none |
Rules in time order; the opposite-direction rule counts only signals that would have been sent in that scenario. Method: `tools/flag_simulation.py`.

## 2. Switch by switch
| Switch (Render environment variable unless noted) | Default | What changes | Effect on the 12 past signals | Effect on scan time / memory | Risks | Recommendation |
|---|---|---|---|---|---|---|
| `SINDHU_RESEARCH_ONLY_TIMEFRAMES=1m,3m,5m` | OFF | strategies on those timeframes are no longer evaluated live; they stay enabled and testable locally | 2 of 12 would remain (10 came from 1m/5m) | local test: CPU 28.6 s -> 15.1 s, pages 1,331 -> 170, memory 192 -> 146 MB; **warm Cloud scan: small** (the 670 s coin loop is mostly not candle download, see SCAN_PROFILE section 12); 11 of 42 strategies are on 1m/5m | 11 strategies stop producing live paper trades (their Wilson/Evolution counts stop growing); they all failed the test, so little is lost | **ON (1m,3m,5m)** if signals continue; it also cuts cold-start time and about 46 MB |
| `SINDHU_GATE_USE_POSITION_EXCHANGE=1` | OFF | the confluence gate reads the real venue (OKX) instead of Bybit | 3 of 12 remain (9 withheld) | one more exchange call per candidate; negligible | none known; it only lowers labels and makes the bar the designed one | **ON** if signals continue (the correct fix) |
| `SINDHU_MAX_TARGET_STOP_RATIO=5` | OFF | withholds a signal whose target is more than 5 times the stop distance | 10 of 12 remain (2 withheld: PUMP 9.9, BTC 9.6) | none | a legitimately wide target would be withheld | ON if signals continue |
| `SINDHU_BLOCK_OPPOSITE_SIGNAL=1` (window `SINDHU_OPPOSITE_SIGNAL_WINDOW_MIN`, default 30) | OFF | withholds a signal opposite to one sent on the same coin within N minutes | 11 of 12 remain at 30 min (1 withheld: BTC short 0.1 h after BTC long); 10 at 360 min | none | hides a genuine reversal | ON, 30 min |
| `SINDHU_HIDE_CONFIDENCE=1` | OFF | removes the "Confidence: x %" line from messages | no change in what is sent; all 12 showed 33-46 % | none | readers lose a number that carries no information (AUC 0.463) | ON (the number misleads) |
| `SINDHU_SIGNAL_DISCLAIMER=1` (new today) | OFF | adds one last line: "Paper-trading test signal, educational only. Not financial advice." | none | none | none | **ON immediately if signals continue at all** |
| `SINDHU_CANDLE_FINGERPRINT=1` | OFF | prints one log line per new closed candle per coin/timeframe (price data only) | none | a few microseconds per call; at most 5,000 lines per run | log volume | ON for 1-2 days, then copy the lines to `tools/compare_fingerprints.py` to compare Cloud's OKX candles with the Binance data |
| `master_send_enabled` / `auto_send_enabled` (dashboard > Telegram, stored in the database) | both ON on Cloud | master = every Telegram send; auto = automatic signals | OFF stops all new signals | none | the groups hear nothing (say so in the group first) | see question 0 |
| `auto_send_high_confidence_only` (dashboard) | OFF on Cloud (True on the laptop) | True = only signals confirmed by the 25-trade Wilson gate; the standard tier is not sent | with True none of the 12 would have been sent (all were "tier=low") | none | far fewer signals | **ON** if signals continue (it is the stricter, intended mode); owner-decision setting, not touched |

## 3. How to change one Render variable (exact steps, one at a time)
1. dashboard.render.com > service **Sindhu-cloud--1** > left menu **Environment**.
2. **Add Environment Variable**: Key (for example `SINDHU_SIGNAL_DISCLAIMER`), Value `1`. Click **Save Changes**. Render restarts the service (about 2 minutes; the free instance restarts, a running scan is lost).
3. Wait until the service shows **Live**, then open `https://sindhu-cloud-1.onrender.com/health` (it must say `"status":"ok"`).
4. Only then add the next variable. One at a time, so that a problem can be traced to one change.
5. **Roll back:** Environment > the 3-dot menu of that variable > **Delete** > Save Changes. The default (OFF) is restored after the restart.
6. For the dashboard settings (`auto_send_enabled`, `master_send_enabled`, `auto_send_high_confidence_only`): the Telegram page of the dashboard; no restart.
**Suggested order if you keep signals:** disclaimer -> hide confidence -> gate fix -> target cap -> opposite block -> research-only 1m,3m,5m -> `auto_send_high_confidence_only` ON.

## 4. Other recommendations (no switch exists yet)
- Show a visible note when the regime check cannot be computed instead of silently counting 2 factors (small code change inside `score_confluence`; needs your OK because it is a gate module).
- Keep Cloud awake (pinger) before judging any scan statistics: today every number mixes cold starts and warm scans.

## Master plan A22 (2026-11-05): the seven flags, one line each (all OFF on Cloud; nothing was flipped)
| Flag | Recommendation |
|---|---|
| SINDHU_RESEARCH_ONLY_TIMEFRAMES | **Keep OFF.** You excluded P7: 1m/5m strategies stay on Cloud; their load is handled by A2/A4/A5 instead. |
| SINDHU_BLOCK_OPPOSITE_SIGNAL | Turn ON when public signals return: no two opposite calls on one coin within the window. |
| SINDHU_MAX_TARGET_STOP_RATIO | Turn ON when public signals return (caps unrealistic targets). |
| SINDHU_HIDE_CONFIDENCE | Turn ON when public signals return: confidence did not predict wins (AUC 0.463). |
| SINDHU_CANDLE_FINGERPRINT | Optional diagnosis only; leave OFF unless investigating a data question. |
| SINDHU_GATE_USE_POSITION_EXCHANGE | No longer needed on Cloud: master plan A7 makes the Cloud gate use the position's exchange anyway. |
| SINDHU_SIGNAL_DISCLAIMER | Obsolete: master plan A14 always adds the disclaimer and the validation class. |
| SINDHU_PUBLIC_SIGNALS (new, A14) | **Keep unset (OFF)** until a strategy is ROBUST and has passed its forward test. |

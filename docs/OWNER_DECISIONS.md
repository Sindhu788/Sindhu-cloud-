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

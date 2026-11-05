# Go-live readiness criteria (shadow mode only)

**This system is PAPER-ONLY. Nothing here is financial advice, a recommendation to trade, or a promise of profit. No real-money feature exists or is enabled.** These are the objective gates that must ALL be green before anyone even discusses trading real money, and even then only with money the owner can afford to lose, after independent advice. A student project that wins on paper can still lose real money (fees, slippage, latency, exchange outages, rule changes).

## How to read the status
`python scripts/go_live_status.py [out.md]` prints the table below from the live database (local SQLite or, with `DATABASE_URL`, Cloud Postgres). Thresholds live in `paper_trading/go_live.py` (`THRESHOLDS`) and must match this document. "NO DATA" is never a pass.

## Gates (measurable)
| # | Gate | Threshold | Why |
|---|---|---|---|
| 1 | Continuous paper trading on fresh live data | >= 28 days between first and last closed trade after 2026-09-17, engine running | one regime is not evidence; 4 weeks covers several weekly cycles |
| 2 | Closed trades on fresh data | >= 200 | below ~100 trades the profit factor is mostly noise (Wilson 25 is a per-pattern minimum, not a portfolio one) |
| 3 | Profit factor after fees and slippage (as modelled in each trade's P&L) | >= 1.3 | margin for costs the model misses |
| 4 | Max drawdown | <= 20 % of the $100 starting balance | survivable loss streaks |
| 5 | Stale-data decisions (market_data gate failures / all decisions, last 7 days) | <= 1 % | a strategy running on old candles proves nothing |
| 6 | Scanner uptime (hours with at least one finished scan, last 7 days) | >= 99 % | missed hours = missed or late signals |
| 7 | Accounting reconciliation (balance == start + closed P&L, every book) | clean every day | trust in the numbers |
| 8 | Always-on paid hosting (no free-plan sleep) | required | free plan sleeps after 15 min and stops scanning |
| 9 | Streaming candle feed with gap-fill (see LIVE_FEED_PLAN.md) | implemented and tested | REST polling can lag by a candle |
| 10 | Owner alerts and daily summary actually received | seen in the owner chat | silent failures are the usual cause of losses |
| 11 | Secrets rotated, backup restore re-tested, runbook rehearsed | done | recovery must work before it is needed |
| 12 | Out-of-sample check (docs/PERFORMANCE_RECONCILIATION.md, Step 22) shows no collapse for the strategies used | required | detects overfitting |
| 13 | Reviewed by an independent, qualified person | required | the author cannot be the only reviewer |

## Status on 4 Nov 2026 (computed from the databases; local and Cloud hold the same 1,132 pre-17-Sep trades)
| Gate | Current | Required | Status |
|---|---|---|---|
| Continuous paper days on fresh live data | n/a | >= 28 days (closed trades since 2026-09-17) | **NO DATA** |
| Closed trades on fresh data | n/a | >= 200 | **NO DATA** |
| Profit factor after fees/slippage (as modelled in pnl) | n/a | >= 1.3 | **NO DATA** |
| Max drawdown (% of $100 start) | n/a | <= 20.0 % | **NO DATA** |
| Stale-data decisions (last 7 days) | n/a | <= 1.0 % of decisions | **NO DATA** |
| Scanner uptime (hours with a scan, last 7 days) | n/a | >= 99.0 % | **NO DATA** |
| Accounting reconciliation clean | 1 | balance == start + closed P&L, every book | **PASS** |
| Always-on paid hosting (no sleep) | manual | paid plan or VPS; not the free plan | **MANUAL (not met: free plan)** |
| WebSocket/stream candle feed with gap-fill | manual | docs/LIVE_FEED_PLAN.md implemented | **MANUAL (not met: REST polling)** |
| Owner alerts + daily summary received | manual | personal_chat_id set and a real alert seen | **MANUAL (not met: owner chat not set)** |
| Secrets rotated, backups restore-tested, runbook rehearsed | manual | docs/OWNER_TODO.md sections N, K; docs/RUNBOOK.md | **MANUAL (backup restore tested; secrets not rotated)** |

**Conclusion: 1 of 11 automatic/manual gates is met. The system is nowhere near a go-live decision, and the pre-17-Sep record (PF 0.75, -87.96 on $100) and the 60-day backtests (all ten tested strategies PF < 1) point the other way.** The earliest honest review date is four weeks after the Cloud engine has run continuously on fresh data.

---
## Status on 5 Nov 2026 (Day 7) - every gate with its evidence (computed from the Cloud database export of 5 Nov 2026 and Render logs)
| # | Gate | Required | Current (evidence) | Status |
|---|---|---|---|---|
| 1 | Continuous paper trading on fresh live data | >= 28 days between first and last closed trade after 17 Sep, engine running | closed trades since 17 Sep: first 4 Nov, last 5 Nov = about 1-2 days (the engine was off from mid-September until 3 Nov; books reset 3 Nov 22:49 UTC) | **NOT MET** |
| 2 | Closed trades on fresh data | >= 200 | 34 | **NOT MET** |
| 3 | Profit factor after fees and slippage | >= 1.3 | 0.17 (34 trades, 7 wins, net -$11.26; sample far too small to conclude) | **NOT MET** |
| 4 | Max drawdown | <= 20 % of the $100 start | worst single book -$2.21 (2.2 %) since the reset | **MET on 2 days of data; meaningless until gate 1 is met** |
| 5 | Stale-data decisions (last 7 days) | <= 1 % | 9.3 % (131 of 1,411 decisions in the newest 2,000 decision-log rows were "Market data is empty" or "Stale closed market candles rejected"; the freshness guard is doing its job, the instance is not fed continuously) | **NOT MET** |
| 6 | Scanner uptime | >= 99 % of hours with a finished scan | 8.3 % (14 of 168 hours; the scan log only reaches back to 2 Nov); the free instance sleeps | **NOT MET** |
| 7 | Accounting reconciliation | clean every day | re-checked at the end of this run (Step 21): see docs/WEEKLY_REVIEW.md | see below |
| 8 | Always-on paid hosting | required | free plan; 10 process starts in 11 hours (4-5 Nov) | **NOT MET** |
| 9 | Streaming candle feed with gap-fill | implemented and tested | REST polling | **NOT MET** |
| 10 | Owner alerts and daily summary received | seen in the owner chat | Cloud log 5 Nov: "personal_chat_id not configured yet" | **NOT MET** |
| 11 | Secrets rotated, backup restore re-tested, runbook rehearsed | done | backup + throwaway restore re-tested 5 Nov (49 tables OK, 0 mismatched); runbook start/kill/duplicate rehearsed (docs/RUNBOOK.md 11e); secrets NOT rotated; sleep/wake NOT VERIFIED | **PARTIAL** |
| 12 | Out-of-sample check shows no collapse for the strategies used | required | 0 of 42 strategies ROBUST over 47 coins and 10 months; Sep-Oct 2026 holdout is not clean; forward test (earliest 5 Jan 2027) has no registered candidate | **NOT MET** |
| 13 | Independent qualified review | required | none | **NOT MET** |
| 14 (proposed, Day 7) | At least one strategy ROBUST under the corrected protocol AND passed the pre-registered forward test | required | none ROBUST; 1 FRAGILE | **NOT MET** |
| 15 (proposed, Day 7) | Public-signal gate sees the real venue and every message carries a disclaimer | required before ANY public signal | the gate reads Bybit on Cloud (9 of 12 sent signals would have been withheld with the real exchange); 0 of 12 messages had a disclaimer; the fixes exist but are OFF | **NOT MET** |
**Conclusion: 0 of 15 gates are fully met (gate 4 only trivially).** Nothing in the evidence supports any step towards real money. The system is a paper-trading research tool; its public signals should be treated as test messages (see docs/OWNER_DECISIONS.md, Day 7 decision pack, question 0).

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

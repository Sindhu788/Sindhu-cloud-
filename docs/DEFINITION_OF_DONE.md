# Definition of Done - "stable SINDHU" (status 4 Nov 2026)

PASS = verified with evidence in this repo's docs/tests/logs. OPEN = not true yet or needs the owner. NOT VERIFIED = could not be checked from here.

## A. Safety gates (never weakened)
| # | Item | Status | Evidence |
|---|---|---|---|
| A1 | Wilson 25-trade gate, Evolution 100-trade gate unchanged | PASS | `tests/test_safety_gates_block.py` |
| A2 | Kill switch, drawdown breaker, same-coin cap 5, 15 min freshness, 0.5 % drift, 60 s sweep unchanged | PASS | same file + `tests/test_signal_ownership.py` |
| A3 | Only Profitable/Challenge signals reach Telegram | PASS | `test_telegram_profitable_challenge_only.py`, `test_signal_start_readiness.py`, e2e test, and Cloud: Losing-group open positions have no Telegram rows |
| A4 | No runtime AI calls in backtest / paper / signals | PASS (core path) | engine core does not import `ai_integration`; opt-in advisors exist (`ai_trade_review.py`, `challenge_ai_advisor.py`), off unless enabled |
| A5 | Local can never publish public signals | PASS | `SINDHU_PUBLIC_SIGNAL_OWNER=disabled` + empty local token; probe logged `signal NOT sent` |

## B. Cloud signal chain
| # | Item | Status | Evidence |
|---|---|---|---|
| B1 | Cloud healthy on the current branch | PASS | `/health` ok (also reports commit and engine flag) |
| B2 | Paper Trading persisted ON | PASS | Neon `engine_enabled=true`; log `Restoring to ON` / `engine started` after every restart |
| B3 | Fresh data on all scanned coins | PASS (sample) | no `Stale closed market candles` warnings after the 3 Nov paging fix; trades opened at live prices |
| B4 | Groups populated | PASS | 12 profitable / 46 losing / 4 challenge; 42 enabled and unpaused |
| B5 | Delivery READY | PASS | log `Public signal delivery: READY` |
| B6 | Real signal sent to the channel | PASS | 3 Nov 21:33 UTC BTC/USDT long (format: pair, direction, entry, stop-loss, take-profit, duration, confidence) |
| B7 | Cloud stays awake | OPEN | needs the external pinger or a paid plan (OWNER_TODO K) |
| B8 | Owner alerts reach the owner | OPEN | `personal_chat_id` not set (OWNER_TODO 1) |
| B9 | Every decision explainable | PASS | `/api/ops/why`, decision trace table, tests |

## C. Quality of results
| # | Item | Status | Evidence |
|---|---|---|---|
| C1 | Profitable+Challenge expectancy > 0 over >= 100 trades | PASS (old sample) | +0.170 per trade, PF 1.52, 310 trades (Aug-Sep); re-check on fresh trades |
| C2 | Whole-book profit factor > 1 | OPEN | PF 0.75 |
| C3 | Strategies profitable in an independent backtest | OPEN | all 10 most-traded strategies PF < 1 over 60 days (Step 14) |
| C4 | Confidence predicts wins on post-17-Sep trades | NOT VERIFIED | no closed trade after 17 Sep exists yet |
| C5 | Conclusive losers paused or in the Losing group | OPEN | 8 recommended pauses (Step 15), owner decides |

## D. Engineering
| # | Item | Status | Evidence |
|---|---|---|---|
| D1 | Full test suite green | see PROGRESS_CHECKPOINT.md (final run) | |
| D2 | Dashboard QA | PASS with 10 low items | docs/DASHBOARD_QA.md (124/134 checks, desktop + phone) |
| D3 | Local and Cloud match except by design | PASS | docs/PARITY.md; `/api/ops/settings-parity` |
| D4 | Accounting reconciles | PASS | local and Cloud: 58 books, stored PnL == trades PnL (-87.96) |
| D5 | Backup restore tested | PASS | 45 tables, 10,377 rows, 0 mismatches |
| D6 | CI on every push | OPEN until the first GitHub run is seen | `.github/workflows/tests.yml` |
| D7 | Secrets out of config files and rotated | OPEN | OWNER_TODO N |
| D8 | One code line + rollback | PASS | `codex/trading-intelligence` = tested `recovery/clean`; tag `pre-recovery-backup`; docs/RUNBOOK.md |
| D9 | Go-live gates | OPEN (1 of 11) | docs/GO_LIVE_CRITERIA.md |

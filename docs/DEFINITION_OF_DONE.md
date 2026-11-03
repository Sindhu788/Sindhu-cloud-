# Definition of Done - "stable SINDHU" (status as of 2026-11-03)

PASS = verified with evidence. OPEN = not yet true / needs the owner. Re-check every Monday (see WEEKLY_REVIEW.md).

## A. Safety gates (must never be weakened)
| # | Item | Status | Evidence |
|---|---|---|---|
| A1 | Wilson 25-trade gate, Evolution 100-trade gate unchanged | PASS | `tests/test_safety_gates_block.py` |
| A2 | Kill switch, account drawdown breaker, same-coin cap 5, 15 min freshness, 0.5 % drift, 60 s sweep unchanged | PASS | same test file + `tests/test_signal_ownership.py` |
| A3 | Only Profitable/Challenge signals reach Telegram | PASS | `test_telegram_profitable_challenge_only.py`, `test_signal_start_readiness.py` |
| A4 | No runtime AI calls in backtest / paper / signals | PASS (core path) | `backtest_engine` and the paper engine core do not import `ai_integration` (opt-in advisors exist in `paper_trading/ai_trade_review.py`, `challenge_ai_advisor.py`, off unless enabled) |
| A5 | Local machine can never publish public signals | PASS | `SINDHU_PUBLIC_SIGNAL_OWNER=disabled` + empty local token; log line proof |

## B. Cloud signal chain
| # | Item | Status | Evidence |
|---|---|---|---|
| B1 | Cloud app healthy on current branch | PASS | `/health` ok, deploy live |
| B2 | Paper Trading persisted ON in Neon | PASS | `paper_trading_settings.engine_enabled=true` (3 Nov) |
| B3 | Engine actually running after restart | OPEN until verified in the Render log (`[paper-trading] Restoring to ON`) |
| B4 | Groups populated (Wilson-assigned) | PASS | 62 rows: 12 profitable / 46 losing / 4 challenge |
| B5 | Delivery READY in the startup log | PASS | `[telegram] Public signal delivery: READY` (15:51 UTC) |
| B6 | Telegram token + channel id present on Render | OPEN | cannot be read from outside; owner/manager confirms |
| B7 | First real signal sent and visible in the channel | OPEN | requires a qualifying signal; the system will not force one |
| B8 | Cloud stays awake (keep-alive) | OPEN | workflow `.github/workflows/keepalive.yml` added; needs GitHub Actions enabled / paid plan |

## C. Quality of results
| # | Item | Status | Evidence |
|---|---|---|---|
| C1 | Profitable+Challenge group expectancy > 0 over >= 100 trades | PASS (sample) | +0.170 / trade, PF 1.52, 310 trades (Aug-Sep) - re-check on new trades |
| C2 | Whole book profit factor > 1 | OPEN | PF 0.75 (Losing group drags) |
| C3 | Confidence score predicts wins (AUC > 0.55 on post-17-Sep trades, >= 100 trades) | OPEN | AUC 0.46 on old data; no post-fix trades yet |
| C4 | Every strategy with >= 25 trades and a statistically conclusive loss is paused or in the Losing group | OPEN | see scorecard recommendations |

## D. Engineering
| # | Item | Status | Evidence |
|---|---|---|---|
| D1 | Full test suite green | PASS | 2299+ passed, 0 failed (see PROGRESS_CHECKPOINT.md) |
| D2 | Pages load < 3 s (median < 1 s) on local | PASS | QA: median ~0.6 s |
| D3 | No JS console errors / dead endpoints on any page | see DASHBOARD_QA.md |
| D4 | Local and Cloud settings match except by design | PASS (tool) | `/api/ops/settings-parity`, `tests/test_ops_checks.py` |
| D5 | Backups: local DB + config, Neon export | PASS | `D:\sindhu_backup_*`, `cloud_export_*` |
| D6 | Secrets out of config files / rotated | OPEN | proxy, Neon, sync secret still plain text; owner must rotate |
| D7 | One code line, rollback tag | PASS | `codex/trading-intelligence` = recovery/clean tree, tag `pre-recovery-backup` |

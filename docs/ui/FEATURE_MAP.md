# FEATURE MAP (Master plan V2, F3 / W10)

Rule: **no feature may disappear.** Every page, button group and API that exists today is listed here with its new place.
Anything not rebuilt in the six new sections (Home, Trades, Strategies, Backtests, Settings, System) stays reachable under
Counts at F3: 38 SPA pages, 36 menu entries, 461 route decorators.
**More / Legacy** with the new shell and styles. Generated from `sindhu_web/api/home.py` NAV_PAGES, the `PAGES` router in
`sindhu_web/static/js/app.js` and every `@router`/`@app` route decorator; statuses are updated by PG8.

Final status (PG8, 2026-11-07): every row is NEW, MERGED or LEGACY; none removed. Status values: `TODO` (not migrated yet), `NEW` (rebuilt in the new section), `LEGACY` (reachable under More/Legacy, new styles),
`MERGED` (its content lives in a new section and the old page is also kept under More/Legacy).

## 1. Pages (hash routes)

| Old location (menu group / label) | Route | New location | Status |
|---|---|---|---|
| (not in menu; reached by link or MAIN_SECTIONS) | `#wallet` | Home (W4) | NEW |
| CEO / Orchestrator / Dashboard | `#home` | More/Legacy (old Dashboard; key cards move to Home W4) | MERGED |
| Data / Market | `#market` | More/Legacy | LEGACY |
| Data / Data | `#data` | More/Legacy | LEGACY |
| Research / Backtesting | `#backtesting` | Backtests (W7) | MERGED |
| Reporting / Reports | `#reports` | More/Legacy | LEGACY |
| Operations / System / Settings | `#settings` | Settings (W8) | MERGED |
| Research / Knowledge | `#knowledge` | More/Legacy | LEGACY |
| Strategy / Strategies | `#strategies` | Strategies (W6) | MERGED |
| Trading / Execution / Paper Trading | `#paper_trading` | Trades (W5) | MERGED |
| Strategy / Knowledge Compiler | `#knowledge_compiler` | More/Legacy | LEGACY |
| Strategy / AI Center | `#ai_center` | More/Legacy | LEGACY |
| Research / Backtest History | `#backtest_history` | Backtests (W7) - history; page kept under More/Legacy | MERGED |
| Research / Pipeline History | `#pipeline_history` | More/Legacy | LEGACY |
| Learning / Reflection / Evolution | `#evolution` | More/Legacy | LEGACY |
| Learning / Reflection / Evolution History | `#evolution_history` | More/Legacy | LEGACY |
| Strategy / SINDHU Strategy | `#sindhu_strategy` | More/Legacy | LEGACY |
| Trading / Execution / Signal Tracker | `#signal_tracker` | Trades (W5) - Signals tab; page kept under More/Legacy | MERGED |
| Learning / Reflection / Strategy Lab | `#strategy_lab` | More/Legacy | LEGACY |
| Learning / Reflection / Self-Learning Engine | `#self_learning` | More/Legacy | LEGACY |
| Trading / Execution / Challenge Mode | `#challenge_mode` | More/Legacy | LEGACY |
| (not in menu; reached by link or MAIN_SECTIONS) | `#strategy_wizard` | More/Legacy | LEGACY |
| Research / Web-Sourced Strategies | `#web_sourced_strategies` | More/Legacy | LEGACY |
| Operations / System / Control Center | `#control_center` | System (W9) | MERGED |
| Trading / Execution / Telegram Signals | `#telegram_dashboard` | More/Legacy | LEGACY |
| CEO / Orchestrator / SINDHU CEO | `#ceo` | More/Legacy | LEGACY |
| Strategy / Clarification | `#clarification_center` | More/Legacy | LEGACY |
| Trading / Execution / External Signal Tracker | `#external_signals` | More/Legacy | LEGACY |
| Research / Compare | `#compare` | Backtests (W7) - compare; page kept under More/Legacy | MERGED |
| Operations / System / Live Logs | `#live_logs` | System (W9) - logs link; page kept under More/Legacy | MERGED |
| Operations / System / Project Status | `#project_status` | System (W9) - versions; page kept under More/Legacy | MERGED |
| Operations / System / Incidents | `#incidents` | System (W9) - incidents; page kept under More/Legacy | MERGED |
| Learning / Reflection / Strategy Lifecycle | `#strategy_lifecycle` | Strategies (W6) - lifecycle badges; page kept under More/Legacy | MERGED |
| (not in menu; reached by link or MAIN_SECTIONS) | `#strategy_overview` | Strategies (W6) - overview; page kept under More/Legacy | MERGED |
| Risk / Risk | `#risk_department` | More/Legacy | LEGACY |
| Memory Core / Memory Core | `#memory_core` | More/Legacy | LEGACY |
| Operations / System / Configuration Panel | `#configuration_panel` | Settings (W8) - merged groups; page kept under More/Legacy | MERGED |
| Trading / Execution / Practice Mode | `#practice_mode` | More/Legacy | LEGACY |

Menu entries without a router entry: concepts

## 2. Other HTML pages

| File | Route | New location | Status |
|---|---|---|---|
| sindhu_web/static/login.html | `/login` | Login v2 (LG1-LG3) | NEW |
| sindhu_web/static/activity_log.html | `/static/activity_log.html` (no menu link) | More/Legacy | LEGACY |
| sindhu_web/static/concepts.html | menu "Concepts" (external_url) | More/Legacy (Knowledge) | LEGACY |

## 3. Global controls

| Control | Old location | New location | Status |
|---|---|---|---|
| Kill-switch button + confirm modal | ops banner (C2) | App shell banner (PG1) | NEW |
| Paper-trading banner, freshness dot | ops banner (C2) | App shell banner (PG1) | NEW |
| Logout | sidebar footer | user menu in shell (PG1) | NEW |
| Lite mode toggle (lite_mode.js) | topbar | Settings > Appearance (PG6) + shell | NEW |
| Session-expiry warning | topbar | shell (PG1) | NEW |
| Live log websocket `/ws/logs` | Live Logs page | System (W9) | NEW |

## 4. API routes (unchanged by the redesign; listed so every UI call has a home)

| File | Method | Path |
|---|---|---|
| cloud_runtime/app.py | GET | `/api/token` |
| cloud_runtime/app.py | GET | `/api/nav` |
| cloud_runtime/app.py | GET | `/api/home` |
| cloud_runtime/app.py | GET | `/health/details` |
| cloud_runtime/app.py | API_ROUTE | `/health` |
| cloud_runtime/app.py | GET | `/login` |
| cloud_runtime/app.py | GET | `/` |
| sindhu_web/api/activity.py | GET | `/api/activity` |
| sindhu_web/api/activity.py | GET | `/api/audit-trail` |
| sindhu_web/api/activity.py | GET | `/api/safety-gate-trip-history` |
| sindhu_web/api/activity.py | GET | `/api/undo-last-action` |
| sindhu_web/api/activity.py | POST | `/api/undo-last-action` |
| sindhu_web/api/ai_integration.py | GET | `/api/ai/providers` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/providers/{name}/config` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/providers/{name}/enable` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/providers/{name}/disable` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/providers/{name}/activate` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/providers/deactivate` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/providers/{name}/test` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/import` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/import/upload` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/import/youtube` |
| sindhu_web/api/ai_integration.py | GET | `/api/ai/usage` |
| sindhu_web/api/ai_integration.py | GET | `/api/ai/logs` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/cache/clear` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/import/queue` |
| sindhu_web/api/ai_integration.py | GET | `/api/ai/import/queue` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/import/queue/{item_id}/retry` |
| sindhu_web/api/ai_integration.py | POST | `/api/ai/import/queue/retry-failed` |
| sindhu_web/api/ai_integration.py | GET | `/api/ai/knowledge-score/{doc_id}` |
| sindhu_web/api/ai_integration.py | GET | `/api/ai/dictionary` |
| sindhu_web/api/ai_integration.py | GET | `/api/ai/dashboard` |
| sindhu_web/api/auth.py | GET | `/api/auth/status` |
| sindhu_web/api/auth.py | POST | `/api/auth/setup` |
| sindhu_web/api/auth.py | POST | `/api/auth/login` |
| sindhu_web/api/auth.py | POST | `/api/auth/logout` |
| sindhu_web/api/auth.py | POST | `/api/auth/change-password` |
| sindhu_web/api/automation_pipeline.py | GET | `/api/automation/optimizations` |
| sindhu_web/api/automation_pipeline.py | POST | `/api/automation/trigger` |
| sindhu_web/api/automation_pipeline.py | POST | `/api/automation/submit-batch` |
| sindhu_web/api/automation_pipeline.py | GET | `/api/automation/submission-queue` |
| sindhu_web/api/automation_pipeline.py | GET | `/api/automation/pipeline-history` |
| sindhu_web/api/automation_pipeline.py | GET | `/api/automation/pipeline-history/{job_id}` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/parse` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/similarity-check` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/strategies` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/strategies/{strategy_id}/versions` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/strategies/{strategy_id}/claim-check` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/strategies/{strategy_id}/versions/{version_a}/diff/{version_b}` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/restore-version` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/duplicates` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/archive` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/unarchive` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/strategies/{strategy_id}/extraction-verification` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/extraction-override` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/extraction-audit` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/strategies/{strategy_id}` |
| sindhu_web/api/backtesting.py | DELETE | `/api/backtesting/strategies/{strategy_id}` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/favourite` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/tags` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/comment` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategies/{strategy_id}/duplicate` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/coins` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/monte-carlo/{batch_id}` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/plausibility/{batch_id}` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/slippage-sensitivity/{batch_id}` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/duration-stats` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/what-if` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/feature-importance` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/cross-coin-validation/{batch_id}` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/strategy-variants` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/stress-test/{strategy_id}/{symbol}` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/genetic-optimize/{strategy_id}/{symbol}` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/trade-audit/{batch_id}/{symbol}/{timeframe}/{trade_num}` |
| sindhu_web/api/backtesting.py | GET | `/api/backtesting/replay/{batch_id}/{symbol}` |
| sindhu_web/api/backtesting.py | POST | `/api/backtesting/run` |
| sindhu_web/api/backup.py | POST | `/api/backup/create` |
| sindhu_web/api/backup.py | GET | `/api/backup/list` |
| sindhu_web/api/backup.py | POST | `/api/backup/restore` |
| sindhu_web/api/backup.py | POST | `/api/backup/verify` |
| sindhu_web/api/backup.py | GET | `/api/backup/drill-status` |
| sindhu_web/api/clarification.py | GET | `/api/backtesting/strategies/{strategy_id}/clarification` |
| sindhu_web/api/clarification.py | POST | `/api/backtesting/strategies/{strategy_id}/clarify` |
| sindhu_web/api/clarification.py | POST | `/api/backtesting/strategies/{strategy_id}/reextract-field` |
| sindhu_web/api/clarification.py | POST | `/api/backtesting/strategies/{strategy_id}/clarify/preview` |
| sindhu_web/api/clarification.py | GET | `/api/backtesting/clarification/all` |
| sindhu_web/api/clarification.py | GET | `/api/backtesting/strategies/{strategy_id}/read-mode` |
| sindhu_web/api/concepts_usage.py | GET | `/api/concepts/usage` |
| sindhu_web/api/concepts_usage.py | GET | `/api/concepts/family-tree` |
| sindhu_web/api/dashboard_scores.py | GET | `/api/module-health` |
| sindhu_web/api/dashboard_scores.py | GET | `/api/project-score` |
| sindhu_web/api/dashboard_scores.py | GET | `/api/decision-center` |
| sindhu_web/api/data.py | GET | `/api/data` |
| sindhu_web/api/data.py | GET | `/api/data/quality` |
| sindhu_web/api/data.py | POST | `/api/data/download` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/status` |
| sindhu_web/api/evolution.py | POST | `/api/evolution/start` |
| sindhu_web/api/evolution.py | POST | `/api/evolution/stop` |
| sindhu_web/api/evolution.py | POST | `/api/evolution/run-tick` |
| sindhu_web/api/evolution.py | POST | `/api/evolution/strategies/{base_id}/force-generation` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/learning-freeze` |
| sindhu_web/api/evolution.py | POST | `/api/evolution/learning-freeze/{strategy_id}` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/strategies` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/settings` |
| sindhu_web/api/evolution.py | POST | `/api/evolution/settings` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/strategies/{base_id}/lineage` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/strategies/{base_id}/explain` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/ranking` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/research/dna-correlations` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/lessons` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/champions` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/knowledge-versions` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/comparisons` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/weekly-reviews` |
| sindhu_web/api/evolution.py | POST | `/api/evolution/weekly-reviews/generate-now` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/history` |
| sindhu_web/api/evolution.py | GET | `/api/evolution/history/compare` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/channels` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/channels` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/channels/{channel_id}/enable` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/channels/{channel_id}/disable` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/channels/{channel_id}/rename` |
| sindhu_web/api/external_signals.py | DELETE | `/api/external-signals/channels/{channel_id}` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/channels/{channel_id}/messages` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/channels/{channel_id}/messages/manual` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/process-pending` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/channels/{channel_id}/signals` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/signals/{signal_id}/open-position` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/check-price-updates` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/channels/{channel_id}/positions` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/channels/{channel_id}/report` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/comparison` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/channels/{channel_id}/eligibility` |
| sindhu_web/api/external_signals.py | GET | `/api/external-signals/settings` |
| sindhu_web/api/external_signals.py | POST | `/api/external-signals/settings` |
| sindhu_web/api/feature_control.py | GET | `/api/feature-control/state` |
| sindhu_web/api/feature_control.py | POST | `/api/feature-control/toggle` |
| sindhu_web/api/feature_control.py | POST | `/api/feature-control/master-pause` |
| sindhu_web/api/home.py | GET | `/api/nav` |
| sindhu_web/api/home.py | GET | `/api/strategy-summary` |
| sindhu_web/api/home.py | GET | `/api/home` |
| sindhu_web/api/incidents.py | POST | `/api/incidents` |
| sindhu_web/api/incidents.py | GET | `/api/incidents` |
| sindhu_web/api/incidents.py | GET | `/api/incidents/{incident_id}` |
| sindhu_web/api/incidents.py | POST | `/api/incidents/{incident_id}/update` |
| sindhu_web/api/incidents.py | POST | `/api/incidents/{incident_id}/resolve` |
| sindhu_web/api/infra_weekly_digest.py | GET | `/api/infra-weekly-digest` |
| sindhu_web/api/infra_weekly_digest.py | POST | `/api/infra-weekly-digest/generate-now` |
| sindhu_web/api/jobs.py | GET | `/api/jobs` |
| sindhu_web/api/jobs.py | GET | `/api/jobs/{job_id}` |
| sindhu_web/api/jobs.py | POST | `/api/jobs/{job_id}/pause` |
| sindhu_web/api/jobs.py | POST | `/api/jobs/{job_id}/resume` |
| sindhu_web/api/jobs.py | POST | `/api/jobs/{job_id}/stop` |
| sindhu_web/api/knowledge.py | GET | `/api/knowledge/categories` |
| sindhu_web/api/knowledge.py | GET | `/api/knowledge/report` |
| sindhu_web/api/knowledge.py | GET | `/api/knowledge/lessons` |
| sindhu_web/api/knowledge.py | GET | `/api/knowledge/lessons/{lesson_id}` |
| sindhu_web/api/knowledge.py | POST | `/api/knowledge/lessons` |
| sindhu_web/api/knowledge.py | PUT | `/api/knowledge/lessons/{lesson_id}` |
| sindhu_web/api/knowledge.py | DELETE | `/api/knowledge/lessons/{lesson_id}` |
| sindhu_web/api/knowledge.py | POST | `/api/knowledge/lessons/{lesson_id}/duplicate` |
| sindhu_web/api/knowledge.py | POST | `/api/knowledge/lessons/{lesson_id}/status` |
| sindhu_web/api/knowledge_compiler.py | POST | `/api/knowledge-compiler/compile` |
| sindhu_web/api/knowledge_compiler.py | GET | `/api/knowledge-compiler/documents` |
| sindhu_web/api/knowledge_compiler.py | GET | `/api/knowledge-compiler/documents/{doc_id}` |
| sindhu_web/api/knowledge_compiler.py | GET | `/api/knowledge-compiler/concepts` |
| sindhu_web/api/manager_chat.py | POST | `/api/manager-chat/ask` |
| sindhu_web/api/market.py | GET | `/api/market` |
| sindhu_web/api/memory_core.py | GET | `/api/memory-core/checkpoints` |
| sindhu_web/api/network.py | GET | `/api/network` |
| sindhu_web/api/ops_checks.py | GET | `/api/ops/warnings` |
| sindhu_web/api/ops_checks.py | GET | `/api/ops/settings-snapshot` |
| sindhu_web/api/ops_checks.py | GET | `/api/ops/settings-snapshot-sync` |
| sindhu_web/api/ops_checks.py | GET | `/api/ops/settings-parity` |
| sindhu_web/api/ops_checks.py | GET | `/api/ops/why` |
| sindhu_web/api/ops_checks.py | GET | `/api/ops/why-summary` |
| sindhu_web/api/ops_checks.py | GET | `/api/ops/pinger` |
| sindhu_web/api/ops_checks.py | POST | `/api/ops/test-owner-alert` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/status` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/health-check` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/start` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/stop` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/kill-switch/status` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/kill-switch/activate` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/kill-switch/deactivate` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/account-drawdown-status` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/account-drawdown-resume` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/run-tick-now` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/run-coin-scan-now/{symbol}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/settings` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/settings` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/settings/defaults` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/settings/history` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/reset-balance/preview` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/reset-balance` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/positions` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/trades` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/positions/{position_id}/close` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/positions/{position_id}/note` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/decisions` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-performance` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/lesson-performance` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-config/enable-all` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-config/{strategy_id}` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-config/{strategy_id}` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-config/{strategy_id}/pause` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-config/{strategy_id}/resume` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-config/{strategy_id}/overrides` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-config/{strategy_id}/signal-filters` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-config/{strategy_id}/reset-stats/preview` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-config/{strategy_id}/reset-stats` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-config/{strategy_id}/reset-history` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-configs` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-overview` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/groups` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/style-breakdown` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/groups/{group_key}` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/groups/sync` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/groups/{strategy_id}/move` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/periods` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-periods/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-comparison/export` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/cloud-sync/status` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/cloud-sync/run-now` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/cloud-sync/download` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/cloud-sync/import` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/secret` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/target` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-sync/target` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-sync/trigger/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/log` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/status` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-sync/push` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/conflicts` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/timeline` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/bandwidth` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/offline-queue` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/strategy-sync/offline-queue/flush` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/strategy-sync/offline-queue/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/health-check` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-sync/cloud-state` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/cloud-status-for-auto-stop` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/cloud-aware-auto-stop/state` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/cloud-aware-auto-stop/resume` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/status-ping/state` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/status-ping/send-now` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/dashboard-badge-status` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/analytics` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/override/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/overrides` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/session-stats` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/hour-of-day-stats` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/coin-stats/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/coin-heatmap` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/coin-deep-dive/{symbol}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/alerts` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/custom-alert-rules` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/custom-alert-rules` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/custom-alert-rules/{rule_id}/enabled` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/custom-alert-rules/{rule_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/pattern-memory` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/balance-history/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/confluence-history/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/pattern-reliability` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/lesson-candidates` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/streak/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/genealogy/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/readiness/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/auto-avoid-rules` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/auto-avoid-rules/{rule_id}/deactivate` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/auto-lessons` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/auto-lessons/{lesson_id}/deactivate` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/goals` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/goals` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/goals/{goal_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/maintenance-mode` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/maintenance-mode/enter` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/maintenance-mode/exit` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/auto-downgrade/state` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/auto-downgrade/check-now` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/paused-strategies` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/resume/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/risk-metrics/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/ai-trade-review/settings` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/ai-trade-review/settings` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/ai-trade-review/{position_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/capital-allocations` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/capital-allocations/recompute-now` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/risk-pct-recommendations` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/risk-metrics-all` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/regime` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/regime/{symbol}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/correlation-warnings` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-correlation-matrix` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/portfolio` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/portfolio-risk-score` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/coin-exposure` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/duplicate-exposure-warnings` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-exposure` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/direction-exposure` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-profile/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/settings` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/settings` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/channel-override/{strategy_id}` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/test` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/test-signal` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/network-check` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/test-proxy` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/quiet-mode` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/telegram/quiet-mode` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/reactions/{position_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/reactions` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/live-stats/update-now` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/additional-channels` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/telegram/additional-channels/{channel_id}` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/snooze/{strategy_id}` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/telegram/snooze/{strategy_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/log` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/alert-status` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/send/{position_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/signals` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/analytics` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/status-summary` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/performance-report` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/delivery-log` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/telegram/daily-missed-opportunity-report/generate-now` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/near-misses` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/connection-status` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/health-score` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/best-strategy-this-month` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/best-check-time` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/strategy-config/{strategy_id}/confidence-trend` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/telegram/preview/{position_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/signal-tracker/feed` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/signal-tracker/match-table` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/challenge` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/challenge` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/challenge/clear` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/challenge/breakdown` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/attribution-breakdown` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/confidence-calibration` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/silent-strategies` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/challenge/best-portfolio` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/challenge/recommend` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/challenges` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/challenges` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/challenges/{challenge_id}/archive` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/challenges/{challenge_id}/extend` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/challenges/{challenge_id}/full-analysis` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/challenges/replay` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/challenges/rotation-suggestion` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/confluence-open-positions` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/confluence/{position_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/signal-detail/{position_id}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/graveyard` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/graveyard/check-similarity` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/retirement-suggestions` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/signal-history` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/active-signals` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/export-center/trades.csv` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/export-center/trades.json` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/trade-journal/export-pdf` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/coin-blacklist` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/coin-blacklist` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/coin-blacklist/{symbol}` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/coin-priority` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/coin-priority/pin` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/coin-priority/demote` |
| sindhu_web/api/paper_trading.py | DELETE | `/api/paper-trading/coin-priority/{symbol}` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/position-size-calculator` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/pattern-sharing/generate` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/pattern-sharing/suggestions` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/pattern-sharing/suggestions/{suggestion_id}/approve` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/pattern-sharing/suggestions/{suggestion_id}/reject` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/practice-mode/evaluate` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/weekly-reports` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/weekly-reports/generate-now` |
| sindhu_web/api/paper_trading.py | POST | `/api/paper-trading/private-report/send-now` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/private-report/status` |
| sindhu_web/api/paper_trading.py | GET | `/api/paper-trading/trade-audit/{position_id}` |
| sindhu_web/api/project_meta.py | GET | `/api/project-meta/dependency-map` |
| sindhu_web/api/project_meta.py | GET | `/api/project-meta/readiness` |
| sindhu_web/api/project_status.py | GET | `/api/compare-strategies` |
| sindhu_web/api/project_status.py | GET | `/api/compare-strategies/dual-tp` |
| sindhu_web/api/project_status.py | GET | `/api/live-logs` |
| sindhu_web/api/project_status.py | GET | `/api/what-changed` |
| sindhu_web/api/project_status.py | GET | `/api/session-handoff` |
| sindhu_web/api/project_status.py | GET | `/api/project-status` |
| sindhu_web/api/project_status.py | POST | `/api/feedback` |
| sindhu_web/api/project_status.py | GET | `/api/feedback` |
| sindhu_web/api/project_status.py | POST | `/api/feedback/{feedback_id}/status` |
| sindhu_web/api/project_status.py | POST | `/api/quick-notes` |
| sindhu_web/api/project_status.py | GET | `/api/quick-notes` |
| sindhu_web/api/project_status.py | DELETE | `/api/quick-notes/{note_id}` |
| sindhu_web/api/report_builder.py | POST | `/api/report-builder` |
| sindhu_web/api/reports.py | GET | `/api/reports` |
| sindhu_web/api/reports.py | GET | `/api/backtest-history` |
| sindhu_web/api/reports.py | POST | `/api/backtest-history/{batch_id}/rename` |
| sindhu_web/api/reports.py | GET | `/api/backtest-history/{batch_id}/comparison` |
| sindhu_web/api/reports.py | GET | `/api/reports/best-worst/strategies` |
| sindhu_web/api/reports.py | GET | `/api/reports/{batch_id}` |
| sindhu_web/api/reports.py | GET | `/api/reports/{batch_id}/condition-reports` |
| sindhu_web/api/reports.py | GET | `/api/reports/{batch_id}/trades` |
| sindhu_web/api/reports.py | GET | `/api/reports/{batch_id}/export/{fmt}` |
| sindhu_web/api/research.py | POST | `/api/research/search` |
| sindhu_web/api/research.py | POST | `/api/research/queue-url` |
| sindhu_web/api/research.py | GET | `/api/research/trusted-sources` |
| sindhu_web/api/research.py | GET | `/api/research/settings` |
| sindhu_web/api/research.py | POST | `/api/research/settings` |
| sindhu_web/api/research.py | GET | `/api/research/runs` |
| sindhu_web/api/research.py | GET | `/api/research/web-sourced-strategies` |
| sindhu_web/api/risk_department.py | GET | `/api/risk-department` |
| sindhu_web/api/search.py | GET | `/api/search` |
| sindhu_web/api/self_learning.py | GET | `/api/self-learning/status` |
| sindhu_web/api/self_learning.py | GET | `/api/self-learning/cycles` |
| sindhu_web/api/self_learning.py | GET | `/api/self-learning/attempts` |
| sindhu_web/api/self_learning.py | GET | `/api/self-learning/combination-scores` |
| sindhu_web/api/self_learning.py | POST | `/api/self-learning/run-now` |
| sindhu_web/api/settings.py | GET | `/api/settings` |
| sindhu_web/api/settings.py | POST | `/api/settings` |
| sindhu_web/api/settings.py | GET | `/api/settings/costs` |
| sindhu_web/api/settings.py | POST | `/api/settings/costs` |
| sindhu_web/api/settings.py | DELETE | `/api/settings/costs/{cost_id}` |
| sindhu_web/api/settings.py | GET | `/api/settings/coin-event-caution` |
| sindhu_web/api/settings.py | POST | `/api/settings/coin-event-caution` |
| sindhu_web/api/settings.py | GET | `/api/settings/coin-event-caution/{symbol}` |
| sindhu_web/api/sindhu_strategy.py | GET | `/api/sindhu-strategy/today` |
| sindhu_web/api/sindhu_strategy.py | GET | `/api/sindhu-strategy/daily-log` |
| sindhu_web/api/sindhu_strategy.py | GET | `/api/sindhu-strategy/candidates` |
| sindhu_web/api/sindhu_strategy.py | GET | `/api/sindhu-strategy/candidates/{candidate_id}` |
| sindhu_web/api/sindhu_strategy.py | POST | `/api/sindhu-strategy/generate` |
| sindhu_web/api/sindhu_strategy.py | POST | `/api/sindhu-strategy/candidates/{candidate_id}/backtest` |
| sindhu_web/api/strategy_lab.py | GET | `/api/strategy-lab/latest` |
| sindhu_web/api/strategy_lab.py | GET | `/api/strategy-lab/history` |
| sindhu_web/api/strategy_lab.py | POST | `/api/strategy-lab/scan-now` |
| sindhu_web/api/strategy_lab.py | POST | `/api/strategy-lab/approve` |
| sindhu_web/api/strategy_lifecycle.py | GET | `/api/strategy-lifecycle` |
| sindhu_web/api/strategy_lifecycle.py | GET | `/api/strategy-lifecycle/{strategy_id}/failure-reasons` |
| sindhu_web/api/summary.py | GET | `/api/summary` |
| sindhu_web/api/system.py | POST | `/api/system/restart-services` |
| sindhu_web/api/system.py | POST | `/api/system/client-diagnostics` |
| sindhu_web/api/system.py | GET | `/api/system/api-monitor` |
| sindhu_web/api/system.py | GET | `/api/system/health` |
| sindhu_web/api/system.py | GET | `/api/system/restart-analytics` |
| sindhu_web/api/time_machine.py | GET | `/api/time-machine/{date_str}` |
| sindhu_web/api/timeline_compare.py | GET | `/api/timeline-compare` |
| sindhu_web/api/wallet.py | GET | `/api/wallet` |
| sindhu_web/api/wallet.py | POST | `/api/wallet/unpause/{strategy_id}` |
| sindhu_web/api/weekly_snapshot.py | GET | `/api/weekly-snapshot/list` |
| sindhu_web/api/weekly_snapshot.py | POST | `/api/weekly-snapshot/create-now` |
| sindhu_web/api/weekly_snapshot.py | GET | `/api/weekly-snapshot/compare` |
| sindhu_web/api/wizard.py | GET | `/api/wizard/concept-library` |
| sindhu_web/api/wizard.py | POST | `/api/wizard/classify-other` |
| sindhu_web/api/wizard.py | POST | `/api/wizard/save` |
| sindhu_web/api/ws.py | WEBSOCKET | `/ws/logs` |
| sindhu_web/server.py | GET | `/api/token` |
| sindhu_web/server.py | GET | `/login` |
| sindhu_web/server.py | GET | `/` |
| sindhu_web/server.py | API_ROUTE | `/health` |
| sindhu_web/server.py | GET | `/health/details` |

## 5. Where things are now (PG8 summary)
- New app at `/`: Home, Trades, Strategies, Backtests, Settings, System, More / Legacy, UI kit (`/ui-kit`), command palette (Ctrl/Cmd+K).
- Old dashboard unchanged at **`/legacy`** (same app.js, now on the v2 colour tokens and fingerprinted assets). Every old hash link
  (`/#paper_trading`, `/#evolution` ...) still works: pages rebuilt in v2 open the new page, all others redirect to `/legacy#<page>`.
- MERGED = its main content is in the new section and the old page stays reachable under More / Legacy.
- Not rebuilt as new pages (LEGACY): research tools such as Evolution, Strategy Lab, Knowledge, AI Center, Telegram dashboard, Risk
  Department, Memory Core and the rest. They work as before, styled by the v2 tokens, but keep their old layout.

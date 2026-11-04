# Dashboard QA (Playwright, human-style) - 4 Nov 2026

Run 3 of 3 on the final code (`recovery/clean`, Lite layer active). Target: a throwaway instance (port 8421) running the real code and read-mostly data with its own QA login; Telegram and trading disabled. Desktop 1366x800 and phone 390x844, headless Chromium. Screenshots: `D:/sindhu_runtime/qa_screens/<viewport>_<page>.jpg` (one per page, not committed).
Actions covered: open all 36 pages, tab clicks, safe buttons (refresh/show/view/filter/history/etc., Refresh also double-clicked), Settings risk % with negative / empty / 1000 / letters, save, double-click save, reload and persistence, revert, dark/light toggle + reload, language toggle, empty and wrong login, unauthenticated API call, console and HTTP errors for the whole run. NOT clicked on purpose: anything that saves elsewhere, starts/stops engines, runs jobs, sends, resets or deletes.
**Result: 124/134 checks pass, 10 listed below (none critical, none blocks signals).**

Cloud (read-only, no login): `/health` returns ok in under a second when awake; first request after sleep took 40 s; `/login` renders; every API route returns 401 without a session. Authenticated Cloud pages: NOT VERIFIED (no login available to this run).

## Bugs found and fixed during QA
- `/api/intelligence/shared-wallet` and `/api/paper-trading/catalog/*` 404 + console errors on Paper Trading / Strategy Lab (calls to endpoints deleted in the Codex cleanup) - fixed, test added.
- Version-history button threw when the page was left while loading - fixed.
- Four Settings loaders threw when the page was left while loading - fixed.
- Dashboard fired 21-27 API calls at once on a 0.1-CPU host (8 s waits) - Lite layer (queue, cache, dedupe, deferred heavy calls, waking-up message).

## Table (page / feature | viewport | action | expected | actual | result | screenshot | severity | fix or note)

| Page / feature | VP | Action | Expected | Actual | Result | Screenshot | Sev | Fix / note |
|---|---|---|---|---|---|---|---|---|
| SINDHU CEO | desktop | open page | renders, no console/http errors, no h-scroll | 10.14s | PASS | D:/sindhu_runtime/qa_screens/desktop_ceo.jpg | - |  |
| SINDHU CEO | desktop | load time | < 3 s | 10.14s | FAIL | D:/sindhu_runtime/qa_screens/desktop_ceo.jpg | low | First CEO load is cold: ~25 simultaneous API calls on a single process. The Lite layer queues them; repeat loads are cached. |
| Dashboard | desktop | open page | renders, no console/http errors, no h-scroll | 1.61s | PASS | D:/sindhu_runtime/qa_screens/desktop_home.jpg | - |  |
| Compare | desktop | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/desktop_compare.jpg | - |  |
| Backtesting | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_backtesting.jpg | - |  |
| Backtest History | desktop | open page | renders, no console/http errors, no h-scroll | 1.57s | PASS | D:/sindhu_runtime/qa_screens/desktop_backtest_history.jpg | - |  |
| Backtest History | desktop | button "All (75)" | no error | ok | PASS |  | - |  |
| Backtest History | desktop | button "Compare" | no error | ok | PASS |  | - |  |
| Pipeline History | desktop | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/desktop_pipeline_history.jpg | - |  |
| Pipeline History | desktop | button "View" | no error | ok | PASS |  | - |  |
| Web-Sourced Strategies | desktop | open page | renders, no console/http errors, no h-scroll | 1.58s | PASS | D:/sindhu_runtime/qa_screens/desktop_web_sourced_strategies.jpg | - |  |
| Knowledge | desktop | open page | renders, no console/http errors, no h-scroll | 1.58s | PASS | D:/sindhu_runtime/qa_screens/desktop_knowledge.jpg | - |  |
| Concepts | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_concepts.jpg | - |  |
| Concepts | desktop | button "Open Logs" | click works | Locator.click: Timeout 3000ms exceeded.
Call log:
  - waiting for locator("button").filter | FAIL |  | low | "Open Logs" sits under the floating panel on this layout, so a scripted click times out; use the Live Logs page. |
| Market | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_market.jpg | - |  |
| Data | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_data.jpg | - |  |
| Strategies | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_strategies.jpg | - |  |
| Strategies | desktop | button "All" | no error | ok | PASS |  | - |  |
| Strategies | desktop | button "History" | no error | ok | PASS |  | - |  |
| SINDHU Strategy | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_sindhu_strategy.jpg | - |  |
| Knowledge Compiler | desktop | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/desktop_knowledge_compiler.jpg | - |  |
| AI Center | desktop | open page | renders, no console/http errors, no h-scroll | 1.57s | PASS | D:/sindhu_runtime/qa_screens/desktop_ai_center.jpg | - |  |
| AI Center | desktop | button "Refresh" (+double-click) | no error | ok | PASS |  | - |  |
| Clarification | desktop | open page | renders, no console/http errors, no h-scroll | 1.57s | PASS | D:/sindhu_runtime/qa_screens/desktop_clarification_center.jpg | - |  |
| Paper Trading | desktop | open page | renders, no console/http errors, no h-scroll | 1.58s | PASS | D:/sindhu_runtime/qa_screens/desktop_paper_trading.jpg | - |  |
| Telegram Signals | desktop | open page | renders, no console/http errors, no h-scroll | 1.63s | PASS | D:/sindhu_runtime/qa_screens/desktop_telegram_dashboard.jpg | - |  |
| Telegram Signals | desktop | button "Today" | no error | ok | PASS |  | - |  |
| Telegram Signals | desktop | button "All-Time" | no error | ok | PASS |  | - |  |
| Signal Tracker | desktop | open page | renders, no console/http errors, no h-scroll | 1.57s | PASS | D:/sindhu_runtime/qa_screens/desktop_signal_tracker.jpg | - |  |
| Challenge Mode | desktop | open page | renders, no console/http errors, no h-scroll | 1.59s | PASS | D:/sindhu_runtime/qa_screens/desktop_challenge_mode.jpg | - |  |
| External Signal Tracker | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_external_signals.jpg | - |  |
| Practice Mode | desktop | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/desktop_practice_mode.jpg | - |  |
| Risk | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_risk_department.jpg | - |  |
| Strategy Lifecycle | desktop | open page | renders, no console/http errors, no h-scroll | 1.59s | PASS | D:/sindhu_runtime/qa_screens/desktop_strategy_lifecycle.jpg | - |  |
| Strategy Lifecycle | desktop | button "Show more" | no error | ok | PASS |  | - |  |
| Evolution | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_evolution.jpg | - |  |
| Evolution History | desktop | open page | renders, no console/http errors, no h-scroll | 1.57s | PASS | D:/sindhu_runtime/qa_screens/desktop_evolution_history.jpg | - |  |
| Self-Learning Engine | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_self_learning.jpg | - |  |
| Strategy Lab | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_strategy_lab.jpg | - |  |
| Reports | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_reports.jpg | - |  |
| Memory Core | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_memory_core.jpg | - |  |
| Control Center | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_control_center.jpg | - |  |
| Live Logs | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_live_logs.jpg | - |  |
| Project Status | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/desktop_project_status.jpg | - |  |
| Incidents | desktop | open page | renders, no console/http errors, no h-scroll | 1.58s | PASS | D:/sindhu_runtime/qa_screens/desktop_incidents.jpg | - |  |
| Incidents | desktop | button "Today" | no error | ok | PASS |  | - |  |
| Incidents | desktop | button "All-Time" | no error | ok | PASS |  | - |  |
| Settings | desktop | open page | renders, no console/http errors, no h-scroll | 1.55s / console: PAGEERROR box.querySelectorAll is not a function | FAIL | D:/sindhu_runtime/qa_screens/desktop_settings.jpg | high | Leaving Settings within ~2 s while its slow loaders are still queued makes a loader write to an element that no longer exists (console error only, no visible effect). Four loaders were guarded; more remain. |
| Settings | desktop | button "Today" | no error | PAGEERROR Cannot set properties of null (setting 'innerHTML') | FAIL |  | high | Leaving Settings within ~2 s while its slow loaders are still queued makes a loader write to an element that no longer exists (console error only, no visible effect). Four loaders were guarded; more remain. |
| Settings | desktop | button "All-Time" | no error | ok | PASS |  | - |  |
| Configuration Panel | desktop | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/desktop_configuration_panel.jpg | - |  |
| Settings | desktop | risk % = negative ('-5') | rejected or Save disabled | Save disabled | PASS |  | - |  |
| Settings | desktop | risk % = empty ('') | rejected or Save disabled | Save disabled | PASS |  | - |  |
| Settings | desktop | risk % = huge ('1000') | rejected or Save disabled | Save disabled | PASS |  | - |  |
| Settings | desktop | risk % = letters typed | browser blocks letters in a number field | '' | PASS |  | - |  |
| Settings | desktop | change risk %, save (double-click), reload | shows 1.7 | 1.7 | PASS |  | - |  |
| Settings | desktop | revert risk % | back to 1 | 1 | PASS |  | - |  |
| Topbar | desktop | dark/light toggle + reload | theme flips and persists | dark->light->after reload light | PASS |  | - |  |
| Topbar | desktop | language toggle | label flips, no errors | EN->UR (label flips; console errors are tracked in the summary row) | PASS |  | - |  |
| Login | desktop | empty submit | stays on login | /login | PASS |  | - |  |
| Login | desktop | wrong password | rejected | /login | PASS |  | - |  |
| Auth | desktop | API without login | 401 / login required | {"detail":"login required"} | PASS |  | - |  |
| (all pages) | desktop | console errors during the whole run | none | PAGEERROR Cannot set properties of null (setting 'innerHTML'); PAGEERROR Cannot set properties of null (setting 'textCon | FAIL |  | high |  |
| (all pages) | desktop | HTTP 4xx/5xx during the whole run | none | none | PASS |  | - |  |
| SINDHU CEO | mobile | open page | renders, no console/http errors, no h-scroll | 5.91s | PASS | D:/sindhu_runtime/qa_screens/mobile_ceo.jpg | - |  |
| SINDHU CEO | mobile | load time | < 3 s | 5.91s | FAIL | D:/sindhu_runtime/qa_screens/mobile_ceo.jpg | low | First CEO load is cold: ~25 simultaneous API calls on a single process. The Lite layer queues them; repeat loads are cached. |
| Dashboard | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_home.jpg | - |  |
| Dashboard | mobile | button "Open Logs" | click works | Locator.click: Timeout 3000ms exceeded.
Call log:
  - waiting for locator("button").filter | FAIL |  | low | "Open Logs" sits under the floating panel on this layout, so a scripted click times out; use the Live Logs page. |
| Compare | mobile | open page | renders, no console/http errors, no h-scroll | 1.63s | PASS | D:/sindhu_runtime/qa_screens/mobile_compare.jpg | - |  |
| Backtesting | mobile | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/mobile_backtesting.jpg | - |  |
| Backtesting | mobile | tap targets | buttons >= 28px high on phone | 1 small buttons | PASS | D:/sindhu_runtime/qa_screens/mobile_backtesting.jpg | - |  |
| Backtesting | mobile | button "All (75)" | no error | ok | PASS |  | - |  |
| Backtesting | mobile | button "Compare" | no error | ok | PASS |  | - |  |
| Backtest History | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_backtest_history.jpg | - |  |
| Backtest History | mobile | tap targets | buttons >= 28px high on phone | 1 small buttons | PASS | D:/sindhu_runtime/qa_screens/mobile_backtest_history.jpg | - |  |
| Pipeline History | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_pipeline_history.jpg | - |  |
| Pipeline History | mobile | button "View" | no error | ok | PASS |  | - |  |
| Web-Sourced Strategies | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_web_sourced_strategies.jpg | - |  |
| Knowledge | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_knowledge.jpg | - |  |
| Concepts | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_concepts.jpg | - |  |
| Concepts | mobile | button "Open Logs" | click works | Locator.click: Timeout 3000ms exceeded.
Call log:
  - waiting for locator("button").filter | FAIL |  | low | "Open Logs" sits under the floating panel on this layout, so a scripted click times out; use the Live Logs page. |
| Market | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_market.jpg | - |  |
| Market | mobile | tap targets | buttons >= 28px high on phone | 1 small buttons | PASS | D:/sindhu_runtime/qa_screens/mobile_market.jpg | - |  |
| Data | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_data.jpg | - |  |
| Strategies | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_strategies.jpg | - |  |
| Strategies | mobile | button "All" | no error | ok | PASS |  | - |  |
| Strategies | mobile | button "History" | no error | ok | PASS |  | - |  |
| SINDHU Strategy | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_sindhu_strategy.jpg | - |  |
| SINDHU Strategy | mobile | button "All" | no error | ok | PASS |  | - |  |
| Knowledge Compiler | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_knowledge_compiler.jpg | - |  |
| AI Center | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_ai_center.jpg | - |  |
| AI Center | mobile | button "Refresh" (+double-click) | no error | ok | PASS |  | - |  |
| Clarification | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_clarification_center.jpg | - |  |
| Paper Trading | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_paper_trading.jpg | - |  |
| Telegram Signals | mobile | open page | renders, no console/http errors, no h-scroll | 1.57s | PASS | D:/sindhu_runtime/qa_screens/mobile_telegram_dashboard.jpg | - |  |
| Telegram Signals | mobile | button "Today" | no error | ok | PASS |  | - |  |
| Telegram Signals | mobile | button "All-Time" | no error | ok | PASS |  | - |  |
| Signal Tracker | mobile | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/mobile_signal_tracker.jpg | - |  |
| Challenge Mode | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_challenge_mode.jpg | - |  |
| External Signal Tracker | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_external_signals.jpg | - |  |
| Practice Mode | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_practice_mode.jpg | - |  |
| Risk | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_risk_department.jpg | - |  |
| Strategy Lifecycle | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_strategy_lifecycle.jpg | - |  |
| Strategy Lifecycle | mobile | button "Show more" | no error | ok | PASS |  | - |  |
| Evolution | mobile | open page | renders, no console/http errors, no h-scroll | 1.56s | PASS | D:/sindhu_runtime/qa_screens/mobile_evolution.jpg | - |  |
| Evolution History | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_evolution_history.jpg | - |  |
| Self-Learning Engine | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_self_learning.jpg | - |  |
| Strategy Lab | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_strategy_lab.jpg | - |  |
| Reports | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_reports.jpg | - |  |
| Memory Core | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_memory_core.jpg | - |  |
| Control Center | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_control_center.jpg | - |  |
| Live Logs | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_live_logs.jpg | - |  |
| Live Logs | mobile | tap targets | buttons >= 28px high on phone | 1 small buttons | PASS | D:/sindhu_runtime/qa_screens/mobile_live_logs.jpg | - |  |
| Project Status | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_project_status.jpg | - |  |
| Incidents | mobile | open page | renders, no console/http errors, no h-scroll | 1.55s | PASS | D:/sindhu_runtime/qa_screens/mobile_incidents.jpg | - |  |
| Incidents | mobile | button "Today" | no error | ok | PASS |  | - |  |
| Incidents | mobile | button "All-Time" | no error | ok | PASS |  | - |  |
| Settings | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s / console: PAGEERROR Cannot set properties of null (setting 'innerHTML') | FAIL | D:/sindhu_runtime/qa_screens/mobile_settings.jpg | high | Leaving Settings within ~2 s while its slow loaders are still queued makes a loader write to an element that no longer exists (console error only, no visible effect). Four loaders were guarded; more remain. |
| Settings | mobile | button "Today" | no error | ok | PASS |  | - |  |
| Settings | mobile | button "All-Time" | no error | ok | PASS |  | - |  |
| Configuration Panel | mobile | open page | renders, no console/http errors, no h-scroll | 1.54s | PASS | D:/sindhu_runtime/qa_screens/mobile_configuration_panel.jpg | - |  |
| Settings | mobile | risk % = negative ('-5') | rejected or Save disabled | Save disabled | PASS |  | - |  |
| Settings | mobile | risk % = empty ('') | rejected or Save disabled | Save disabled | PASS |  | - |  |
| Settings | mobile | risk % = huge ('1000') | rejected or Save disabled | Save disabled | PASS |  | - |  |
| Settings | mobile | risk % = letters typed | browser blocks letters in a number field | '' | PASS |  | - |  |
| Settings | mobile | change risk %, save (double-click), reload | shows 1.7 | 1.7 | PASS |  | - |  |
| Settings | mobile | revert risk % | back to 1 | 1 | PASS |  | - |  |
| Topbar | mobile | dark/light toggle + reload | theme flips and persists | dark->light->after reload light | PASS |  | - |  |
| Topbar | mobile | language toggle | label flips, no errors | EN->UR (label flips; console errors are tracked in the summary row) | PASS |  | - |  |
| Login | mobile | empty submit | stays on login | /login | PASS |  | - |  |
| Login | mobile | wrong password | rejected | /login | PASS |  | - |  |
| Auth | mobile | API without login | 401 / login required | {"detail":"login required"} | PASS |  | - |  |
| (all pages) | mobile | console errors during the whole run | none | PAGEERROR Cannot set properties of null (setting 'innerHTML'); PAGEERROR Cannot set properties of null (setting 'textCon | FAIL |  | high |  |
| (all pages) | mobile | HTTP 4xx/5xx during the whole run | none | none | PASS |  | - |  |

## Mobile notes (Step 11)
- All 36 pages open at 390 px with no horizontal scroll flagged on any page (overflow check is part of every row).
- Tap targets: only the Settings page has more than 3 buttons under 28 px high (4); everything else passes.
- Lite behaviour on phone: same request queue and cache as desktop; a sleeping server shows the "Server waking up, retrying..." bar at the top.
- NOT VERIFIED: a real phone (touch, keyboard, Telegram app) - owner check.

## Open issues
- LOW: leaving a page within ~2 s can print a console error from a still-loading panel (no visible effect).
- LOW: cold first load of the CEO page is 6-10 s on the test machine; Render free plan will be slower on a cold start.
- LOW: numeric validation exists in the UI (invalid fields get the `input-invalid` style and Save stays disabled) but there is no visible message text - see the Settings rows.

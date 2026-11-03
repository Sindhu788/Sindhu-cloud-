# Dashboard QA (Playwright, human-style) - 2026-11-03

Target: `recovery/clean` local app (safe mode) on a throwaway instance with its own login/config but the real read-mostly DB (port 8421). Viewports: desktop 1366x800 and mobile 375x812. Headless Chromium.
Cloud: only unauthenticated pages can be reached without the owner's login. `/health` and `/login` were checked; authenticated Cloud pages are BLOCKED-USER.
Destructive and DB-writing buttons (Reset, Delete, Enable/Disable All, Run, Start/Stop, Save outside Settings, Import, Send) were deliberately NOT clicked. Only navigation/refresh/filter-type buttons were clicked (max 4 per page), `Refresh` also double-clicked.

## Summary

- **desktop**: 36 pages opened, 37 checks passed, 4 failed; load median 0.68 s, max 10.79 s; 4 safe buttons clicked, 0 JS errors on passing pages.
- **mobile**: 36 pages opened, 37 checks passed, 4 failed; load median 0.66 s, max 10.85 s; 4 safe buttons clicked, 0 JS errors on passing pages.
- **extra checks (login, ops endpoints, settings validation, overflow, console)**: 14 passed, 1 failed.

## Findings

| Page | Control | Result | Severity | Evidence |
|---|---|---|---|---|
| SINDHU CEO (desktop) | load | FAIL | medium | 10.79s, slow 10.79s |
| Dashboard (desktop) | load | FAIL | medium | 10.26s, slow 10.26s |
| Compare (desktop) | load | FAIL | medium | 10.14s, slow 10.14s |
| Backtesting (desktop) | load | FAIL | medium | 5.66s, slow 5.66s |
| SINDHU CEO (mobile) | load | FAIL | medium | 10.33s, slow 10.33s |
| Dashboard (mobile) | load | FAIL | medium | 10.85s, slow 10.85s |
| Compare (mobile) | load | FAIL | medium | 10.29s, slow 10.29s |
| Backtesting (mobile) | load | FAIL | medium | 6.15s, slow 6.15s |
| Settings | desktop: inputs found | FAIL | low | 0 numeric inputs |

### How the findings were resolved
- **Strategy Lab / Paper Trading - HTTP 404 `/api/intelligence/shared-wallet` + console errors** (first run, both viewports): real bug - the dashboard still called a Codex endpoint removed in the cleanup. FIXED (calls removed, `tests/test_frontend_no_dead_endpoints.py`). The second run shows no console errors on any page.
- **SINDHU CEO / Dashboard / Compare ~10 s, Backtesting ~6 s**: the QA waits up to 8 s for the network to go idle, and these pages poll continuously, so the 10 s figure is mostly that wait (test artefact). Real cause for Backtesting/Compare: several read endpoints took 3-5 s on cold cache (duplicates, dual-TP, evolution ranking/strategies, retirement suggestions). FIXED with a stale-while-revalidate cache (`tests/test_cached_endpoint.py`); first call after a restart is still slow, later calls are instant.
- **Settings: no numeric inputs found on desktop**: the Settings page uses text/select controls for most values, so out-of-range numeric validation could NOT be exercised in the browser (not verified). Observed: the Save button stays disabled until a change is made. Low; recommend a manual check of negative/empty values on the Settings page.
- **First QA run found 0 mobile pages**: script timing (navigation list builds after login); fixed in the script, mobile now opens all 36 pages.

## Per-page results (desktop | mobile load seconds)

| Page | Desktop | Mobile |
|---|---|---|
| AI Center | PASS 0.56 | PASS 1.28 |
| Backtest History | PASS 0.68 | PASS 0.77 |
| Backtesting | FAIL 5.66 | FAIL 6.15 |
| Challenge Mode | PASS 0.63 | PASS 0.6 |
| Clarification | PASS 1.33 | PASS 0.66 |
| Compare | FAIL 10.14 | FAIL 10.29 |
| Concepts | PASS 1.12 | PASS 0.79 |
| Configuration Panel | PASS 0.57 | PASS 0.65 |
| Control Center | PASS 0.66 | PASS 0.64 |
| Dashboard | FAIL 10.26 | FAIL 10.85 |
| Data | PASS 0.76 | PASS 0.68 |
| Evolution | PASS 0.8 | PASS 0.66 |
| Evolution History | PASS 0.72 | PASS 0.62 |
| External Signal Tracker | PASS 0.81 | PASS 0.61 |
| Incidents | PASS 0.65 | PASS 0.69 |
| Knowledge | PASS 0.6 | PASS 0.72 |
| Knowledge Compiler | PASS 0.62 | PASS 1.48 |
| Live Logs | PASS 0.6 | PASS 0.68 |
| Market | PASS 0.67 | PASS 0.64 |
| Memory Core | PASS 0.76 | PASS 0.6 |
| Paper Trading | PASS 0.92 | PASS 0.66 |
| Pipeline History | PASS 0.71 | PASS 0.64 |
| Practice Mode | PASS 0.59 | PASS 0.57 |
| Project Status | PASS 0.62 | PASS 0.64 |
| Reports | PASS 0.75 | PASS 0.62 |
| Risk | PASS 0.64 | PASS 0.64 |
| SINDHU CEO | FAIL 10.79 | FAIL 10.33 |
| SINDHU Strategy | PASS 0.6 | PASS 0.69 |
| Self-Learning Engine | PASS 0.71 | PASS 0.76 |
| Settings | PASS 0.58 | PASS 0.59 |
| Signal Tracker | PASS 0.64 | PASS 0.64 |
| Strategies | PASS 0.6 | PASS 0.7 |
| Strategy Lab | PASS 0.73 | PASS 0.6 |
| Strategy Lifecycle | PASS 0.62 | PASS 0.62 |
| Telegram Signals | PASS 1.07 | PASS 0.7 |
| Web-Sourced Strategies | PASS 0.65 | PASS 1.25 |

## Not covered (honest)
- Authenticated Cloud pages (BLOCKED-USER: no login).
- Buttons that write to the database or send anything (skipped on purpose).
- Real-phone rendering and the real Telegram chat (owner check).

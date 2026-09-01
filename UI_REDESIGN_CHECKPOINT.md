# Dashboard Navigation Audit + Compare Redesign — Checkpoint (COMPLETE)

## Phase 0 — Status Check
A full institutional-grade redesign was ALREADY completed in this codebase before this
session, across multiple prior passes (confirmed via `git log` + `PROGRESS.md`, not assumed):
- `6638322`/`cf60e6d` — "Dashboard Professional Redesign": dark theme, collapsible sidebar,
  top bar (search/notifications/quick actions), refined color tokens (green=profitable,
  red=losing, yellow=pending, used via `.pill-up`/`.pill-down`/`.pill-pending`/`.pill-muted`
  consistently across the whole CSS file, confirmed by direct grep).
- `04b92c9` — "Navigation Audit + Reorganization": grouped sidebar (7 groups), removed 3 dead
  placeholder nav entries (Reflection/News/disabled Telegram), extracted Control Center to its
  own real page.
- `87d300d` — "Scoped dashboard clutter reduction": strategy cards over dense tables, honestly
  scoped (explicitly did NOT attempt a full 5-page overhaul in one pass).
- A prior session's own `project_status.py` audit item already investigated and correctly
  flagged `sindhu_web/static/activity_log.html` as legacy debris (superseded by the Live Logs
  SPA page) -- deliberately not linked into nav, not deleted (matches this task's own "flag,
  don't delete" constraint).

**Conclusion: this was a REFINEMENT pass, not a from-scratch build.** Phases 1-3 below proceeded
on that basis -- verifying current state first, then making concrete, scoped improvements.

## Phase 1 — Navigation Audit (DONE)
Checked all 29 nav-reachable destinations (28 SPA hash routes from the live `/api/nav` payload
+ 1 external static page) by driving the real browser to every one and reading rendered content:

| Finding | Result |
|---|---|
| All 28 SPA pages | Working -- real content rendered, zero console errors |
| Concepts (external_url) | Working (verified separately, own page) |
| Duplicate nav entries | None found |
| Orphaned built-but-unlinked pages | None found. `strategy_wizard` exists in `PAGES{}` but not in top-level nav -- checked and confirmed intentional: reachable via the Strategies page's "New Strategy" choice modal (`choiceWizardBtn`), a sub-flow entry point, not a missing link. |
| Dead/legacy pages | `static/activity_log.html` -- already known, already flagged in a prior audit (see Phase 0), correctly left unlinked, not deleted per the "flag, don't remove" constraint. |

No broken links, no 404s, no blank pages found. Navigation is healthy.

## Phase 2 — Compare Page Redesign (DONE)
File: `sindhu_web/static/js/app.js` (`renderCompare`, `compareRowsHtml`, `wireCompareRowClicks`),
`cardClass()` extended with an optional 4th `caption` param (additive, every other caller
unaffected).

Concrete changes:
- **4 glanceable summary cards** at the top: Total Strategies, Genuinely Profitable, Losing
  (new), Best Performer with PF + strategy name (new) -- was 2 cards before.
- **Main table wrapped in its own `.section-card`** titled "Main Strategies" with a plain-
  language subtitle, instead of a bare table with no visual boundary.
- **All / Profitable / Losing filter tabs** (reuses the existing `.period-tab` component
  already used on Project Status -- no new CSS component invented) so the 31-row table defaults
  to something scannable instead of one 31-row wall; each tab shows its own count.
  Confirmed working: clicking "Losing (23)" correctly filters to only losing rows.
- **Compare row -> Strategy Profile click-through** (the missing "vice versa" half of the
  navigation gap -- Profile -> Compare already existed via the "View on Compare page" button
  and `compareHighlightStrategy` flash-scroll). Reuses the exact same `pendingProfileStrategyId`
  hand-off the Strategies page's own deep-links already use. Confirmed working round-trip in the
  live browser: Compare row click -> Strategy Profile page -> "View on Compare page" button ->
  back to Compare, scrolled + flashed on the right row.
- **Dual-TP archived-variant section visually separated further**: added an explicit
  `pill-muted` badge reading "Draft variants -- not in totals above" next to that section's own
  title, on top of the `.section-card` boundary it already had -- so it reads as clearly
  separate from Main Strategies, not just implicitly so.
- PF/Verdict were already the most visually prominent elements (`.stat-hero` + color-coded
  `.pill-up`/`.pill-down`) before this pass -- confirmed, left unchanged, no jargon found in
  Compare's own labels beyond "PF" itself, which already has its own plain-language explainer
  box at the top of the page.

Verified live in-browser: screenshots + console-error checks at both desktop and 1024px width
(no overlap, table has its own horizontal scroll like it already did).

## Phase 3 — Full Dashboard Design Pass (SCOPED, per Phase 0 findings)
Since Phase 0 confirmed the design system (color tokens, card/pill/table components, spacing)
is already coherent and already applied consistently dashboard-wide -- not a raw/inconsistent
starting point -- this phase was a **verification + targeted-fix pass**, not a rebuild:
- Confirmed profitable/losing/pending color usage is identical across Compare, Strategy
  Lifecycle, and Home (green/red/yellow pill tokens, one shared CSS source).
- Confirmed Home page is already genuinely glanceable: Balance/PnL/Win Rate/Total Trades/
  Knowledge Score/Evolution Score/DB Status/System Health all visible without scrolling, plus
  System Maturity Level and System Alerts directly below.
- No further CSS/layout changes made beyond Compare's own additions above -- making broad
  changes across pages that were already confirmed consistent would have been pure risk with no
  real gain, and would go against this project's own established precedent (see `87d300d`'s
  explicit "do not leave the dashboard in a half-redesigned broken state" scoping note).

**No page needed a data/logic change to look right** -- nothing flagged for follow-up.

## Verification
- pytest: 896 passed (zero regressions) after Phase 2's changes.
- Live browser verification: all 28 SPA pages load with real content and no console errors;
  Compare's filter tabs, row-click-through, and round-trip Profile link all confirmed working;
  1024px-width responsive check showed no overlap/breakage.

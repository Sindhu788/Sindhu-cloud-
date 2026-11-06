# SINDHU DESIGN SYSTEM v2 (master plan V2 DS1, W1)

**Concept: "Trading desk, not a template."** Calm, dense, precise. Confidence comes from type, alignment and restraint, not effects.
Source of truth: `sindhu_web/static/css/tokens.css` (tokens) and `sindhu_web/static/css/ds.css` (components, DS2).

## Accent choice: teal (and why not amber)
Amber is already the **warning** colour (plan rule: amber = warning only). An amber accent would make every primary button look like a
warning. Teal is calm, reads well on graphite and on paper, and is far enough from profit-green in hue and lightness that a teal
button is not read as "profit". Teal is used for: primary buttons, links, focus rings, the active menu item, the selected tab, and the
single rim light in the login scene. Nothing else.

## Colour tokens
| Token | Dark | Light | Use | Don't |
|---|---|---|---|---|
| `--bg` | #0e1114 ink | #f8f6f1 paper | page background | cards |
| `--surface` / `--surface-2` / `--surface-3` | #12161a / #151a1f / #1a2026 | #fff / #fcfbf8 / #f4f2ed | shell, cards, table headers (raised) | text |
| `--line` / `--line-soft` | #2a323a / #20262d | #e2ded5 / #ebe8e1 | borders, table rows | decoration lines |
| `--text` / `--text-2` / `--text-3` | 13.8:1 / 7.4:1 / 6.0:1 | 14.8:1 / 6.8:1 / 5.1:1 | primary, secondary, hints (all WCAG AA) | grey text below `--text-3` |
| `--accent` (+`-strong`, `-soft`, `--on-accent`) | #2fb3ad | #0d7c78 | primary action, focus, active nav | data meaning |
| `--profit` | #4cb782 | #1d7a4b | **profit only** | success toasts, decoration |
| `--loss` (+`--on-loss`) | #e5605a | #b8322c | **loss and danger only** | "important" highlighting |
| `--warn` | #d9a441 | #8f610a | **warnings only** (stale data, paused) | accent, links |
| `--g-50` ... `--g-900` | 9-step neutral grey | inverted | neutral fills | - |

Contrast numbers are the minimum over `--bg`, `--surface-2`, `--surface-3`, computed with the WCAG formula (DS1 commit).
Old names (`--bg-card`, `--accent-2`, `--green`, `--yellow` ...) are aliases of the v2 tokens so legacy pages follow the theme.

## Type
- UI: **Inter** (self-hosted variable woff2, latin subset, `font-display: swap`). Numbers, prices, IDs, times: **JetBrains Mono** with
  tabular digits (`.num`, `.mono`, `td.num`). Only these two families.
- Scale: 12 / 13 / 14 (body) / 16 / 20 / 24 / 32 px (`--fs-*`). Headings 600 weight; no all-caps except tiny labels (12 px, +4 % tracking).
- Numbers right-aligned, always with a unit: `$`, `%`, `UTC`, `s`, `MB`.

## Space, grid, radius, shadow
- 4/8 px spacing (`--space-1` 4 ... `--space-7` 48). Desktop 12-column grid (`.ds-grid`), phone single column.
- Radius: 6 px controls (`--radius-sm`), 10 px cards (`--radius-md`), pill only for badges.
- Two shadows only: `--shadow-1` (raised controls), `--shadow-2` (modals, menus). Cards use a border, not a shadow.

## Icons
One set: **Lucide** (ISC), as one SVG sprite `static/vendor/lucide-sprite.svg` (52 icons). Use
`<svg class="icon"><use href="/static/vendor/lucide-sprite.svg#i-house"/></svg>`. No emoji in the UI.

## Motion
150 / 200 / 250 ms (`--dur-1..3`), ease-out (`--ease`). Only for state changes and reveals (menu open, toast in, row expand).
`prefers-reduced-motion: reduce` sets every duration to ~0 and stops animations (skeleton shimmer, login scene).

## Do / don't
| Do | Don't |
|---|---|
| Left-aligned content, the most important number first and largest | Center everything |
| One primary button per view | Two teal buttons side by side |
| Green/red only for money moving up/down | Green "OK" pills, red "important" headings |
| Short, specific copy ("Data purana: BTC 15m, 22 min") | "Unlock the power of..." / "Welcome back, trader!" |
| Borders and spacing for structure | Glassmorphism, neon glow, purple-blue gradients, rainbow charts |

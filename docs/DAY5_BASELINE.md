# Day 5 baseline (4 Nov 2026, 18:47 UTC) and inventory

| Item | Value | Source |
|---|---|---|
| Cloud `/health` | commit `f65735e`, engine_running true, postgres; the first answer took 45 s (instance had been asleep) | curl |
| External pinger | none seen (no `GET /health` from a pinger in the log); `/api/ops/pinger` needs a login | Render log |
| Local app | **DOWN** at 127.0.0.1:8420; no python process was running. LAN address of this laptop is now **192.168.1.113** (it was 192.168.1.111 on earlier days); no Windows Firewall rule for TCP 8420 exists | curl, ipconfig, netsh |
| Git | local `recovery/clean` HEAD `504991e`; deployed `f65735e`; origin `f65735e`; `504991e` is inside the deployed merge (`git merge-base --is-ancestor` true); so no Day 4 commit or document was missing from GitHub | git |
| Disk | C: 137 GB total, 63 GB free; **D: 100 GB total, 53 GB free** | df |
| Binance public API from this PC | `api.binance.com/api/v3/ping` 200 (0.85 s); `klines` 200; `data-api.binance.vision` 200; **`data.binance.vision` bulk archive: 200 (monthly and daily zip files and `.CHECKSUM` exist)** | curl, HTTP status only |
| OKX from this PC | `/api/v5/public/time` 200 but `/api/v5/market/history-candles` fails at connection level (curl code 000 in 0.2 s) -> OKX candle history is **not reachable** from this PC | curl |
| Bybit from this PC | `/v5/market/time` 200 | curl |
| Render services | 9 in the workspace (see docs/OWNER_TODO.md Day 4); live one: Sindhu-cloud--1 | Render API |

**Decision for Part C:** the data source is Binance (reachable, public bulk archive with published checksums, 1 request per coin-month). Cloud trades on OKX, so backtest and live differ slightly; the comparison is in docs/DATA_QUALITY.md.

## Inventory of unpushed / local-only work (Step 3)
| What | Hash | State |
|---|---|---|
| Day 4 docs (SCAN_PROFILE, SIGNAL_QUALITY, STRATEGY_FORENSICS, SECURITY_REVIEW, DAY4_BASELINE, OWNER_TODO additions, checkpoint) | `d20a497`, `02276f4`, `504991e` | already on GitHub inside deployed `f65735e` |
| Day 4 code (pool, memo, memory guard, health fix, retry logging, login throttle) | `a70f619`, `2302f9e` and merge | deployed |
| Day 5 local launcher scripts and runbook 11c | `597e4f4` | pushed with Day 5 push 1 (`5ad081b`) |
| Exchange circuit breaker, per-thread ccxt, flagged gate fix | Day 5 commit before `5ad081b` | pushed and deployed (`5ad081b`) |
| Data platform code (`data_platform/`), downloader tests | uncommitted at this point | local only, under test |

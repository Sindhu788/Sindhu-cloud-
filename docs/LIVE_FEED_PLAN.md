# Live candle feed plan (DESIGN ONLY - nothing in this document is implemented)

Goal: replace "poll REST for every coin every tick" with a shared, streamed candle cache, so every strategy is evaluated exactly once per candle close on fresh, gap-free data, and so a stale feed is detected within seconds.

## 1. How data is fetched today (code references)
| Step | File | What it does |
|---|---|---|
| Tick loop | `paper_trading/engine.py` (`_loop`, `_tick_impl`, `tick_interval_seconds`=30 in `paper_trading/config.py`) | every 30 s: list tradeable symbols, rank, evaluate strategies per coin |
| Coin ranking | `paper_trading/coin_filter.py` (`shortlist`, modes `activity` / `liquidity`) | pulls 72 h of 1h candles per symbol via `get_ohlcv` to score the market |
| Candle access | `data_engine/resample.py::get_ohlcv` -> `data_engine/live_candles.py::get_ohlcv_live` when `SINDHU_LIVE_CANDLES=1` (Cloud) | per `(exchange, symbol, interval)` in-memory pandas cache; first call = paginated REST fetch (`_fetch_range`, `_PAGE_LIMIT` 1000, `_MAX_RETENTION_DAYS` 25), later calls fetch only candles newer than the last cached one |
| Exchange client | `data_engine/exchanges/ccxt_client.py::get_ohlcv` (ccxt `fetch_ohlcv`, `enableRateLimit`) | one REST request per page |
| Exchange choice / failover | `data_engine/exchanges/registry.py` (`get_working_exchange_client`, `exchange-failover` log) | tries binance -> okx -> bybit -> bitget -> gate; Cloud ends up on OKX because Binance/Bybit are blocked from Render |
| Freshness guard | `paper_trading/market_data_guard.py::closed_recent_frame` | drops the open candle; rejects frames whose last closed candle is older than one period, with gaps, duplicates or bad OHLC; logs a WARNING and counts it |
| Multi-timeframe frames | `backtest_engine/mtf_context.py` | builds each strategy's roles (entry/bias/htf) from the cached frames |

Known weaknesses of REST polling: (a) a candle can be up to one tick late; (b) exchange page caps differ (OKX ~300 rows) - the 3 Nov outage was exactly this; (c) ~10 coins x 4-5 timeframes x refresh per 30 s is hundreds of requests per minute and the first scan after a restart downloads ~28,800 1m rows per coin (minutes on a 0.1 CPU host); (d) rate limits are per IP, shared by everything on the host.

## 2. Target design
1. **Candle cache service (in-process first):** one asyncio task that keeps a WebSocket open to the primary exchange's PUBLIC candle stream for the shortlisted coins (1m is enough: 5m/15m/1h are resampled from closed 1m bars with the existing resampling code). It writes closed bars into the same pandas structure `live_candles._cache` already uses, so `get_ohlcv_live` and everything above it stay unchanged.
2. **Evaluate on close:** the stream marks a bar closed (exchange `confirm` flag); the engine is notified and evaluates only the strategies whose timeframe just closed (5m strategies every 5 min, 1h every hour) instead of re-scanning all coins every 30 s. The existing gates (confluence, Wilson, freshness 15 min, drift 0.5 %) run unchanged on the new trigger.
3. **Reconnect and gap-fill:** on disconnect or a missing sequence (`open_time` jump) fetch the missing range through the existing REST `_fetch_range` (now correctly paged) and merge by `open_time`; mark the cache "degraded" until contiguous. The guard in `market_data_guard.py` stays as the final safety net.
4. **Staleness alert:** a per-feed heartbeat (last message time). If no message for 2x the expected interval, raise the existing owner-chat alert (`paper_trading/monitoring.py`, code `stale_data`) and block new signals (guard already does).
5. **Exchange selection:** keep the failover list; add the WebSocket endpoint per exchange (OKX public business channel `candle1m`, Binance `<symbol>@kline_1m`, Bybit `kline.1.<symbol>`). Endpoint names and limits must be re-checked against each exchange's current documentation when implementing (NOT VERIFIED here).

## 3. Hosting and region
- Binance and Bybit are unreachable from Render's Oregon region (observed 3 Nov). A feed from a region those exchanges serve (e.g. Singapore) would allow the primary exchange to be Binance. A Render service's region is fixed at creation, so this needs a **new** web service in Singapore (new URL, new env vars, repoint pingers and Telegram webhook if used).
- A WebSocket needs a process that stays up: free plan sleeps -> unsuitable. Options: (a) Render Starter (always on, ~US$7/month, Singapore), (b) small VPS (Hetzner/Vultr/DigitalOcean Singapore, ~US$5/month) running the same `uvicorn cloud_runtime.app:app`, (c) keep Render and put only the feed on a VPS that writes to Neon (more moving parts - not recommended).
- Recommendation: one always-on Singapore instance running the whole app; Neon stays the database (pick the Singapore Neon region for latency, migrating with `scripts/backup_cloud_export.py` + a restore).

## 4. Migration steps
1. Implement behind a flag `SINDHU_FEED=ws` (default `rest`); unit-test the gap-fill with a fake socket (same style as `tests/test_live_candles_pagination.py`).
2. Run local in shadow mode: compare WS-built candles with REST candles for 48 h (counts, OHLC equality, close-time lag).
3. Deploy to the new Singapore service with signals still going only through the existing owner guard; leave the old Oregon service running with `SINDHU_PUBLIC_SIGNAL_OWNER=disabled` (or `main`) so exactly one publisher exists.
4. Move the Telegram publisher role (`SINDHU_PUBLIC_SIGNAL_OWNER=cloud` only on the new service); update pingers; watch `/api/ops/warnings`.
## 5. Rollback
Set `SINDHU_FEED=rest` (instant, no deploy of code) or redeploy the previous commit; the REST path is untouched. Re-enable the old service's publisher role only after disabling the new one.

## 6. Risks
WebSocket drops silently (mitigate: heartbeat + REST gap-fill); exchange changes channel names or sends partial bars (mitigate: only trust `confirm=1` closed bars, keep `closed_recent_frame`); clock skew (use exchange timestamps); duplicate publishers during migration (strict one-owner rule); extra monthly cost; more code on a student project - keep the REST path as the fallback and do not remove it.

# FORWARD TEST LOG (master plan A25 / P22)

Forward-test data is **never deleted or reset**. Every change that could affect how results are read is listed here with its time, so the
numbers stay interpretable. Evaluation is not before **2027-01-05** and needs at least 100 positions per candidate
(docs/BACKTEST_PROTOCOL.md). Until then, counts only, no verdict.

| UTC | Event | Effect on reading the results |
|---|---|---|
| 2026-11-05 22:38 | Deploy D1 (6390321): Cloud never uses Bybit/Binance; confluence UNKNOWN when regime data is missing (withheld from public send); automatic public signals off by code default | public Telegram signals stop; paper trading unchanged |
| 2026-11-05 23:09 | Deploy D2 (02d12c3): MAIN_WALLET added (mirrors research positions that pass every gate, with wallet rules); invalid config refuses new entries | research books unchanged; a new $100 wallet record starts |
| 2026-11-05 23:20:33 | **MAIN_WALLET created on Cloud**: $100.00 start (wallet_state `MAIN_WALLET:created_at`) | wallet results count from here |
| 2026-11-06 00:00 | Forward-test window starts (pre-registered) | positions opened from here count |
| 2026-11-06 00:14 | First two wallet entries (BTC/USDT 4h $51.53, NEAR/USDT 5m $48.37), both from strategies labelled FAILED | shows the old sizing (about 50 % per trade) |
| (next deploy, D3) | Wallet: one position at most equity / 4 (25 %); no-free-cash reason | later entries are smaller; the two above keep their size |

Registered forward-test candidates: **0** (`D:\sindhu_data\manifest\forward_registry.json`). The two V2 benchmark strategies (both
FRAGILE) are NOT registered; that is an owner decision (docs/OWNER_DECISIONS.md).

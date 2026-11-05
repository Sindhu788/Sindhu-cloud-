# Strategy pipeline: what runs where, and how a strategy earns (and loses) a place on Cloud (Day 6 Step 18)

## 1. Where each step runs
| Step | Where | Notes |
|---|---|---|
| 1. Import a strategy (AI reads the source, writes rules) | **Local** | the only place AI is used; everything after is deterministic |
| 2. Backtest with candle files | **Local** (laptop) | uses the protected dataset `D:\sindhu_data` through `data_platform.loader` (closed candles only). Cloud never needs candle files and candles are never written to Postgres |
| 3. Protocol / validation (costs, walk-forward, null model, baselines, dossier) | **Local** | `python -m data_platform.protocol_run`, `protocol_analyze`, `protocol_rigor`; the candidate tool of Step 19 |
| 4. Shortlist / promotion decision | **Local + owner** | docs/OWNER_DECISIONS.md |
| 5. Sync of approved strategies to Cloud | Local -> Cloud | only after owner approval; nothing syncs by itself for a candidate |
| 6. Paper trading, Wilson 25-trade gate, Evolution 100-trade gate, confluence, risk manager, freshness, same-coin cap | **Cloud** (also Local if run) | the safety gates are never loosened by this pipeline |
| 7. Telegram signals (Profitable + Challenge groups only) | **Cloud** | Losing group sends nothing |

## 2. Promotion rule (all must be true; evidence goes into the dossier)
1. Label **ROBUST** under the CORRECTED metrics (position-level, docs/BACKTEST_PROTOCOL.md section 10): >= 300 positions, >= 6 of 8 walk-forward windows with >= 30 positions, PF >= 1.1 in >= 60 % of windows and coins, PF > 1 at cost x1.5.
2. **Beats the random-entry null model** (p < 0.05, FDR-controlled across the candidates tested together) and the SMA-4h and RSI-1h baselines by mean net return per position; the 95 % interval of the profit factor (cluster bootstrap) stays above 1.
3. **Timeframe can be served live:** the entry timeframe must be longer than the measured Cloud scan time allows (see docs/STRATEGY_FORENSICS.md timeframe table). Strategies on timeframes the live scan cannot serve stay **research-only** (flag below).
4. **Pre-registered forward test passed** (docs/BACKTEST_PROTOCOL.md section 9): >= 60 days and >= 100 positions after registration, one look.
5. **Owner approval** (written in docs/OWNER_DECISIONS.md). The AI never promotes by itself.

## 3. Demotion rule (any one is enough to recommend a pause; the owner decides)
- Live paper results: 100+ closed trades with profit factor < 1.0 after costs, or the existing Evolution/downgrade thresholds trigger.
- A re-run of the protocol on new data labels it FAILED or FRAGILE, or its PF interval falls below 1.
- A data or code change makes the earlier evidence invalid (new `data_version`/code commit not re-tested).

## 4. Rollback
- A strategy: disable it in the dashboard (data stays), or re-sync the previous strategy set.
- Code/config: git tag `pre-recovery-backup`; Render deploys only fast-forward pushes of the deploy branch, so a revert commit restores the previous behaviour.
- Data: the dataset folder is never deleted or overwritten; manifests keep a `.bak`.

## 5. Research-only flag (prepared, OFF)
`SINDHU_RESEARCH_ONLY_TIMEFRAMES` (comma list, for example `1m,3m`) on the **live service**: strategies whose ENTRY timeframe is in the list are not evaluated by the live scan (no candles loaded, no candidates). They stay enabled and fully backtestable locally. With the variable unset (the default) nothing changes. Code: `paper_trading/research_only.py`, hook at the top of the strategy loop in `paper_trading/signal_generator.py`; tests: `tests/test_research_only.py` (3).

## 6. Evaluating a NEW candidate strategy (Step 19)
1. Owner fills `docs/templates/CANDIDATE_CLAIM_TEMPLATE.md` (what is the claimed edge, and WHY should it exist).
2. Import the strategy with the normal import mechanism, but with `SINDHU_DATA_DIR` and `SINDHU_STRATEGY_LIBRARY_DIR` pointing at scratch folders (a LOCAL sandbox database that is never synced).
3. Run: `python -m data_platform.candidate_eval --library-dir <scratch library> --strategy-id <id> --claim <claim file> [--coins 50] [--workers 2]` (venv with pandas + pyarrow, e.g. `D:\sindhu_venv_bt`).
4. Result: `D:\sindhu_data\candidates\<id>_<time>\DOSSIER.md` (claim, one-page verdict, rules and timeframe, costs, walk-forward results, comparison with the random-entry null model and the baselines, fee sensitivity x1 / x1.5 / x2, label).
**Isolation (tested, `tests/test_candidate_sandbox.py`, 7 tests):** the tool removes every credential-like environment variable (token, secret, password, API key, database URL, chat id) before importing anything, and blocks every outgoing non-local connection, including in the worker processes; so it cannot reach Cloud, Neon or Telegram. It reads the strategy from a COPY and writes only into its own folder. The sealed holdout and the forward window are never read.
**Proof run (5 Nov 2026):** existing strategy Ichimoku 1d Trailing-SL (`8d94d5ee403f`), 10 coins, 1 worker: finished in under a minute, 21 positions, PF 1.93, label INSUFFICIENT_DATA (same numbers as the 42-strategy run).

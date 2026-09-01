# Database Cleanup Record

Generated: 2026-08-29T22:21:04.021879+00:00

CEO-approved cleanup of stale/unreachable rows. Recorded here BEFORE the
delete so there is a permanent trace of exactly what was removed.

## 1. Backtest batches stuck in status='running'

Found **6**. These are runs that never finished (the process died
mid-run), so they sit as 'running' forever and can never complete.

| batch_id | strategy | started |
|---|---|---|
| `20260823_112357_48deb2` | Deliberately Contradictory RSI Strategy | 2026-08-23T06:23:57 |
|  | *(holds 0 per-coin results, 0 trade rows -- KEPT, only the status changes)* | |
| `20260823_152326_9c8498` | Lower Time Frame Liquidity Reversal Strategy | 2026-08-23T10:23:26 |
|  | *(holds 3 per-coin results, 1353 trade rows -- KEPT, only the status changes)* | |
| `20260823_180309_2f39a4` | Lower Time Frame Liquidity Reversal Strategy | 2026-08-23T13:03:09 |
|  | *(holds 41 per-coin results, 16514 trade rows -- KEPT, only the status changes)* | |
| `20260824_105841_c70f3f` | Lower Time Frame Liquidity Reversal Strategy | 2026-08-24T05:58:41 |
|  | *(holds 0 per-coin results, 0 trade rows -- KEPT, only the status changes)* | |
| `20260824_195434_cf2313` | 4-Hour Range Breakout-Retest [Manual Build] | 2026-08-24T14:54:34 |
|  | *(holds 27 per-coin results, 11032 trade rows -- KEPT, only the status changes)* | |
| `20260830_030009_504b78` | SINDHU Deterministic Candidate #4 | 2026-08-29T22:00:09 |
|  | *(holds 1 per-coin results, 0 trade rows -- KEPT, only the status changes)* | |

**Action: status 'running' -> 'stopped'. No rows deleted.** Any partial
results they did produce stay queryable.

## 2. Orphaned rows whose parent batch no longer exists

- `backtest_results` with no parent batch: **452**
- `backtest_trades` with no parent batch: **51224**
- `confluence_score_log` with no parent position: **56**

They belong to **82** batch ids that no longer exist in
`backtest_batches`. Sample of those dead ids:

- `20260819_095248_a17b3b` (890 trade rows)
- `20260819_160851_bcacdd` (890 trade rows)
- `20260819_161529_428034` (890 trade rows)
- `20260819_190734_de5cef` (890 trade rows)
- `20260820_064323_d1c5d0` (890 trade rows)
- `20260820_160549_f189c6` (0 trade rows)
- `20260820_161436_240d8f` (890 trade rows)
- `20260823_081039_582e4d` (890 trade rows)
- `20260823_082527_2d76c8` (0 trade rows)
- `20260823_083523_12a935` (890 trade rows)

**Why these are unreachable, not merely unused:** every read path in this
codebase reaches results through an explicit batch id -- 
`latest_completed_batch_for_strategy_name()` -> `get_batch_results(batch_id)`.
With no surviving `backtest_batches` row there is no id to look them up by,
so nothing in the app can ever display or aggregate them. Verified in the
Part 2 audit: they cannot leak into any leaderboard or total.

## 3. Explicitly NOT touched

- All **193** batch rows are kept (5 only change status).
- `backtest_results` total 6757 -> 6305 kept.
- `backtest_trades` total 2025514 -> 1974290 kept.
- Every strategy config, lesson, paper position, knowledge row: untouched.
- My Part 3 verification batch stays as 'stopped' with its 457 trades intact.


---

## 4. RESULT OF THE CLEANUP (applied 2026-08-29)

| | before | after |
|---|---|---|
| `backtest_batches` rows | 193 | **193** (none removed) |
| batches stuck at `running` | 6 | **0** |
| `backtest_results` | 6,757 | **6,305** |
| `backtest_trades` | 2,025,514 | **1,974,290** |
| `confluence_score_log` | 82 | **26** |
| orphaned results / trades / confluence | 452 / 51,224 / 56 | **0 / 0 / 0** |

Deleted: 452 orphaned results, 51,224 orphaned trades, 56 orphaned confluence
rows. Every batch row preserved; every reachable result and trade preserved.

## 5. MISTAKE MADE DURING THIS CLEANUP -- recorded honestly

The stuck-batch step used a blanket `WHERE status=''running''` instead of the five
specific stale ids. At that moment the Evolution Engine was **actively running**
a sixth batch, `20260830_030009_504b78` (*SINDHU Deterministic Candidate #4*),
so that live run was also marked `stopped` mid-flight.

Impact, checked rather than assumed:
- its data is intact (1 per-coin result saved, 0 trades -- that candidate
  produced no trades);
- the candidate WAS still recorded as tested -- untested count moved 130 -> 129;
- `evolution_jobs` row `evo_1788039735952` stayed `status=''running''`, so the
  engine resumed normally on the next server start.

Left as `stopped` rather than reverted: it genuinely was stopped, and nothing is
running it now, so `stopped` is the accurate state. Recorded here so it is not
mistaken later for an organic failure.

**Lesson for future cleanups in this repo: never filter live state by status
alone -- always target the specific stale ids.**

## 6. STILL OPEN -- orphan rows are being created again

This cleanup is not permanent. New orphans appeared during the session itself
(e.g. `20260830_024927_431b99`, a single BTCUSDT 5m result with 928 trades,
whose `backtest_batches` parent never existed). The pattern goes back to at
least 2026-08-19.

Bounded investigation done, cause NOT found:
- `runner.py` always calls `storage.create_batch()` before any
  `storage.save_result()`, on both the `run_batch` and `run_mtf_batch` paths;
- every `save_result` caller in the codebase lives in `runner.py`;
- there is **no `DELETE FROM backtest_batches` anywhere** in the project, and no
  retention/pruning job for that table.

Best available hypothesis (a hypothesis, not a finding): a batch row whose
creating transaction never committed -- `storage.get_conn()` opens a fresh
connection per call, so an interrupted or rolled-back `create_batch` would leave
later per-symbol writes, made on their own connections, committed and parentless.
Needs a dedicated follow-up with write-level tracing.

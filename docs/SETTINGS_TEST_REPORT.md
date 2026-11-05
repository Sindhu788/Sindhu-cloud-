# SETTINGS TEST REPORT (master plan A21 / P9)

50 cycles, seed 20261105, SQLite in a throwaway data folder, through the real HTTP API (`python tools/settings_cycles.py --cycles 50 --seed 20261105 --write`). Every 10th cycle a fresh Python process (a real restart) re-reads all saved settings. **Postgres: BLOCKED** (no local Postgres/Docker and no throwaway Neon branch; the real Cloud database is never used for tests).

**Result: 50 of 50 cycles passed.**

| Setting | Cycles | Pass | Fail | Notes (first 3) |
|---|---|---|---|---|
| coin_filter_top_n | 1 | 1 | 0 | #46 below: HTTP 422, old value kept |
| cooldown_minutes | 6 | 6 | 0 | #7 HTTP 200; #17 wrong_type: HTTP 422, old value kept; #29 wrong_type: HTTP 422, old value kept |
| cooling_off_hours | 1 | 1 | 0 | #26 HTTP 200 |
| cooling_off_loss_streak | 1 | 1 | 0 | #10 HTTP 200; restart read-back ok |
| daily_goal_pct | 5 | 5 | 0 | #1 wrong_type: HTTP 422, old value kept; #20 HTTP 200; restart read-back ok; #27 HTTP 200 |
| ensemble_voting_min_agreeing_strategies | 2 | 2 | 0 | #5 HTTP 200; #36 empty: HTTP 422, old value kept |
| lesson_default_rr | 2 | 2 | 0 | #16 HTTP 200; #50 below: HTTP 422, old value kept; restart read-back ok |
| lesson_default_sl_pct | 1 | 1 | 0 | #6 below: HTTP 422, old value kept |
| lookback_days | 3 | 3 | 0 | #19 wrong_type: HTTP 422, old value kept; #37 HTTP 200; #48 wrong_type: HTTP 422, old value kept |
| max_open_positions_per_coin | 3 | 3 | 0 | #22 empty: HTTP 422, old value kept; #28 HTTP 200; #40 wrong_type: HTTP 422, old value kept; restart read-back ok |
| max_open_trades | 1 | 1 | 0 | #32 HTTP 200 |
| max_portfolio_risk_pct_per_coin | 1 | 1 | 0 | #23 HTTP 200 |
| opposite_signal_policy | 1 | 1 | 0 | #45 HTTP 200 |
| priority_rule | 1 | 1 | 0 | #43 HTTP 200 |
| profit_lock_trail_pct | 4 | 4 | 0 | #3 empty: HTTP 422, old value kept; #11 HTTP 200; #38 HTTP 200 |
| profit_lock_trigger_r | 2 | 2 | 0 | #4 empty: HTTP 422, old value kept; #14 HTTP 200 |
| risk_pct_default | 4 | 4 | 0 | #8 HTTP 200, size effect ok; #9 HTTP 200, size effect ok; #13 above: HTTP 422, old value kept |
| tick_interval_seconds | 3 | 3 | 0 | #12 below: HTTP 422, old value kept; #18 HTTP 200; #21 empty: HTTP 422, old value kept |
| time_filter_block_end_utc | 2 | 2 | 0 | #24 bad time: HTTP 422, old value kept; #35 HTTP 200 |
| time_filter_block_start_utc | 6 | 6 | 0 | #2 HTTP 200; #15 HTTP 200; #25 bad time: HTTP 422, old value kept |

Not drawn by this seed (covered by the per-field validator tests): initial_balance.

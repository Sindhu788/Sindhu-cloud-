
---
# PART 2 RESUME NOTES (2026-11-03, second session)
- Server on 8431 stopped (PID 14716). Worktree `D:\sindhu_recovery` = branch `recovery/stable` (base main b2e790c + all 13 Codex commits cherry-picked cleanly, then fix commits).
- Commit 0504b08: hermetic tests/conftest.py (temp SINDHU_DATA_DIR + init_db), expiry test made date-relative, nav test includes control_room. Fixes 33/35 original "env" failures.
- requirements.lock.txt added (75 pkgs, from scratch venv at scratchpad/venv). Playwright installed into same venv. Node NOT installed (BLOCKED-USER for market_history tests).
- Baseline: orig tree + hermetic conftest running -> scratchpad/pytest_orig2.log.

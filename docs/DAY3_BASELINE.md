# Day 3 baseline (4 Nov 2026, ~08:40 UTC) - evidence only

| Item | Value | Source |
|---|---|---|
| Cloud /health | status ok, version 5.1-cloud, commit `65b0a36`, engine_running true, cloud_mode true, live_candles_only true, db_backend postgres, started_at 2026-11-04T08:18:33Z; answered in 1.5 s (instance was awake) | `curl /health` |
| Deployed commit vs repo | Deployed `65b0a36` = origin/codex/trading-intelligence. Local branch `recovery/clean` HEAD `b20b557` is the SAME TREE: `65b0a36` is the merge commit made in the deploy worktree D:\sindhu_merge (parents: the old deploy tip and `b20b557`). No mismatch in content. | `git ls-remote`, `git log` in D:\sindhu_merge |
| Local app | http://127.0.0.1:8420/health -> `{"status":"ok","safe_start":true}` (runs from the scratchpad venv, see RUNBOOK 11) | curl |
| Scan receipts, Cloud (Neon `paper_scan_log`) | 85 rows in total, newest `2026-11-03T20:18:55Z`; nothing in the ~12 h since | read-only SQL |
| Scan receipts, Local | none by design (local is safe-start, never scans) | DB / code |
| Render instances (new instance id = new process) | 3 Nov 18:08, 18:46 (x2), 19:20, 19:39, 20:18 (x2), 21:23, 21:24; 4 Nov 03:13, 03:14, 03:32, **08:18** (current) | Render logs "Waiting for application startup" |
| Warnings/errors in the Render log since 00:00 UTC 4 Nov | none | `list_logs level=warning,error` |
| Cloud CPU / RAM since the 08:18 start | CPU 0.007-0.075 of a 0.15 CPU limit (idle after the first 4 minutes); RAM 245-295 MB of 512 MB | Render metrics |
| Fast test subset | `test_scan_heartbeat`, `test_monitoring`, `test_e2e_pipeline`, `test_decision_trace`, `test_signal_start_readiness`, `test_health_light`, `test_cloud_runtime`, `test_ops_checks`, `test_instance_state`: all pass (before the Day 3 push) | pytest |
| Decision-trace activity per hour (UTC, 4 Nov) | 03h 20 rows, 04h 20, 05h 1, 06h 9, 07h 10, nothing after 07:56 | read-only SQL |

Reading: the process is restarted often (13 starts in 15 h), and between 08:18 and 08:40 it was awake with almost no CPU use but wrote no receipt and no decisions. See the root-cause analysis in docs/INVESTIGATION_REPORT.md (Day 3 section).

[PROGRESS 15% | steps 4/30 done | now: Step 6 - light /health | status: RUNNING | elapsed 50m | blockers: LAN URL unreachable (firewall)]

# Checkpoint (grand master prompt, unattended run, started 2026-11-03 ~20:45 UTC)
Resume rule: read this file, continue at "now". Local app: D:\sindhu_runtime\start_local.cmd. Work tree: D:\sindhu_clean (branch recovery/clean); deploy worktree D:\sindhu_merge (merge, fast-forward push to codex/trading-intelligence).

## Done
- Step 1: 19 targeted tests green (paging, live candles, coin mode, blacklist). Full suite started in background -> scratchpad pytest_p1.log (result recorded at Step 30 / when it finishes).
- Step 2: pushed 40ff8c0 (fast-forward, tree == recovery/clean 00791dc); Render deploy live; /health ok (started 21:23:54Z).
- Step 3: after 21:24Z no "Stale closed market candles rejected" / "Market data is empty" warnings in Render warning/error logs; positions opened at live prices (BTC/USDT 21:32Z). Scan receipts/decision rows are only written when a scan ENDS and none had ended yet (slow cold start on free plan) -> see Step 17.
- Step 4: PROOF (a): Telegram signal sent 2026-11-03 21:33:12Z success=1, BTC/USDT long, "Ichimoku 15m Indicator-Exit [Manual Build]", group profitable, confidence 46.29. 2nd candidate (Kotegawa Bear Market Reversal, BTC/USDT long) withheld as duplicate of the first. Open Losing-group positions (SOL, PEPE, PUMP) have no Telegram rows. Delivery banner READY => token/channel/master/auto flags set and SAFE_START/DRY_RUN not 1 (no values printed).
- Step 5: local /health ok (127.0.0.1:8420, safe mode). LAN 192.168.1.111:8420 NOT reachable (likely Windows Firewall). Local sends hard-blocked (OWNER=disabled, no token). Local scanning intentionally OFF (decision D11).

## Open problems
- LAN access needs a firewall rule (owner).
- Scan end-to-end time on Render free plan is long (decision rows buffered until the scan ends).

# ROLLBACK: going back to a known-good version (master plan A25 / P43)

Use this when Cloud is broken after a deploy: a crash loop, `/health` failing, memory above 450 MB for long, or wrong behaviour.

## Way 1: Render dashboard (fastest, no laptop needed)
1. Open https://dashboard.render.com and sign in.
2. Click the service **Sindhu-cloud--1**.
3. Click **Events** (or **Deploys**) on the left.
4. Find the last deploy marked **Live** that worked. Its commit id is in the list below.
5. Click its **⋯** menu → **Rollback** (or "Redeploy"). Confirm.
6. Wait 2–3 minutes. Open https://sindhu-cloud-1.onrender.com/health and check that `"commit"` shows that id.

Note: Render auto-deploys the branch `codex/trading-intelligence`. The next push deploys again on top of the rollback.

## Way 2: git (when you want the code itself back)
In the merge folder `D:\sindhu_merge`:
```
git revert --no-edit <bad commit id>
git push origin HEAD:codex/trading-intelligence
```
`git revert` adds a new commit that undoes the bad one. Nothing is deleted and no force-push is needed.

## Known-good commits
| Commit | Date (UTC) | What | Checked |
|---|---|---|---|
| c035ca3 | 2026-11-05 13:29 | Day 7 final | /health OK, CI green |
| 6390321 | 2026-11-05 22:37 | Master plan D1 (health HEAD, light 404, incremental candles, deadlines, Neon breaker, no Bybit, public signals off) | /health OK, HEAD 200, CI green; 2,568 tests passed |
| 02d12c3 | 2026-11-05 23:07 | Master plan D2 (MAIN_WALLET, owner-only commands, Cloud password guard, self-check, /health/details) | /health/details: trading enabled, self-check 4/4; 2,596 tests passed |

Safety: tag `pre-recovery-backup` (from before all this work) also still exists in git.

## Master plan V2 deploys (G1 ab38f58; G2/G3 below)
- Last good before V2: **3eabeac** (V1 D3). After G1: **ab38f58**.
- Fast rollback of a V2 UI deploy (login problem, broken page): in `D:\sindhu_merge`:
  `git revert --no-edit -m 1 <merge commit>` then `git push origin HEAD:codex/trading-intelligence` (no force push). Render redeploys
  in about 2 minutes; check `/health` shows the expected commit.
- The old dashboard never went away: `/legacy` serves the unchanged app.js even while the new pages are live.

# Weekly review routine (15 minutes, every Monday)

1. **Is Cloud alive?** Open `https://sindhu-cloud-1.onrender.com/health` (wakes it) - then the dashboard warning banner at the bottom must be empty. Banner items mean: engine OFF, signals BLOCKED (lists why), stale scan, skipped candle frames, database nearly full.
2. **Settings parity:** Local dashboard -> `/api/ops/settings-parity` should show 0 unexpected differences (engine_enabled / telegram send flags / token flags differ by design).
3. **Scorecard:** run `python scripts/weekly_scorecard.py docs/SCORECARD_<date>.md` on Local (reads the local DB) and on Cloud (set `DATABASE_URL` to Neon; read-only). Read: overall PF, Profitable+Challenge expectancy, worst coins, "Recommended pauses".
4. **Signals:** count messages sent this week (Telegram dashboard) vs. withheld (Paper Trading -> decision log reasons). Zero signals is acceptable if nothing qualified; it is NOT acceptable if the banner shows a blocker.
5. **Pauses:** for each strategy in "Recommended pauses" (>= 25 trades and win-rate upper bound below break-even) decide pause / keep. The system never pauses anything by itself except through its existing guards.
6. **Confidence check:** once >= 100 trades exist after 17 Sep, read the calibration table. AUC near 0.5 = the score is noise; do not trust high-confidence labels.
7. **Housekeeping:** DB size warning, Render free hours (shared across all free services), pending secret rotations, Definition-of-Done table (`docs/DEFINITION_OF_DONE.md`).
8. **Write down** any change you made in `docs/DECISIONS.md` (date, what, why).

# How to test a NEW strategy idea safely (plain language) - written 5 Nov 2026

**The rule:** a new idea never goes to Cloud, never sends a Telegram message, and never touches your real strategies. It is tested on the laptop in a locked room (a "sandbox"), and the result is one readable page (the *dossier*). Only after that page says ROBUST **and** a 60-day forward test passes can you decide to promote it (docs/PIPELINE.md).

## What you provide
1. **The idea, in plain words**, on the one-page template below (also saved as `docs/templates/CANDIDATE_CLAIM_TEMPLATE.md`). The most important line is: *what is the edge, and WHY should it exist?* (who is on the other side of the trade, and why do they lose?). If you cannot answer that, the idea is probably noise.
2. **The strategy rules as a strategy file.** Either (a) the normal import of the video/text, run with scratch folders (see "Import" below), or (b) ask the assistant to write the file from your one-page template. Either way the file ends up in a *scratch library folder*, for example `D:\sindhu_data\candidates\my_library\<strategy id>\`.

## The three commands (copy-paste, one at a time)
All three run on your laptop only. Use the data/backtest environment `D:\sindhu_venv_bt`.

**1. Put the strategy file in a scratch library** (the demo does this for you):
```bash
D:\sindhu_venv_data\Scripts\python.exe D:\sindhu_clean\tools\make_demo_candidate.py D:\sindhu_data\candidates\demo_library
```
For your own idea the folder `D:\sindhu_data\candidates\my_library\<id>` must contain `meta.json` and `versions\v1.json` (the assistant creates them for you).

**2. Run the evaluation** (about 2 minutes for a 4-hour strategy on 47 coins; more for 1-minute strategies):
```bash
cd D:\sindhu_clean
D:\sindhu_venv_bt\Scripts\python.exe -m data_platform.candidate_eval --library-dir D:\sindhu_data\candidates\demo_library --strategy-id demo4hbreak01 --claim D:\sindhu_data\candidates\demo_claim.md --coins 50 --workers 3
```
It prints the path of the dossier at the end.

**3. Open the dossier** (a text file; any editor opens it): `D:\sindhu_data\candidates\<id>_<date>_<time>\DOSSIER.md`.

## How the sandbox protects you
Before anything else the tool **removes every password/token/key-like setting from its own environment** and **blocks every outgoing internet connection** (also in its helper processes). So it cannot log in to Cloud or the database, and it cannot send a Telegram message, even by mistake. It reads your candle files and writes only into its own folder. This is tested by 7 automatic tests (`tests/test_candidate_sandbox.py`), including one that starts the real tool with a fake token and a connection to the Telegram address and checks both fail. It never reads the sealed Sep-Oct 2026 window or any data after 6 Nov 2026.

## How to read the dossier (one page)
- **Section 2, the verdict:** the label and the key numbers. Labels: **ROBUST** (passed everything), **FRAGILE** (profit factor above 1 but a robustness rule failed), **FAILED** (loses money after costs), **INSUFFICIENT_DATA** (too few trades to say anything).
- **Profit factor (PF):** total won divided by total lost, after costs. Below 1 = loses money. We want it above 1.1 even when costs are 50 % higher ("x1.5").
- **The 95 % interval of the PF:** the honest range. If it includes 1.0, the result could be luck.
- **Random-entry test:** the same trades but at random times (same direction mix, same holding times, same costs). "p" is the chance random entries do as well; we want p below 0.05. In a falling market a short-biased random book also wins, so this test catches strategies that only ride the market.
- **Baselines:** two boring rules (a moving-average rule and an RSI rule). A new idea must beat them.
- **Fee sensitivity (x1 / x1.5 / x2):** if the profit disappears when costs rise 50 %, it is not a real edge.
- **Windows and coins:** the strategy must work in most of the 8 time windows and on most coins, not in one episode or on one coin.

## What ROBUST requires (all of these)
At least 300 positions and 6 of the 8 time windows with 30+ positions; profit factor 1.1+ in at least 60 % of the windows and of the coins; profit factor above 1.1 at normal costs and above 1.0 at 1.5x costs; the 95 % interval of the PF above 1; the random-entry p below 0.05 (corrected for testing many ideas); better than both baselines. **Then** a pre-registered forward test: at least 60 days and 100 positions after the registration date, evaluated once (docs/BACKTEST_PROTOCOL.md section 9), and **your approval**. Nothing is promoted by the assistant.

## The proof run (5 Nov 2026)
A demo idea ("4h breakout above SMA50, long only", textbook trend following) went through all three commands: 1,364 positions on 47 coins, **profit factor 0.76 after costs, label FAILED**, in about 2 minutes. That is the expected result for a plain textbook rule in a falling market, and it shows the tool works and says no when the answer is no.

## Import with scratch folders (not tested today: NOT VERIFIED)
The normal import (AI reads the text/video) writes into the live strategy library. To keep a candidate away from the real one, start the local app from a terminal with two scratch folders before importing:
```bash
set SINDHU_DATA_DIR=D:\sindhu_data\candidates\sandbox_db
set SINDHU_STRATEGY_LIBRARY_DIR=D:\sindhu_data\candidates\my_library
```
then import, and the new strategy folder appears in `my_library`. I did not test this import path today; if in doubt, ask the assistant to write the strategy file from your template.

## One-page template (fill this in before running)
```
IDEA (one sentence):
WHY SHOULD AN EDGE EXIST? (who loses money to this rule, and why do they keep losing?):
RULES (when to buy, when to sell, where is the stop, where is the target):
TIMEFRAME and typical holding time:
WHICH COINS / WHICH MARKET CONDITIONS (and where it should NOT work):
EXPECTED FAILURE MODES (how would this idea lose money? what regime breaks it?):
WHAT RESULT WOULD MAKE ME STOP BELIEVING IT (a number, decided in advance):
WHAT I ALREADY LOOKED AT (charts / earlier tests, so they are not counted as new evidence):
```

## Daily portfolio strategies (master plan B7, the V2 benchmark pipeline)
**Hinglish:** naya daily strategy test karna ho (bina Claude):
1. Pehle `docs/BENCHMARK_PREREGISTRATION_V2.md` jaisa ek naya file likho: rules, coins, costs, pass criteria. **Result dekhne se PEHLE** `git commit` karo.
2. Data: `D:\sindhu_venv_bt\Scripts\python.exe -m data_platform.daily_download` (daily candles, resumable), phir `python tools/daily_quality.py`.
3. Code: `data_platform/benchmark_v2.py` mein ek naya `*_signal(p)` function (sirf din t ke close tak ka data) aur `run_strategy` mein ek naam.
4. Test: `tests/test_benchmark_v2.py` jaisa no-lookahead test likho, phir `pytest`.
5. Run: `python -m data_platform.benchmark_v2_run --job-dir D:\sindhu_runtime\bt_jobs\<naya-naam>` (purane folder kabhi overwrite nahi hote).
6. Report: `python tools/benchmark_v2_report.py --job <folder> --write`. Verdict FAILED/FRAGILE aaye to wahi likho, parameters badal kar dobara mat chalao.

**English:** (1) pre-register and commit before any result; (2) download native daily data and run the quality check; (3) add a
signal function that only reads data up to the close of day t; (4) add a no-lookahead unit test; (5) run the resumable job into a new
folder; (6) write the report. Never re-tune after seeing results; a re-run counts as a new test for the FDR rule.

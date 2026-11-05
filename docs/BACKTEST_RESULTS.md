# Backtest results (Day 5, 5 Nov 2026)

**Setup:** 42 enabled strategies x 10 liquid coins (Binance spot 1m data resampled), development window 1 Nov 2025 - 31 Aug 2026, 8 walk-forward windows, costs per docs/BACKTEST_PROTOCOL.md. **No strategy parameter was changed.** The sealed holdout (Sep-Oct 2026) was NOT touched. Run: 420 runs with `python -m data_platform.protocol_run --coins 10 --workers 3` (about 43 min of compute, it was interrupted once and resumed), analysis with `python -m data_platform.protocol_analyze`. Raw results: `D:\sindhu_data\experiments\protocol_results.json`.

## Verdict (honest)

- Labels: **0 ROBUST, 0 FRAGILE, 32 FAILED, 10 INSUFFICIENT_DATA**.
- **No strategy passed the protocol.** Every strategy with enough trades has a profit factor below 1 after realistic costs; 32 of 32 testable strategies FAILED.
- The 10 INSUFFICIENT_DATA strategies traded too rarely (under 300 trades or under 6 usable windows). Some show PF above 1 (e.g. the three Ichimoku trailing/indicator-exit variants) but on 21-110 trades with t-statistics around 1: that is noise, not evidence.
- Caveats: only 10 coins and 10 months (sample sizes are in the table); spot costs only, no funding; the paper engine's results on live data may differ. This is a statement about THESE rules on THIS data, not a forecast.
- **Day 5 inconsistency explained and fixed (Day 6 Step 4-5):** see section 'Metrics audit' at the end. Only Daily Liquidity Scalping was affected; no label changed.

## Per-strategy table (sorted by label, then PF after costs)

| Label | Strategy | Entry TF | Trades | Win % | PF x1 | PF x1.5 | PF x2 | PF gross | Windows ok | Coins ok | t (mean R) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FAILED | Dumb Money Concepts -- Confirmation Entry [Manual Build] | 4h | 302 | 18.2 | 0.9414764139163441 | 0.8523349275553374 | 0.7769999324756822 | 1.179737646046196 | 1/6 | 3/6 | -0.19 |
| FAILED | 4-Hour Range Breakout-Retest [Manual Build] | 5m | 2262 | 33.5 | 0.8046014832789645 | 0.7235281997381546 | 0.6525634878189439 | 1.0071481073860762 | 0/8 | 0/10 | -5.02 |
| FAILED | Laxman Rekha 5-EMA Trigger-Candle Strategy [Manual Build] | 5m | 2672 | 24.6 | 0.7752888159719767 | 0.7004207926198037 | 0.6356166122713517 | 0.9663178919428144 | 0/8 | 0/10 | -5.91 |
| FAILED | Kotegawa Bear Market Reversal Strategy [Manual Build] | 15m | 752 | 22.5 | 0.7750032372755965 | 0.7340688043814687 | 0.6962825823910055 | 0.8680335604278174 | 2/6 | 0/10 | -3.12 |
| FAILED | Range Breakout Volume Confirmation [Manual Build] | 15m | 641 | 44.9 | 0.7735049982739326 | 0.6462499234548148 | 0.5449361859993367 | 1.1340793050169138 | 0/6 | 0/5 | -1.29 |
| FAILED | Liquidity Sweep Reversal Strategy [Manual Build] | 15m | 4606 | 49.6 | 0.7685014539243072 | 0.6581089798818989 | 0.5637092296740555 | 1.0493900619752239 | 0/8 | 0/9 | -7.16 |
| FAILED | Liquidity Sweep Multi-Confirmation [Manual Build] | 5m | 1429 | 21.6 | 0.7608348895281692 | 0.6683560311495916 | 0.5926715615992804 | 1.0224919008548023 | 1/8 | 0/8 | -3.15 |
| FAILED | Daily Liquidity Scalping Strategy [Manual Build] | 1m | 6920 | 44.8 | 0.7496518197928502 | 0.6623936599311268 | 0.5870029085870486 | 0.9730729960858604 | 1/8 | 0/10 | 11.54 |
| FAILED | Ichimoku 1h Indicator-Exit [Manual Build] | 1h | 2726 | 27.4 | 0.721081148102507 | 0.5995938784951624 | 0.506230710849955 | 1.0977666064839002 | 1/8 | 1/10 | -5.56 |
| FAILED | OTE Liquidity Sweep Reversal [Manual Build] | 15m | 2703 | 27.5 | 0.7160536562259262 | 0.6016717310764054 | 0.510451635506778 | 1.0603525617698553 | 0/8 | 0/10 | -8.23 |
| FAILED | PDH/PDL Multi-Timeframe Reversal [Manual Build] | 5m | 1798 | 25.1 | 0.7045597982186822 | 0.5997703383879218 | 0.5153516221086586 | 1.0141249839023383 | 0/8 | 0/10 | -7.41 |
| FAILED | Asian Range London Sweep [Manual Build] | 5m | 557 | 30.9 | 0.7025546517275951 | 0.6271853268531161 | 0.5618397449413725 | 0.8938685203666958 | 1/8 | 1/10 | -4.07 |
| FAILED | Liquidity Sweep + Engulfing Candle (Strict) [Manual Build] | 5m | 3577 | 33.0 | 0.7021682894669196 | 0.5983955837917149 | 0.5125988823178286 | 0.9922291570814812 | 0/8 | 0/10 | -10.37 |
| FAILED | FVG Pure + Inverse FVG (Structure) [Manual Build] | 1h | 3492 | 37.9 | 0.6831640649892707 | 0.5333477769441055 | 0.42335202511673414 | 1.1733454850884886 | 1/8 | 1/10 | -2.0 |
| FAILED | Candle Range Theory (Loose) [Manual Build] | 1h | 3696 | 32.9 | 0.6784385959243404 | 0.5620065093000246 | 0.46814425138479593 | 1.0217988088863412 | 0/8 | 0/10 | -13.36 |
| FAILED | Support/Resistance + Liquidity Sweep (Fixed-RR) [Manual Build] | 1h | 1330 | 45.4 | 0.6731825062251365 | 0.5543588187366533 | 0.4551527277293954 | 0.9912659390100738 | 1/8 | 0/10 | -7.05 |
| FAILED | Liquidity Sweep + Engulfing Candle (Loose) [Manual Build] | 5m | 5646 | 32.1 | 0.672013573578392 | 0.5757884963522607 | 0.4956016037345481 | 0.9366370702726408 | 0/8 | 0/10 | -15.35 |
| FAILED | FVG Pure + Inverse FVG (Fixed 1:2) [Manual Build] | 1h | 3605 | 33.5 | 0.6700923687864583 | 0.5505447137447828 | 0.4550656291556098 | 1.0299260115094155 | 0/8 | 0/10 | -11.69 |
| FAILED | HTF-LTF FVG/OB Confluence Entry [Manual Build] | 15m | 3271 | 51.0 | 0.6656933760316597 | 0.5181773835544085 | 0.40752577538573964 | 1.0994209322523858 | 1/8 | 0/8 | -4.84 |
| FAILED | Order Block Trading (Strict) [Manual Build] | 1h | 884 | 44.5 | 0.6636897166299149 | 0.5669305879270385 | 0.48710877372293615 | 0.9211256157857397 | 1/8 | 0/9 | -4.43 |
| FAILED | Fibonacci Golden Zone Retracement [Manual Build] | 1h | 4331 | 36.8 | 0.6610784500701805 | 0.5497408799981135 | 0.46028555889550393 | 0.983364379211928 | 0/8 | 0/10 | -12.4 |
| FAILED | Previous High/Low Reversal [Manual Build] | 15m | 3784 | 42.6 | 0.6539700067972533 | 0.5497014386111163 | 0.46428907157692256 | 0.9391893245349896 | 0/8 | 0/10 | -10.01 |
| FAILED | Candlestick Pattern Reversal Strategy [Manual Build] | 15m | 3625 | 43.1 | 0.6484204258763926 | 0.5456611482713427 | 0.4603732037193243 | 0.9244184022419084 | 0/8 | 0/10 | -10.01 |
| FAILED | Market Structure Shift Reversal [Manual Build] | 15m | 2553 | 48.4 | 0.6355652895654412 | 0.544372744134532 | 0.46821907964345755 | 0.873758093426948 | 0/8 | 0/9 | -8.12 |
| FAILED | Candle Range Theory (Strict) [Manual Build] | 1h | 662 | 31.7 | 0.6244802979761623 | 0.5144473924391777 | 0.4263624321587936 | 0.9540912489214423 | 0/8 | 0/10 | -6.36 |
| FAILED | Equal Highs/Lows Reversal [Manual Build] | 15m | 5012 | 46.7 | 0.6139101457702385 | 0.49452644110484656 | 0.40139885382456153 | 0.9553133634437612 | 0/8 | 0/8 | -10.59 |
| FAILED | FVG Momentum Pullback (Structure) [Manual Build] | 1h | 1885 | 35.5 | 0.6020210743471078 | 0.477499886310539 | 0.38356557632959465 | 0.9968776869864584 | 0/8 | 0/10 | -7.06 |
| FAILED | Fixed Range Volume Profile -- Market Shape [Manual Build] | 1h | 4869 | 39.9 | 0.5907261457358272 | 0.4783279615283038 | 0.390308210908439 | 0.9193626959973654 | 0/8 | 0/10 | -15.87 |
| FAILED | Ichimoku 15m Indicator-Exit [Manual Build] | 15m | 10495 | 21.8 | 0.5814686017658499 | 0.44658477472673597 | 0.35313725989715555 | 1.1031157518980017 | 0/8 | 0/10 | -20.72 |
| FAILED | Liquidity Sweep + CISD (Pure Swing Variant) [Manual Build] | 5m | 2097 | 39.1 | 0.5703178818336537 | 0.46018789541520155 | 0.37308706165437694 | 0.8937600676883827 | 0/8 | 0/10 | -11.34 |
| FAILED | Donchian LWTI Volume Confluence [Manual Build] | 15m | 1626 | 56.5 | 0.509953518459 | 0.37849621080295603 | 0.2836002476892193 | 0.9089988373162101 | 1/8 | 1/9 | -7.8 |
| FAILED | Ichimoku 5m Indicator-Exit [Manual Build] | 5m | 29591 | 16.8 | 0.41880838230456574 | 0.2998830314899606 | 0.22378284850910227 | 0.9889849169345812 | 0/8 | 0/10 | -61.98 |
| INSUFFICIENT_DATA | Ichimoku 1d Trailing-SL [Manual Build] | 1d | 21 | 42.9 | 1.9333953128359578 | 1.8433922242877345 | 1.7590896671382001 | 2.1329836353293072 | 0/0 | 0/0 | 1.01 |
| INSUFFICIENT_DATA | Ichimoku 1d Indicator-Exit [Manual Build] | 1d | 108 | 32.4 | 1.7820383955399353 | 1.6419749437210092 | 1.5189210672596332 | 2.130102601621192 | 0/1 | 0/0 | 1.7 |
| INSUFFICIENT_DATA | Ichimoku 15m Trailing-SL [Manual Build] | 15m | 110 | 9.1 | 1.6316947497088239 | 1.5079502179680295 | 1.4008906184412753 | 1.9472887161143169 | 1/1 | 0/0 | 0.91 |
| INSUFFICIENT_DATA | SMA-Alignment Strategy (Approximate - ZIP Indicator Excluded) [Manual Build] | 1h | 321 | 40.2 | 1.009963132682655 | 0.9025939941437404 | 0.8088984168499729 | 1.276229778515724 | 1/3 | 1/5 | 0.08 |
| INSUFFICIENT_DATA | Supply/Demand Zone Strategy [Manual Build] | 1h | 82 | 24.4 | 0.8821854711560588 | 0.7858802368462404 | 0.7044678350403819 | 1.1394802607454255 | 0/0 | 0/0 | -0.47 |
| INSUFFICIENT_DATA | Heikin Ashi Trend Reversal [Manual Build] | 15m | 248 | 29.4 | 0.7963010440965989 | 0.6718185080871552 | 0.5721608409778952 | 1.1680734283322167 | 0/6 | 0/3 | -1.53 |
| INSUFFICIENT_DATA | Ichimoku 1h Trailing-SL [Manual Build] | 1h | 53 | 13.2 | 0.6768200156392349 | 0.6492004112975935 | 0.6235330426638734 | 0.7388801826536101 | 0/0 | 0/0 | -0.98 |
| INSUFFICIENT_DATA | Dumb Money Concepts -- Combined Confirmation [Manual Build] | 4h | 271 | 15.5 | 0.6696401015037156 | 0.6070976952298279 | 0.5541849073563773 | 0.8363906487030216 | 2/5 | 1/4 | -1.73 |
| INSUFFICIENT_DATA | 9-20 EMA SMC Hybrid [Manual Build] | 15m | 269 | 31.6 | 0.6167101991128721 | 0.5209862310225086 | 0.4421079962108259 | 0.8861434040628755 | 0/5 | 0/4 | -3.83 |
| INSUFFICIENT_DATA | SAR + SMC (CISD Entry) [Manual Build] | 5m | 64 | 48.4 | 0.3478094761717076 | 0.19441512805230907 | 0.10404898588903891 | 0.9067811950132557 | 0/0 | 0/0 | -3.18 |

Bonferroni threshold t >= 3.24; none of the strategies with positive PF qualifies.

## What this means for the owner
- Do not trust any strategy's claimed edge from this backtest: none showed one. Existing safety gates (Wilson 25-trade, Evolution 100-trade, confluence) remain the right filter; nothing here changes them.
- Next honest steps: investigate the Daily Liquidity Scalping discrepancy; widen to 50 coins; collect more paper trades. The sealed holdout stays unopened until a candidate exists.

## Metrics audit (Day 6, 5 Nov 2026)
**Question:** Daily Liquidity Scalping (sid b36687e8401a) showed t = +11.54 (mean R positive) but profit factor 0.75 and a net result of -6,588.1 (money, 10 coins, 10 months).
**Method:** independent script `tools/recompute_metrics.py` (plain numpy, imports nothing from data_platform), run on the stored raw trades.
**Cause (numbers from the raw trades):**
1. The engine closes this strategy's entries in TWO legs: a partial take-profit leg (80 % of the size, risk 8) and a remainder leg (20 %, risk 2). 6,920 stored records = **5,011 positions** (1,909 of them have two legs). Day 5 treated every leg as a separate trade.
2. R was computed per leg as pnl / that leg's own risk. The small-risk remainder legs hit 2.75 R targets (1,181 take-profit legs, mean R +2.75) and dominate an unweighted average: mean R per leg = +0.219 (t +11.54), but money-weighted R (sum pnl / sum risk) = -0.185 and the position-level result is a loss.
3. Counting legs as independent trades also inflated n (6,920 vs 5,011) and changed the win rate (44.8 % per leg vs 38.1 % per position).
Not the cause (checked): fees (net = gross - commission; gross PF is 0.89, still < 1, so the strategy loses before fees too), sign errors, duplicates (the 10 'duplicate' keys are legs of one position ending at end-of-data), look-ahead (not examined by this audit).
**Fix:** `data_platform/metrics.py` defines every metric once (unit = position, R = position pnl / position risk); `protocol_analyze.analyze_strategy` now uses it. Tests: `tests/test_metrics.py` (9 tests with hand-computed profit factor, win rate, expectancy, t-statistic, drawdown, fees, zero- and one-trade inputs; the analyzer test fails on the old analyzer and passes on the new).
**Before / after (all 42 strategies re-labelled from the stored runs):** labels unchanged (32 FAILED, 10 INSUFFICIENT_DATA). Only Daily Liquidity Scalping's numbers changed: trades 6,920 -> 5,011, PF 0.750 -> 0.738, t +11.54 -> -10.82, win rate 44.8 % -> 38.1 %. For the other 41 strategies every entry has exactly one leg, so legs = positions and the independent script reproduces the framework's profit factor and t-statistic exactly.
**Three other strategies checked as requested:** winner-looking Ichimoku 1d Trailing-SL (21 positions, PF 1.93, t +1.01); loser Ichimoku 5m Indicator-Exit (29,591 positions, PF 0.42, t -61.98); INSUFFICIENT 9-20 EMA SMC Hybrid (269 positions, PF 0.62, t -3.83). Framework and independent numbers agree for all three.
**Remaining weakness (important):** trades are not independent. Lag-1 autocorrelation of R is 0.12-0.28 for these strategies and many positions open on the same days across coins. Clustering the R values by exit day shrinks the evidence a lot:
| Strategy | positions | days | t per trade | t per day (clustered) |
|---|---|---|---|---|
| Daily Liquidity Scalping | 5,011 | 299 | -10.82 | +0.56 |
| Ichimoku 1d Trailing-SL | 21 | 12 | +1.01 | -2.35 |
| Ichimoku 5m Indicator-Exit | 29,591 | 304 | -61.98 | -27.09 |
| 9-20 EMA SMC Hybrid | 269 | 156 | -3.83 | -2.90 |
Per-trade t-statistics therefore overstate significance. (The per-day R is an equal-weight average, so it can differ from the money view; both are shown.) Step 6 adds block-bootstrap intervals for this reason.

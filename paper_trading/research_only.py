"""Research-only timeframes (Day 6 Step 18). OFF by default: with SINDHU_RESEARCH_ONLY_TIMEFRAMES unset or empty nothing is skipped.
Set it (for example "1m,3m") on the LIVE service to stop evaluating strategies whose ENTRY timeframe is in the list - the live scan cannot serve them
(a candle every minute vs a scan that takes minutes). The strategies stay enabled and stay backtestable locally; they simply produce no live candidates,
which also saves scan CPU. This is a promotion-pipeline decision (docs/PIPELINE.md), owner approval required."""
import os


def research_only_timeframes(env=None):
    env = os.environ if env is None else env
    raw = str(env.get("SINDHU_RESEARCH_ONLY_TIMEFRAMES", "") or "")
    return {t.strip().lower() for t in raw.split(",") if t.strip()}


def is_research_only(entry_timeframe, env=None):
    tfs = research_only_timeframes(env)
    return bool(tfs) and str(entry_timeframe or "").strip().lower() in tfs

"""Final Audit (BACKTESTING_MASTER_SPEC.md Requirements 5/18, Data Engine
/ Data Quality Report): checks real downloaded/resampled candle data for
missing candles, duplicates, invalid timestamps, corrupted OHLC, and
correct resampling. Confirmed absent anywhere in the codebase during the
earlier gap audit -- this closes that gap. Pure, read-only checks: never
mutates data, never guesses a fix, only reports exactly what's wrong.
"""

import pandas as pd

_INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "12h": 43_200_000, "1d": 86_400_000, "1w": 604_800_000,
}


def check_missing_candles(df, interval):
    """Returns a list of {gap_start, gap_end, missing_count} -- one entry
    per contiguous gap (an exchange outage shows up as ONE gap, not one
    row per missing candle inside it)."""
    if df is None or len(df) < 2 or interval not in _INTERVAL_MS:
        return []
    expected_ms = _INTERVAL_MS[interval]
    idx_ms = df.index.view("int64") // 1_000_000  # ns -> ms
    gaps = []
    for i in range(1, len(idx_ms)):
        d = idx_ms[i] - idx_ms[i - 1]
        if d > expected_ms:
            gaps.append({
                "gap_start": pd.Timestamp(idx_ms[i - 1], unit="ms", tz="UTC").isoformat(),
                "gap_end": pd.Timestamp(idx_ms[i], unit="ms", tz="UTC").isoformat(),
                "missing_count": int(d // expected_ms) - 1,
            })
    return gaps


def check_duplicate_candles(df):
    """Returns the sorted list of duplicated timestamps (ISO strings)."""
    if df is None or len(df) == 0:
        return []
    dupes = df.index[df.index.duplicated(keep=False)]
    return sorted({ts.isoformat() for ts in dupes})


def check_invalid_timestamps(df):
    """Non-monotonic ordering, or a timezone that isn't UTC (or missing
    entirely) -- either would silently corrupt every timeframe-role merge
    downstream, which assumes a clean, sorted, UTC-aware index."""
    issues = []
    if df is None or len(df) == 0:
        return issues
    if not df.index.is_monotonic_increasing:
        issues.append("timestamp index is not strictly increasing (out-of-order candles)")
    if df.index.tz is None:
        issues.append("timestamp index has no timezone (expected UTC-aware)")
    elif str(df.index.tz) != "UTC":
        issues.append(f"timestamp index timezone is {df.index.tz}, expected UTC")
    return issues


def check_corrupted_ohlc(df):
    """Returns a list of {timestamp, reasons} for every bar with an
    impossible OHLC relationship or a non-positive price/negative
    volume."""
    issues = []
    if df is None or len(df) == 0:
        return issues
    bad_mask = (
        (df["high"] < df["low"])
        | (df["open"] > df["high"]) | (df["open"] < df["low"])
        | (df["close"] > df["high"]) | (df["close"] < df["low"])
        | (df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)
        | (df["volume"] < 0)
    )
    for ts, row in df[bad_mask].iterrows():
        reasons = []
        if row["high"] < row["low"]:
            reasons.append("high < low")
        if row["open"] > row["high"] or row["open"] < row["low"]:
            reasons.append("open outside [low, high]")
        if row["close"] > row["high"] or row["close"] < row["low"]:
            reasons.append("close outside [low, high]")
        if row["open"] <= 0 or row["high"] <= 0 or row["low"] <= 0 or row["close"] <= 0:
            reasons.append("non-positive price")
        if row["volume"] < 0:
            reasons.append("negative volume")
        issues.append({"timestamp": ts.isoformat(), "reasons": reasons})
    return issues


def check_resampling(df_1m, df_resampled, interval):
    """Verifies df_resampled genuinely aggregates df_1m correctly by
    independently RE-computing the resample here and diffing -- never
    trusts that the same code path used to produce df_resampled is also
    correct to check it. Reuses data_engine.resample's own
    interval->pandas-rule table (RESAMPLE_RULE) as the one legitimate
    shared source of truth, but the aggregation itself is redone fresh."""
    from data_engine.resample import RESAMPLE_RULE
    if df_1m is None or len(df_1m) == 0 or interval not in RESAMPLE_RULE:
        return {"checked": 0, "mismatches": []}
    rule = RESAMPLE_RULE[interval]
    recomputed = df_1m.resample(rule, label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna(subset=["open"])

    mismatches = []
    common_idx = df_resampled.index.intersection(recomputed.index)
    for ts in common_idx:
        a, b = df_resampled.loc[ts], recomputed.loc[ts]
        for col in ("open", "high", "low", "close", "volume"):
            va, vb = float(a[col]), float(b[col])
            if abs(va - vb) > max(abs(vb) * 1e-9, 1e-9):
                mismatches.append({
                    "timestamp": ts.isoformat(), "column": col,
                    "stored_value": va, "recomputed_value": vb,
                })
    return {"checked": len(common_idx), "mismatches": mismatches}


def run_data_quality_report(df, interval, df_1m_for_resample_check=None):
    """One-call convenience wrapper bundling every check above into a
    single report dict with an overall PASS/FAIL verdict."""
    missing = check_missing_candles(df, interval)
    duplicates = check_duplicate_candles(df)
    bad_timestamps = check_invalid_timestamps(df)
    corrupted = check_corrupted_ohlc(df)
    resampling = (check_resampling(df_1m_for_resample_check, df, interval)
                  if df_1m_for_resample_check is not None and interval != "1m" else None)

    passed = (
        not missing and not duplicates and not bad_timestamps and not corrupted
        and (resampling is None or not resampling["mismatches"])
    )
    return {
        "interval": interval,
        "candle_count": 0 if df is None else len(df),
        "missing_candles": missing,
        "duplicate_candles": duplicates,
        "invalid_timestamps": bad_timestamps,
        "corrupted_ohlc": corrupted,
        "resampling_check": resampling,
        "pass": passed,
    }

"""Item 7 (Cross-Reference Validation) -- compares a strategy's own
source-document performance claim (captured at import time, see
ai_integration.claim_extraction) against its real, MEASURED backtest
result, and honestly flags a material divergence instead of ever letting a
document's marketing claim stand unchallenged. Read-only: never adjusts
the claim, the strategy, or the backtest result -- it only reports."""

MATERIAL_DIVERGENCE_PTS = 15.0


def compare_claim_to_backtest(claimed_win_rate_pct, actual_win_rate_pct, actual_trade_count, min_reliable_trades=25):
    """Returns a plain dict describing the comparison. Never raises.

    has_claim=False: the source document made no performance claim at all
      -- nothing to compare, nothing to warn about.
    has_result=False: a claim exists but this strategy has no completed
      backtest yet -- there is genuinely nothing real to compare it to.
    Otherwise: the real comparison, with `sample_reliable` honestly
      reflecting whether the trade count meets the same 25-trade bar used
      elsewhere in the project (paper_trading.pattern_stats.MIN_SAMPLE_SIZE)
      -- a small-sample divergence (or agreement) is labeled accordingly,
      never presented with false confidence."""
    if claimed_win_rate_pct is None:
        return {"has_claim": False}

    if actual_win_rate_pct is None or not actual_trade_count:
        return {
            "has_claim": True, "has_result": False,
            "claimed_win_rate_pct": claimed_win_rate_pct,
        }

    difference_pts = round(actual_win_rate_pct - claimed_win_rate_pct, 1)
    return {
        "has_claim": True, "has_result": True,
        "claimed_win_rate_pct": claimed_win_rate_pct,
        "actual_win_rate_pct": round(actual_win_rate_pct, 1),
        "actual_trade_count": actual_trade_count,
        "sample_reliable": actual_trade_count >= min_reliable_trades,
        "difference_pts": difference_pts,
        "diverges": abs(difference_pts) >= MATERIAL_DIVERGENCE_PTS,
    }

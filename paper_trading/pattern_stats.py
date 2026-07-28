"""Statistically-sound reliability gate for per-(strategy, coin, market
regime, session) patterns -- shared by Pattern Auto-Avoid and Lesson
Auto-Apply so neither acts on a handful of trades that could easily be
chance (a 4/5 losing streak, or a 8/10 split, both happen reasonably
often even at a true 50/50 coin flip).

Method: the Wilson score interval, the standard textbook confidence
interval for a binomial proportion (a win/loss record IS a binomial
proportion). Chosen over the plain normal/Wald approximation because the
Wald interval is known to misbehave at small-to-moderate sample sizes --
it can produce bounds outside [0, 1] and its actual coverage drifts well
below the nominal 95% exactly in the n=20-50 range this module lives in.
Reference: Wilson, E.B. (1927), "Probable Inference, the Law of
Succession, and Statistical Inference", Journal of the American
Statistical Association.

MIN_SAMPLE_SIZE (25): a conservative floor before ANY conclusion is
trusted, chosen inside the commonly-cited "20-30 trades" range for a
first believable read on a pattern's real edge. Below it, every pattern
is reported as "insufficient data -- observing" no matter how extreme
the raw win rate looks -- a 4/5 record (80%) and a 20/25 record (80%)
are the same raw percentage, but the first could plausibly happen by
chance under a true 50% coin flip about 1 time in 6, while the second is
a genuinely rare outcome (roughly 1 in 300) if the pattern had no real
edge at all.
"""

import math

MIN_SAMPLE_SIZE = 25
Z_95 = 1.959963985  # two-sided 95% confidence (Wilson score interval)

# A pattern's true win rate must be confidently on one side of 50% --
# not just its raw sample win rate -- before it's treated as "good" or
# "bad". These bounds are deliberately away from 50% (not 50/50 exactly)
# so a pattern sitting right at the coin-flip line is correctly left
# "inconclusive" rather than forced into a boost/avoid bucket.
GOOD_LOWER_BOUND = 0.55  # statistically confident true win rate > 55%
BAD_UPPER_BOUND = 0.45   # statistically confident true win rate < 45%


def wilson_interval(wins, n, z=Z_95):
    """Returns (lower, upper) as fractions in [0, 1]."""
    if n <= 0:
        return 0.0, 1.0
    p = wins / n
    denom = 1 + (z * z) / n
    center = p + (z * z) / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)
    lower = (center - margin) / denom
    upper = (center + margin) / denom
    return max(0.0, lower), min(1.0, upper)


def classify(wins, n, min_sample_size=MIN_SAMPLE_SIZE):
    """The single source of truth both Pattern Auto-Avoid and Lesson
    Auto-Apply gate their actions on. Never raises -- n=0 degrades
    gracefully to "insufficient_data" like any other under-threshold
    case, so a brand-new pattern with zero history is always safe."""
    win_rate_pct = round(wins / n * 100, 2) if n else 0.0
    if n < min_sample_size:
        return {
            "sample_size": n, "win_rate_pct": win_rate_pct, "reliable": False,
            "status": "insufficient_data",
            "conclusion": f"insufficient data -- observing ({n}/{min_sample_size} trades so far)",
            "ci_lower_pct": None, "ci_upper_pct": None,
            "method": "wilson_score_95", "min_sample_size": min_sample_size,
        }

    lower, upper = wilson_interval(wins, n)
    if lower >= GOOD_LOWER_BOUND:
        status = "reliable_good"
        conclusion = f"statistically reliable -- true win rate is very likely above {GOOD_LOWER_BOUND*100:.0f}%"
    elif upper <= BAD_UPPER_BOUND:
        status = "reliable_bad"
        conclusion = f"statistically reliable -- true win rate is very likely below {BAD_UPPER_BOUND*100:.0f}%"
    else:
        status = "reliable_inconclusive"
        conclusion = "enough data now, but not one-sided enough to act on"

    return {
        "sample_size": n, "win_rate_pct": win_rate_pct, "reliable": True, "status": status,
        "conclusion": conclusion,
        "ci_lower_pct": round(lower * 100, 2), "ci_upper_pct": round(upper * 100, 2),
        "method": "wilson_score_95", "min_sample_size": min_sample_size,
    }

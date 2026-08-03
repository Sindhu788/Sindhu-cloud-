"""Batch 7, Tasks 3 & 4: "Why This Signal" and the Signal Quality Grade --
both built ENTIRELY from data already computed at signal-send time
(paper_trading.confluence.score_confluence's result and
paper_trading.pattern_stats.classify()'s reliability result, the exact
same two things send_signal_for_position() already computes for the
message itself). No new AI calls, no new data collection -- purely
deterministic templates/rules over existing numbers.
"""

# Batch 7, Task 4: grade boundaries, in the order they're checked.
# reliable_bad (Wilson-confirmed true win rate below BAD_UPPER_BOUND,
# pattern_stats.py) always caps the grade at "C" regardless of how strong
# confluence looks this one time -- a statistically PROVEN losing setup
# is never called anything better, that would contradict the very gate
# this system otherwise trusts. Otherwise: reliable_good (Wilson-confirmed
# true win rate above GOOD_LOWER_BOUND) AND strong confluence (>=75% of
# counted factors aligned) together earn "A+"; either one alone earns
# "A"; moderate confluence alone (>=50%) earns "B"; anything weaker (or
# no usable data at all) is "C".
_STRONG_CONFLUENCE_RATIO = 0.75
_MODERATE_CONFLUENCE_RATIO = 0.5


def _confluence_ratio(confluence_result):
    if not confluence_result or not confluence_result.get("total"):
        return None
    return confluence_result["passed"] / confluence_result["total"]


def grade_signal(confluence_result, reliability_result):
    """Returns {"grade": "A+"|"A"|"B"|"C", "reason": <Roman Urdu string>}.
    Deterministic function of confluence_result/reliability_result only
    -- no new scoring inputs, no AI."""
    ratio = _confluence_ratio(confluence_result)
    reliable_good = bool(reliability_result and reliability_result.get("status") == "reliable_good")
    reliable_bad = bool(reliability_result and reliability_result.get("status") == "reliable_bad")
    strong_confluence = ratio is not None and ratio >= _STRONG_CONFLUENCE_RATIO
    moderate_confluence = ratio is not None and ratio >= _MODERATE_CONFLUENCE_RATIO

    if reliable_bad:
        return {"grade": "C", "reason": "Is exact setup ka statistically confirmed record kamzor hai (Wilson gate), isliye grade C hai."}
    if reliable_good and strong_confluence:
        return {"grade": "A+", "reason": "Confluence strong hai AUR is setup ka statistically confirmed win rate bhi acha hai."}
    if reliable_good:
        return {"grade": "A", "reason": "Is setup ka statistically confirmed win rate acha hai (Wilson gate pass)."}
    if strong_confluence:
        return {"grade": "A", "reason": "Confluence ke zyada tar factors match ho rahe hain."}
    if moderate_confluence:
        return {"grade": "B", "reason": "Confluence ke aadhe se zyada factors match ho rahe hain, lekin statistical record abhi kaafi nahi hai."}
    return {"grade": "C", "reason": "Confluence factors kam match ho rahe hain ya data abhi kaafi nahi hai."}


def explain_signal(confluence_result, reliability_result):
    """Returns a short Roman Urdu sentence (or two) explaining the signal.
    Both arguments may be None (confluence scoring or pattern lookup can
    fail/return nothing) -- degrades gracefully to an honest "not enough
    data yet" rather than fabricating a reason."""
    parts = []

    if confluence_result and confluence_result.get("total"):
        aligned_names = [f["name"] for f in confluence_result.get("factors", []) if f.get("result") is True]
        passed, total = confluence_result["passed"], confluence_result["total"]
        if aligned_names:
            parts.append(f"{passed}/{total} confluence factors match huay: {', '.join(aligned_names)}.")
        else:
            parts.append(f"Confluence: {confluence_result.get('label', '-')}.")
    else:
        parts.append("Confluence ke liye abhi kaafi data nahi hai.")

    if reliability_result and reliability_result.get("reliable"):
        parts.append(
            f"Is exact setup (isi strategy, coin, aur market condition) ka real record "
            f"{reliability_result['win_rate_pct']:.0f}% win rate raha hai "
            f"{reliability_result['sample_size']} trades mein "
            f"(95% range {reliability_result['ci_lower_pct']:.0f}%-{reliability_result['ci_upper_pct']:.0f}%)."
        )
    elif reliability_result:
        parts.append(
            f"Is exact setup ka statistical record abhi ban raha hai "
            f"({reliability_result['sample_size']}/{reliability_result['min_sample_size']} trades so far)."
        )

    return " ".join(parts)

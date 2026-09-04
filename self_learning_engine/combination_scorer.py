"""Phase 1.1 + 1.3: which 2-3 concept DNA-tag combinations are worth trying
next, and which coins they've worked best on -- driven entirely by real
system-wide evidence, never a guess or a random pairing.

Reuses evolution_engine.mutator.research_dna_correlations() (the exact same
BOT-lineage scoring sindhu_strategy.deterministic_builder already consults)
extended to 3-tag combos, pooled with every currently-tracked strategy's
real paper-trading score -- the SAME two data sources deterministic_builder.
dna_score_correlations() uses, just not capped at 2. The per-coin breakdown
(which deterministic_builder does not compute at all) is new: it reuses
data_engine.storage.list_paper_coin_strategy_matrix (the same raw material
paper_trading.coin_heatmap already reads) joined against each strategy's own
DNA tags.

A "combo" here is a tuple of DNA_CATEGORIES tags (e.g. ("liquidity",
"volume")), not concept names yet -- concept selection happens in
candidate_builder.py, using this module's per-combo real-coin evidence to
prefer concepts/coins that have actually worked.
"""

from itertools import combinations

from backtest_engine import strategy_library
from data_engine import storage
from evolution_engine import dna, mutator as evo_mutator

MAX_COMBO_SIZE = 3
MIN_COMBO_SIZE = 2
MIN_SAMPLE = 1
TOP_COINS_PER_COMBO = 5


def _paper_trading_dna_by_strategy():
    """{strategy_id: sorted DNA tags} for every strategy with a saved
    config -- built once and reused for both the score pooling and the
    per-coin breakdown below, avoiding loading each strategy's config
    twice."""
    result = {}
    for meta in strategy_library.list_all():
        try:
            config = strategy_library.load(meta["id"])
        except Exception:
            continue
        tags = tuple(sorted(set(dna.extract_dna(config))))
        if tags:
            result[meta["id"]] = tags
    return result


def score_combinations(max_combo_size=MAX_COMBO_SIZE, min_combo_size=MIN_COMBO_SIZE, min_sample=MIN_SAMPLE):
    """Best-first list of {dna_combo, avg_score, sample_size, best_coins}.

    avg_score pools two real sources on the same 0-100-ish scale: BOT
    lineage evolution_score (research_dna_correlations) and live paper-
    trading score (paper_strategy_performance.score) -- exactly
    deterministic_builder.dna_score_correlations()'s own pooling, just
    sized 2-3 instead of capped at 2.

    best_coins additionally breaks each combo down by symbol (Phase 1.3's
    "which coins those concepts work best on"), using real closed-trade
    history (storage.list_paper_coin_strategy_matrix), sorted by total pnl,
    capped at TOP_COINS_PER_COMBO."""
    dna_by_strategy = _paper_trading_dna_by_strategy()

    buckets = {}
    for c in evo_mutator.research_dna_correlations(min_sample=min_sample, max_combo_size=max_combo_size):
        combo = tuple(sorted(c["dna_combo"]))
        if len(combo) < min_combo_size:
            continue
        buckets.setdefault(combo, []).extend([c["avg_score"]] * c["sample_size"])

    for perf in storage.list_paper_strategy_performance():
        tags = dna_by_strategy.get(perf["strategy_id"])
        if not tags:
            continue
        for size in range(min_combo_size, max_combo_size + 1):
            for combo in combinations(tags, size):
                buckets.setdefault(combo, []).append(perf["score"])

    coin_rows = storage.list_paper_coin_strategy_matrix()
    coin_rows_by_strategy = {}
    for row in coin_rows:
        coin_rows_by_strategy.setdefault(row["strategy_id"], []).append(row)

    results = []
    for combo, scores in buckets.items():
        if len(scores) < min_sample:
            continue
        coin_totals = {}
        for strategy_id, tags in dna_by_strategy.items():
            if not set(combo).issubset(set(tags)):
                continue
            for row in coin_rows_by_strategy.get(strategy_id, []):
                agg = coin_totals.setdefault(row["symbol"], {"total_pnl": 0.0, "closed_trades": 0, "wins": 0})
                agg["total_pnl"] += row["total_pnl"]
                agg["closed_trades"] += row["closed_trades"]
                agg["wins"] += round(row["win_rate"] / 100 * row["closed_trades"])
        best_coins = sorted(
            (
                {
                    "symbol": symbol,
                    "total_pnl": round(agg["total_pnl"], 2),
                    "closed_trades": agg["closed_trades"],
                    "win_rate": round(agg["wins"] / agg["closed_trades"] * 100, 1) if agg["closed_trades"] else 0.0,
                }
                for symbol, agg in coin_totals.items() if agg["closed_trades"] > 0
            ),
            key=lambda r: r["total_pnl"], reverse=True,
        )[:TOP_COINS_PER_COMBO]

        results.append({
            "dna_combo": list(combo),
            "avg_score": round(sum(scores) / len(scores), 2),
            "sample_size": len(scores),
            "best_coins": best_coins,
        })

    results.sort(key=lambda r: -r["avg_score"])
    return results

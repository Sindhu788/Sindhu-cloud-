from datetime import datetime, timezone

from paper_trading import scorecard


def _t(strategy, pnl, group="losing", symbol="BTCUSDT", conf=None, when="2026-10-01"):
    return {"symbol": symbol, "entry": datetime.fromisoformat(when).replace(tzinfo=timezone.utc), "pnl": pnl,
            "strategy_id": strategy, "strategy": strategy, "confidence": conf, "group": group}


def test_stats_basic_numbers():
    s = scorecard.stats([_t("a", 2.0), _t("a", -1.0), _t("a", -1.0)])
    assert s["n"] == 3 and s["wins"] == 1 and s["win_rate"] == 33.3
    assert s["avg_win"] == 2.0 and s["avg_loss"] == -1.0 and s["profit_factor"] == 1.0 and s["pnl"] == 0.0


def test_pause_recommended_only_when_conclusive_and_never_for_small_samples():
    bad = [_t("bad", -1.0) for _ in range(40)] + [_t("bad", 0.5) for _ in range(2)]          # ~5% win, 42 trades
    small = [_t("small", -1.0) for _ in range(10)]                                              # 10 trades: no conclusion
    mild = [_t("mild", 1.0) for _ in range(12)] + [_t("mild", -1.0) for _ in range(14)]         # near break-even
    rec = scorecard.recommend_pauses(bad + small + mild)
    assert [r["strategy"] for r in rec["pause"]] == ["bad"]
    assert "small" not in {r["strategy"] for r in rec["pause"] + rec["watch"]}
    assert rec["insufficient_sample"] == 1


def test_calibration_refuses_to_claim_with_too_few_post_cutoff_trades():
    old = [_t("a", 1.0, conf=80, when="2026-09-01") for _ in range(300)]
    new = [_t("a", 1.0, conf=80, when="2026-10-05") for _ in range(10)]
    c = scorecard.calibration(old + new)
    assert c["trades"] == 10 and "too few trades" in c["status"] and "buckets" not in c


def test_calibration_buckets_and_auc_with_enough_trades():
    trades = [_t("a", 1.0, conf=90) for _ in range(60)] + [_t("a", -1.0, conf=55) for _ in range(60)]
    c = scorecard.calibration(trades)
    assert c["status"] == "ok" and c["auc"] == 1.0
    assert {b["bucket"] for b in c["buckets"]} == {"50-60", "80-100"}


def test_markdown_renders_without_error():
    md = scorecard.render_markdown(scorecard.build([_t("a", 1.0, group="profitable"), _t("b", -1.0)]))
    assert "By group" in md and "Recommended pauses" in md

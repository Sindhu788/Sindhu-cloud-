"""Item 7 (Parser & Extraction Improvements) -- Cross-Reference Validation.

Proves the document's own performance claim is (1) captured as real
structured data at extraction time, and (2) honestly compared against the
system's own real backtest result, with material divergence surfaced
plainly -- never silently trusting the source document's marketing claim."""

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from backtest_engine.claim_validation import compare_claim_to_backtest
from ai_integration import claim_extraction
from sindhu_web.api import backtesting as bt_api


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


# ------------------------------------------------------------ extraction

def test_extracts_a_win_rate_claim_from_a_realistic_document():
    text = "This scalping strategy wins 60% of the time on 5m BTCUSDT. Entry: RSI < 30."
    pct, sentence = claim_extraction.extract_claimed_win_rate(text)
    assert pct == 60.0
    assert "60%" in sentence


def test_extracts_win_rate_phrased_as_a_percent_first():
    pct, _ = claim_extraction.extract_claimed_win_rate("Backtested with a 72% win rate over 200 trades.")
    assert pct == 72.0


def test_extracts_success_rate_phrasing():
    pct, _ = claim_extraction.extract_claimed_win_rate("This system has a success rate of 55.5% historically.")
    assert pct == 55.5


def test_returns_none_when_no_claim_is_made():
    pct, sentence = claim_extraction.extract_claimed_win_rate("Enter long when RSI crosses above 30.")
    assert pct is None
    assert sentence is None


def test_never_invents_an_out_of_range_percentage():
    pct, _ = claim_extraction.extract_claimed_win_rate("This indicator has a 250% edge over the market.")
    assert pct is None


# ------------------------------------------------------------ comparison

def test_no_claim_means_nothing_to_compare():
    result = compare_claim_to_backtest(None, 45.0, 30)
    assert result == {"has_claim": False}


def test_claim_with_no_backtest_result_yet_is_honest_about_it():
    result = compare_claim_to_backtest(60.0, None, None)
    assert result["has_claim"] is True
    assert result["has_result"] is False


def test_material_divergence_is_flagged():
    # Document claims 80%, real backtest measured 40% -- a huge, real gap.
    result = compare_claim_to_backtest(80.0, 40.0, 50)
    assert result["diverges"] is True
    assert result["difference_pts"] == -40.0
    assert result["sample_reliable"] is True


def test_close_agreement_is_not_flagged_as_diverging():
    result = compare_claim_to_backtest(60.0, 58.0, 50)
    assert result["diverges"] is False


def test_small_sample_divergence_is_labeled_unreliable_not_hidden():
    # A big real-looking divergence, but only 10 trades -- still surfaced,
    # but honestly marked as not statistically reliable yet.
    result = compare_claim_to_backtest(80.0, 30.0, 10)
    assert result["diverges"] is True
    assert result["sample_reliable"] is False


# ------------------------------------------------------------ end-to-end via the API

def _strategy_with_claim(**overrides):
    base = dict(
        name="Claimed 60pct Win Rate Strategy",
        raw_text="This strategy wins 60% of the time. Enter when RSI < 30.",
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        exit_conditions=[],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
        claimed_win_rate_pct=60.0, claimed_win_rate_source_text="This strategy wins 60% of the time.",
    )
    base.update(overrides)
    return StrategyConfig(**base)


def test_claim_check_endpoint_reports_no_claim_when_none_was_made(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy_with_claim(claimed_win_rate_pct=None, claimed_win_rate_source_text=None))
    result = bt_api.get_strategy_claim_check(strategy_id)
    assert result == {"has_claim": False}


def test_claim_check_endpoint_compares_against_the_real_latest_batch(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy_with_claim())

    fake_batch = {"status": "completed", "strategy_name": "Claimed 60pct Win Rate Strategy", "batch_id": "b1"}
    monkeypatch.setattr(bt_api.storage, "list_recent_batches", lambda limit=200: [fake_batch])

    import backtest_engine.reports as reports_module
    monkeypatch.setattr(reports_module, "quick_batch_summary", lambda batch_id: {"win_rate": 22.0, "total_trades": 40})

    result = bt_api.get_strategy_claim_check(strategy_id)
    assert result["has_claim"] is True
    assert result["has_result"] is True
    assert result["claimed_win_rate_pct"] == 60.0
    assert result["actual_win_rate_pct"] == 22.0
    assert result["diverges"] is True
    assert result["claim_source_text"] == "This strategy wins 60% of the time."


def test_claim_check_endpoint_404s_for_missing_strategy(test_db, tmp_path, monkeypatch):
    from fastapi import HTTPException
    _isolated_library(tmp_path, monkeypatch)
    try:
        bt_api.get_strategy_claim_check("does-not-exist")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404

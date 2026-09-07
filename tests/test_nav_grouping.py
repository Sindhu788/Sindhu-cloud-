"""Batch 6, Task 2 -- pure navigation reorganization: Paper Trading and
Telegram Signals are grouped together (paper trading is what generates
the signals Telegram sends). No route/id/API changes -- every page must
remain reachable under its exact same id.

Grand Master Prompt, Phase 1 (10-Department Company Structure) regrouped
every page under a department name instead of the earlier feature-shaped
groups -- "Paper Trading" -> "Trading / Execution", "Control" ->
"Operations / System" -- but never touched any id/route, so the two
`test_every_page_id...`/`test_no_duplicate_page_ids` invariants below are
unchanged; only the specific group-name assertions were updated to match.
"""

from sindhu_web.api.home import NAV_PAGES, NAV_GROUPS, get_nav


def _page(pid):
    return next(p for p in NAV_PAGES if p["id"] == pid)


def test_paper_trading_and_telegram_signals_share_a_group():
    assert _page("paper_trading")["group"] == _page("telegram_dashboard")["group"]
    assert _page("paper_trading")["group"] == "Trading / Execution"


def test_every_page_id_from_before_this_change_still_exists():
    """No id/route was renamed or removed -- only "group" changed."""
    expected_ids = {
        "ceo", "home", "strategies", "sindhu_strategy", "web_sourced_strategies",
        "knowledge", "knowledge_compiler", "ai_center", "backtesting",
        "backtest_history", "pipeline_history", "paper_trading", "market", "data",
        "evolution", "control_center", "telegram_dashboard", "settings", "reports",
    }
    actual_ids = {p["id"] for p in NAV_PAGES}
    assert expected_ids <= actual_ids


def test_get_nav_still_returns_every_enabled_page():
    result = get_nav()
    ids = {p["id"] for p in result["pages"]}
    assert "paper_trading" in ids
    assert "telegram_dashboard" in ids
    assert result["groups"] == NAV_GROUPS


def test_control_center_and_settings_remain_reachable_under_control():
    assert _page("control_center")["group"] == "Operations / System"
    assert _page("settings")["group"] == "Operations / System"


def test_no_duplicate_page_ids():
    ids = [p["id"] for p in NAV_PAGES]
    assert len(ids) == len(set(ids))

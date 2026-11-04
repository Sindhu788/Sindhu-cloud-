import os

from paper_trading import ops_checks


def test_snapshot_has_no_secrets_and_reports_token_as_boolean(test_db, monkeypatch):
    from paper_trading import telegram_bot
    telegram_bot.save_settings(bot_token="123456:SECRETTOKEN", channel_id="-100999")
    snap = ops_checks.settings_snapshot()
    text = str(snap)
    assert "SECRETTOKEN" not in text and "-100999" not in text
    assert snap["telegram"]["bot_token_set"] is True and snap["telegram"]["channel_id_set"] is True


def test_diff_flags_unexpected_differences_and_ignores_expected_ones():
    local = {"paper": {"max_open_trades": 5, "engine_enabled": False}, "telegram": {"auto_send_enabled": False, "signal_freshness_minutes": 15}}
    cloud = {"paper": {"max_open_trades": 8, "engine_enabled": True}, "telegram": {"auto_send_enabled": True, "signal_freshness_minutes": 15}}
    d = ops_checks.diff_snapshots(local, cloud)
    assert d["unexpected"] == 1
    keys = {r["key"]: r["expected"] for r in d["differences"]}
    assert keys == {"paper.max_open_trades": False, "paper.engine_enabled": True, "telegram.auto_send_enabled": True}


def test_cloud_with_engine_off_and_blocked_delivery_warns(test_db, monkeypatch):
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    monkeypatch.setenv("SINDHU_TELEGRAM_DRY_RUN", "1")
    codes = {w["code"] for w in ops_checks.collect_warnings()}
    assert "engine_off" in codes and "delivery_blocked" in codes


def test_local_does_not_nag_about_delivery(test_db, monkeypatch):
    monkeypatch.delenv("SINDHU_CLOUD_MODE", raising=False)
    codes = {w["code"] for w in ops_checks.collect_warnings()}
    assert "delivery_blocked" not in codes and "engine_off" not in codes


def test_keepalive_workflow_pings_health_every_ten_minutes():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(root, ".github", "workflows", "keepalive.yml"), encoding="utf-8").read()
    assert '*/10 * * * *' in text and "/health" in text


def test_ci_workflow_runs_the_suite_on_push_and_pull_request():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(root, ".github", "workflows", "tests.yml"), encoding="utf-8").read()
    assert "push:" in text and "pull_request:" in text and "python -m pytest" in text and "timeout-minutes" in text

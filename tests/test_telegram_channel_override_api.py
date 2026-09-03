"""API-layer test for Grand Feature Expansion, Phase 2 Feature 22
(Multi-Channel Support) -- sindhu_web/api/paper_trading.py's dedicated
channel-override endpoint, on top of the module-level behavior already
covered in tests/test_telegram_multi_channel.py.
"""

from data_engine import config as base_config
from paper_trading import telegram_bot
from sindhu_web.api.paper_trading import ChannelOverrideRequest, set_telegram_channel_override

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_setting_an_override_via_the_endpoint(test_db):
    result = set_telegram_channel_override("strat1", ChannelOverrideRequest(channel_id="channel_A"))
    assert result["ok"] is True
    assert result["strategy_channel_overrides"] == {"strat1": "channel_A"}
    assert telegram_bot.channel_for_strategy("strat1") == "channel_A"


def test_clearing_an_override_via_the_endpoint(test_db):
    set_telegram_channel_override("strat1", ChannelOverrideRequest(channel_id="channel_A"))
    result = set_telegram_channel_override("strat1", ChannelOverrideRequest(channel_id=None))
    assert result["strategy_channel_overrides"] == {}
    assert telegram_bot.channel_for_strategy("strat1") is None


def test_setting_one_strategys_override_never_touches_another(test_db):
    set_telegram_channel_override("strat1", ChannelOverrideRequest(channel_id="channel_A"))
    result = set_telegram_channel_override("strat2", ChannelOverrideRequest(channel_id="channel_B"))
    assert result["strategy_channel_overrides"] == {"strat1": "channel_A", "strat2": "channel_B"}

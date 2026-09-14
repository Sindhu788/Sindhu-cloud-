"""Grand Master Batch, Phase 4 Item 12 -- Coin Event/News Caution Flag.

Honest-hook design: no reliable free, no-signup crypto news source
exists, so without a CEO-supplied CryptoPanic API key this stays clearly
"not available" rather than faking a caution reading.
"""

from unittest.mock import patch

import pytest
import requests

from data_engine import config as base_config
from paper_trading import coin_event_caution


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_no_api_key_configured_is_honestly_unavailable():
    result = coin_event_caution.check_coin_caution("BTCUSDT")
    assert result["available"] is False
    assert "API key" in result["reason"]


def test_settings_round_trip():
    coin_event_caution.save_settings(cryptopanic_api_key="real-test-key")
    assert coin_event_caution.load_settings()["cryptopanic_api_key"] == "real-test-key"


def test_real_call_with_key_but_network_failure_is_reported_not_faked():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key-for-test")
    with patch("requests.get", side_effect=requests.ConnectionError("network down")):
        result = coin_event_caution.check_coin_caution("BTCUSDT")
    assert result["available"] is False


def test_no_important_headlines_means_no_caution():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key-for-test")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"results": []}
        result = coin_event_caution.check_coin_caution("BTCUSDT")
    assert result["available"] is True
    assert result["caution"] is False


def test_important_headlines_raise_a_real_caution():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key-for-test")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "results": [{"title": "Big exchange delisting rumor", "url": "https://x", "published_at": "2026-01-01"}],
        }
        result = coin_event_caution.check_coin_caution("BTCUSDT")
    assert result["available"] is True
    assert result["caution"] is True
    assert len(result["headlines"]) == 1


def test_symbol_is_normalized_to_base_coin():
    coin_event_caution.save_settings(cryptopanic_api_key="fake-key-for-test")
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"results": []}
        coin_event_caution.check_coin_caution("ETHUSDT")
    params = mock_get.call_args.kwargs["params"]
    assert params["currencies"] == "ETH"

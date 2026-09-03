"""Grand Feature Expansion, Phase 1 Feature 10: closes the one identified
gap in rate-limit protection -- ai_integration/providers.py's AIProvider.chat()
previously retried a 429 (or any other transient error) immediately, with
no backoff at all, unlike data_engine/binance_client.py's existing
Retry-After-aware pattern for the exchange API. time.sleep is mocked in
every test so this file runs at normal test speed despite exercising real
retry/backoff paths.
"""

from unittest.mock import MagicMock, patch

from ai_integration.providers import ClaudeProvider


def _provider(retry_count=2):
    return ClaudeProvider(api_key="test-key", model="claude-3", retry_count=retry_count)


def _response(status_code, headers=None, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


def test_429_waits_the_retry_after_header_before_retrying(monkeypatch):
    sleeps = []
    monkeypatch.setattr("ai_integration.providers.time.sleep", lambda s: sleeps.append(s))
    success = _response(200, json_data={"content": [{"type": "text", "text": "hi"}], "usage": {}})
    rate_limited = _response(429, headers={"Retry-After": "7"})

    with patch("requests.post", side_effect=[rate_limited, success]):
        result = _provider(retry_count=2).chat("hello")

    assert result.ok is True
    assert sleeps == [7]


def test_429_without_retry_after_header_falls_back_to_a_default_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr("ai_integration.providers.time.sleep", lambda s: sleeps.append(s))
    success = _response(200, json_data={"content": [{"type": "text", "text": "hi"}], "usage": {}})
    rate_limited = _response(429, headers={})

    with patch("requests.post", side_effect=[rate_limited, success]):
        result = _provider(retry_count=2).chat("hello")

    assert result.ok is True
    assert sleeps == [5]  # 5 * (attempt=0 + 1)


def test_500_backs_off_before_retrying(monkeypatch):
    sleeps = []
    monkeypatch.setattr("ai_integration.providers.time.sleep", lambda s: sleeps.append(s))
    success = _response(200, json_data={"content": [{"type": "text", "text": "hi"}], "usage": {}})
    server_error = _response(500, text="internal error")

    with patch("requests.post", side_effect=[server_error, success]):
        result = _provider(retry_count=2).chat("hello")

    assert result.ok is True
    assert sleeps == [2]  # 2 * (attempt=0 + 1)


def test_auth_errors_never_sleep_or_retry(monkeypatch):
    sleeps = []
    monkeypatch.setattr("ai_integration.providers.time.sleep", lambda s: sleeps.append(s))
    unauthorized = _response(401, text="bad key")

    with patch("requests.post", return_value=unauthorized) as mock_post:
        result = _provider(retry_count=2).chat("hello")

    assert result.ok is False
    assert mock_post.call_count == 1  # never retried
    assert sleeps == []


def test_last_attempt_never_sleeps_after_exhausting_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr("ai_integration.providers.time.sleep", lambda s: sleeps.append(s))
    rate_limited = _response(429, headers={"Retry-After": "3"})

    with patch("requests.post", return_value=rate_limited) as mock_post:
        result = _provider(retry_count=1).chat("hello")  # 2 total attempts

    assert result.ok is False
    assert mock_post.call_count == 2
    assert sleeps == [3]  # only slept once, before the 2nd (final) attempt -- never after it


def test_network_timeout_backs_off_before_retrying(monkeypatch):
    import requests
    sleeps = []
    monkeypatch.setattr("ai_integration.providers.time.sleep", lambda s: sleeps.append(s))
    success = _response(200, json_data={"content": [{"type": "text", "text": "hi"}], "usage": {}})

    with patch("requests.post", side_effect=[requests.Timeout(), success]):
        result = _provider(retry_count=2).chat("hello")

    assert result.ok is True
    assert sleeps == [2]

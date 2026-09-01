"""External Signal Tracker -- end-to-end ingest pipeline: capture (Phase
1) -> parse (Phase 2) -> auto paper-trade (Phase 3) -> forwarding
eligibility check (Phase 5), all in one pass, per the task's own speed
requirement that a new signal is acted on immediately, not queued."""

import os
import tempfile

import pytest

import data_engine.storage as storage
from external_signals import channels, ingest, config as ext_config


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
    storage.init_db()
    # Forwarding is never configured in these tests -- confirms ingest
    # degrades cleanly (no crash) when forwarding settings are unset.
    monkeypatch.setattr(ext_config, "load", lambda: dict(ext_config._DEFAULTS))


def test_capture_never_parses_a_parsing_failure_never_loses_the_message(monkeypatch):
    cid = channels.add_channel("TEST Channel", "@test")
    ingest.capture_message(cid, "text", raw_text="Coin: BTC/USDT\nDirection: LONG\nEntry: 65000\nSL: 63000")

    messages_before = storage.list_external_messages(cid)
    assert len(messages_before) == 1
    assert messages_before[0]["processed"] == 0  # capture alone never marks processed


def test_processing_a_real_signal_opens_a_position_automatically(monkeypatch):
    cid = channels.add_channel("TEST Channel", "@test")
    ingest.capture_message(cid, "text", raw_text="Coin: BTC/USDT\nDirection: LONG\nEntry: 65000\nSL: 63000\nTP: 67000")

    results = ingest.process_pending_messages(use_ai_fallback=False)
    assert len(results) == 1
    assert results[0]["is_signal"] is True
    assert results[0]["position_id"] is not None

    positions = storage.list_external_positions(channel_id=cid)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTCUSDT"
    assert positions[0]["status"] == "open"


def test_processing_a_rejected_message_never_opens_a_position(monkeypatch):
    cid = channels.add_channel("TEST Channel", "@test")
    ingest.capture_message(cid, "text", raw_text="gm everyone hope you have a great day")

    results = ingest.process_pending_messages(use_ai_fallback=False)
    assert results[0]["is_signal"] is False
    assert "position_id" not in results[0]
    assert storage.list_external_positions(channel_id=cid) == []


def test_processing_checks_forwarding_eligibility_and_degrades_cleanly_when_unconfigured(monkeypatch):
    """Forwarding settings aren't configured in this test -- must report a
    clean 'not forwarded' reason, never crash the whole ingest pass."""
    cid = channels.add_channel("TEST Channel", "@test")
    ingest.capture_message(cid, "text", raw_text="Coin: BTC/USDT\nDirection: LONG\nEntry: 65000\nSL: 63000\nTP: 67000")

    results = ingest.process_pending_messages(use_ai_fallback=False)
    assert results[0]["forwarding"]["forwarded"] is False
    assert results[0]["forwarding"]["reason"]  # a real, non-empty reason


def test_a_message_with_no_stored_audio_is_marked_processed_with_a_clear_error():
    cid = channels.add_channel("TEST Channel", "@test")
    message_id = ingest.capture_message(cid, "voice", raw_media_bytes=None)  # no audio file at all

    results = ingest.process_pending_messages(use_ai_fallback=False)
    assert results[0]["is_signal"] is None
    assert results[0]["error"]
    msg = storage.list_external_messages(cid)[0]
    assert msg["processed"] == 1


def test_an_image_message_is_marked_processed_with_the_honest_ocr_unavailable_reason():
    cid = channels.add_channel("TEST Channel", "@test")
    ingest.capture_message(cid, "image", raw_media_bytes=b"\x89PNGfakeimagebytes")

    results = ingest.process_pending_messages(use_ai_fallback=False)
    assert results[0]["is_signal"] is None
    assert "not available" in results[0]["error"].lower() or "ocr" in results[0]["error"].lower()

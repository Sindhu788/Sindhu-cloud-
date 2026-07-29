"""Tests for Task 2's per-device single-active-session guard
(sindhu_web/session_guard.py). Deliberately scoped to "one active
connection per device" rather than "one active connection globally" --
the existing, already-verified "Connect from mobile (same WiFi)" feature
depends on a phone and the desktop dashboard staying connected
simultaneously, so a literal single-global-session rule would break it.
"""

import pytest

from sindhu_web import session_guard


@pytest.fixture(autouse=True)
def _reset_session_guard():
    session_guard._active.clear()
    yield
    session_guard._active.clear()


def test_claim_returns_none_for_first_connection_on_a_device():
    ws = object()
    assert session_guard.claim("device-1", ws) is None


def test_second_connection_on_same_device_evicts_first():
    ws1, ws2 = object(), object()
    session_guard.claim("device-1", ws1)
    evicted = session_guard.claim("device-1", ws2)
    assert evicted is ws1


def test_different_devices_do_not_evict_each_other():
    """This is the compromise that keeps the existing 'Connect from mobile'
    feature working: a phone and a desktop are different devices, so
    neither's connection closes the other's."""
    desktop_ws, phone_ws = object(), object()
    session_guard.claim("desktop-device", desktop_ws)
    evicted = session_guard.claim("phone-device", phone_ws)
    assert evicted is None


def test_release_only_clears_if_still_the_active_connection():
    ws1, ws2 = object(), object()
    session_guard.claim("device-2", ws1)
    session_guard.claim("device-2", ws2)  # ws1 evicted, ws2 now active
    session_guard.release("device-2", ws1)  # stale release from ws1's own cleanup -- must be a no-op
    evicted = session_guard.claim("device-2", object())
    assert evicted is ws2  # proves ws1's stale release did not clear ws2's slot


def test_release_clears_slot_when_still_active():
    ws = object()
    session_guard.claim("device-3", ws)
    session_guard.release("device-3", ws)
    evicted = session_guard.claim("device-3", object())
    assert evicted is None


def test_claim_with_no_device_id_is_a_noop():
    assert session_guard.claim(None, object()) is None
    assert session_guard.claim("", object()) is None

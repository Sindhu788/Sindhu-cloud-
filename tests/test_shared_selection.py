import pytest
from trading_intelligence.shared_wallet import SharedWallet
from trading_intelligence.shared_selection import active_session,fresh_selection


def setup(tmp_path):
    wallet=SharedWallet(tmp_path/"journal.db")
    old=wallet.create("preserved-old","a"*64)["session_id"]
    wallet.event(old,"saved-decision","no_trade",{"reason":"preserve"})
    with wallet.connect() as conn:
        conn.execute("CREATE TABLE shared_session_selections(sequence INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL UNIQUE REFERENCES shared_sessions(session_id),selected_at_utc TEXT NOT NULL)")
    return wallet,old


def test_new_session_is_zeroed_and_previous_journal_preserved(tmp_path):
    w,old=setup(tmp_path);before=w.snapshot(old)
    new=fresh_selection(w,expected_previous=old,name="fresh",archive_sha256="a"*64,postgres=False)
    assert new["cash"]==new["equity"]==100 and new["paused"]
    assert new["open_positions"]==new["closed_trades"]==0
    assert active_session(w,postgres=False)==new["session_id"]
    assert w.snapshot(old)==before
    assert SharedWallet(w.path).snapshot(new["session_id"])==new


def test_wrong_previous_or_archive_cannot_change_selection(tmp_path):
    w,old=setup(tmp_path)
    for previous,archive in [("unknown","a"*64),(old,"b"*64)]:
        with pytest.raises(ValueError):fresh_selection(w,expected_previous=previous,name="fresh",archive_sha256=archive,postgres=False)
    assert active_session(w,postgres=False)==old


def test_active_entries_block_handover(tmp_path):
    w,old=setup(tmp_path);w.event(old,"resume","control",{"paused":False})
    with pytest.raises(ValueError,match="Pause"):
        fresh_selection(w,expected_previous=old,name="fresh",archive_sha256="a"*64,postgres=False)
    assert active_session(w,postgres=False)==old

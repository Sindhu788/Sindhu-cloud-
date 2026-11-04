"""Append-only scan receipts. Reads never create or change a database table."""
from datetime import datetime, timezone
import uuid
import json


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_receipt(conn, receipt):
    # This additive table is created only when an explicitly enabled scanner runs.
    conn.execute('''CREATE TABLE IF NOT EXISTS paper_scan_log (
        id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT NOT NULL,
        kind TEXT NOT NULL, outcome TEXT NOT NULL, reason TEXT NOT NULL,
        coins_scanned INTEGER NOT NULL, candidates INTEGER NOT NULL,
        rejected INTEGER NOT NULL, accepted INTEGER NOT NULL,
        no_trade INTEGER NOT NULL, errors INTEGER NOT NULL, market_json TEXT NOT NULL)''')
    keys = ('started_at','completed_at','kind','outcome','reason','coins_scanned',
            'candidates','rejected','accepted','no_trade','errors')
    conn.execute('INSERT INTO paper_scan_log VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (uuid.uuid4().hex, *(receipt[k] for k in keys),json.dumps(receipt.get('market_data',[]))))


# --------------------------------------------------------------------------- live scan heartbeat (Day 3)
# A cold scan on the free plan can take many minutes and the instance can be stopped mid-scan. A receipt is written only when a
# scan ENDS, so an interrupted scan used to leave no trace at all. The heartbeat is ONE row that is updated while a scan runs
# (phase, coin i/N, seconds). On the next start an unfinished heartbeat is turned into an 'interrupted' receipt.
_HB_DDL = '''CREATE TABLE IF NOT EXISTS paper_scan_heartbeat (
    id TEXT PRIMARY KEY, scan_id TEXT NOT NULL, kind TEXT NOT NULL, started_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    phase TEXT NOT NULL, idx INTEGER NOT NULL, total INTEGER NOT NULL, symbol TEXT, coins_scanned INTEGER NOT NULL,
    errors INTEGER NOT NULL)'''
_IDLE = ('idle',)
_last_beat = {"t": 0.0, "phase": None}


def beat(conn, scan_id, kind, started_at, phase, idx=0, total=0, symbol=None, coins_scanned=0, errors=0, force=False, min_gap=5.0):
    """Upsert the single heartbeat row. Throttled (min_gap seconds) unless the phase changed or force=True. Never raises."""
    import time
    now = time.monotonic()
    if not force and phase == _last_beat["phase"] and now - _last_beat["t"] < min_gap:
        return False
    try:
        conn.execute(_HB_DDL)
        conn.execute('''INSERT INTO paper_scan_heartbeat (id, scan_id, kind, started_at, updated_at, phase, idx, total, symbol, coins_scanned, errors)
                        VALUES ('current', ?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT (id) DO UPDATE SET scan_id=excluded.scan_id, kind=excluded.kind, started_at=excluded.started_at,
                        updated_at=excluded.updated_at, phase=excluded.phase, idx=excluded.idx, total=excluded.total,
                        symbol=excluded.symbol, coins_scanned=excluded.coins_scanned, errors=excluded.errors''',
                     (scan_id, kind, started_at, utc_now(), phase, idx, total, symbol, coins_scanned, errors))
        _last_beat["t"], _last_beat["phase"] = now, phase
        return True
    except Exception:
        return False


def recover_interrupted(conn):
    """At process start: if the heartbeat says a scan never finished, record an 'interrupted' receipt (once) and mark it idle.
    Returns the receipt dict or None."""
    try:
        conn.execute(_HB_DDL)
        row = conn.execute("SELECT scan_id, kind, started_at, updated_at, phase, idx, total, symbol, coins_scanned, errors "
                           "FROM paper_scan_heartbeat WHERE id='current'").fetchone()
    except Exception:
        return None
    if not row or row[4] in _IDLE:
        return None
    sid, kind, started, updated, phase, idx, total, symbol, coins, errors = row
    receipt = dict(started_at=started, completed_at=updated, kind=kind, outcome='interrupted',
                   reason=f"Process stopped mid-scan (phase {phase}, coin {idx}/{total}{' ' + symbol if symbol else ''}); "
                          f"the free instance was stopped, slept or redeployed.",
                   coins_scanned=int(coins or 0), candidates=0, rejected=0, accepted=0, no_trade=0, errors=int(errors or 0))
    try:
        write_receipt(conn, receipt)
        conn.execute("UPDATE paper_scan_heartbeat SET phase='idle', updated_at=? WHERE id='current'", (utc_now(),))
    except Exception:
        return None
    return receipt

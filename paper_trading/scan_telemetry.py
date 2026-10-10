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

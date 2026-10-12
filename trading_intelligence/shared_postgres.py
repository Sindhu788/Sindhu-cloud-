"""PostgreSQL transport for the same costed journal; never initializes schema.

DDL is an explicit reviewed migration. A transaction-scoped advisory lock
serializes wallet writes before any balances are read, across worker processes.
"""
from contextlib import contextmanager
from trading_intelligence.shared_wallet import SharedWallet

LOCK_KEY = 1397313096


class Cursor:
    def __init__(self, cursor): self.cursor = cursor
    def fetchone(self): return self.cursor.fetchone()
    def __iter__(self): return iter(self.cursor)


class Connection:
    def __init__(self, raw): self.raw = raw
    def execute(self, sql, params=()):
        cursor=self.raw.cursor()
        cursor.execute(sql.replace('?', '%s'), params)
        return Cursor(cursor)


class PostgresSharedWallet(SharedWallet):
    def __init__(self, connection_factory):
        # The caller provides an existing authorized driver connection factory.
        # No DSN is stored in wallet objects, receipts or exception messages.
        self.connection_factory=connection_factory

    @contextmanager
    def connect(self):
        raw=self.connection_factory()
        try:
            with raw:
                yield Connection(raw)
        finally:
            raw.close()

    def _begin(self, conn):
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute('SELECT pg_advisory_xact_lock(?)', (LOCK_KEY,))


def configured_wallet():
    import os
    import psycopg2
    def connection():
        return psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=10)
    return PostgresSharedWallet(connection)


def local_wallet(root):
    """An explicit, validated handover marker selects the shared PG journal."""
    import json
    from pathlib import Path
    marker=Path(root)/'backend.json'
    if not marker.exists():return SharedWallet(Path(root)/'wallet.db',initialize=False)
    settings=json.loads(marker.read_text())
    if settings.get('backend')!='postgres' or settings.get('branch_id')!='br-fancy-paper-b5r2ys6l':
        raise ValueError('Unapproved shared backend marker')
    import psycopg2
    def connection():
        data=json.loads(Path('D:/sindhu/data/config/neon_runtime_connection.json').read_text())
        return psycopg2.connect(data['database_url'],connect_timeout=10)
    wallet=PostgresSharedWallet(connection)
    from trading_intelligence.shared_selection import active_session
    if active_session(wallet,postgres=True)!=settings['session_id']:
        raise ValueError('Shared backend session identity differs')
    return wallet

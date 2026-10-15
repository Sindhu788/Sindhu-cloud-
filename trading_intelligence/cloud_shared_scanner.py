"""Explicit opt-in Cloud subprocess; no legacy engines or external delivery."""
import json
import os
from pathlib import Path
import subprocess
import sys

_process = None
WORKER_LOCK = 1397313097


def cloud_wallet():
    from trading_intelligence.shared_postgres import configured_wallet
    from trading_intelligence.shared_selection import active_session
    wallet = configured_wallet()
    lock = wallet.connection_factory()
    cursor = lock.cursor()
    # Keep the transaction open: safe with transaction-pooling endpoints too.
    cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', (WORKER_LOCK,))
    if not cursor.fetchone()[0]:
        lock.close()
        raise RuntimeError('Another Cloud scanner owns this journal')
    try:
        ident = active_session(wallet, postgres=True)
        if wallet.snapshot(ident)['initial_balance'] != 100:
            raise ValueError('Verified shared $100 wallet required')
        return wallet, ident, lock
    except Exception:
        lock.close()
        raise


def start():
    global _process
    if os.environ.get('SINDHU_SHARED_PAPER_ENABLED') != '1':
        raise ValueError('Cloud paper activation is disabled')
    if not os.environ.get('DATABASE_URL') or os.environ.get('SINDHU_TELEGRAM_DRY_RUN') != '1' or os.environ.get('SINDHU_PUBLIC_SIGNAL_OWNER') != 'disabled':
        raise ValueError('PostgreSQL and disabled external delivery required')
    if _process is not None and _process.poll() is None:
        return
    root = Path(__file__).resolve().parents[1]
    _process = subprocess.Popen([sys.executable, str(root/'scripts/run_shared_paper.py'), '--cloud', '--cycles', '0'], cwd=root, env=dict(os.environ))


def stop():
    global _process
    if _process is not None and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _process.kill()
            _process.wait(timeout=5)
    _process = None


def status():
    from data_engine.paths import DATA_DIR
    running = _process is not None and _process.poll() is None
    receipt = {}
    if running:
        try:
            receipt = json.loads((Path(DATA_DIR)/'shared_paper/scanner_state.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return {'running': running, 'state': receipt.get('state', 'STARTING') if running else 'NOT_ACTIVATED' if _process is None else 'STOPPED',
            'last_successful_scan_utc': receipt.get('last_successful_scan_utc'),
            'cycles_completed': receipt.get('cycles_completed', 0),
            'evaluated_symbols': receipt.get('evaluated_symbols', []),
            'evaluated_timeframes': receipt.get('evaluated_timeframes', []),
            'selected_versions': receipt.get('selected_versions', {}),
            'strategy_ids': receipt.get('strategy_ids', []),
            'standalone_lessons': 'NOT EXECUTABLE', 'public_delivery': False, 'real_orders': 0}

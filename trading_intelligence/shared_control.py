"""Use the existing dashboard controls for the one approved shared wallet."""
import os
import uuid


def enabled():
    return os.environ.get('SINDHU_SHARED_PAPER_ENABLED') == '1'


def account_status(snapshot, worker, *, dry_run=False):
    daily=snapshot['daily_utc']
    return {'account_mode':'shared_wallet', 'session_id':snapshot['session_id'],
            'balance':snapshot['equity'], 'cash':snapshot['cash'],
            'initial_balance':snapshot['initial_balance'],
            'running':bool(worker['running'] and worker['state']=='RUNNING' and not snapshot['paused']),
            'worker_running':worker['running'], 'scanner_state':worker['state'],
            'entries_paused':snapshot['paused'], 'safe_start':False,
            'dry_run':dry_run, 'paper_only':True, 'real_orders':0,
            'started_at':snapshot['created_at'],
            'last_tick_at':worker.get('last_successful_scan_utc'), 'next_tick_at':None,
            'last_tick_duration_seconds':None, 'scan_progress':{},
            'tick_count':worker.get('cycles_completed',0),
            'trades_today':daily['accepted'], 'signals_sent_today':daily['delivery_success'],
            'open_trades':snapshot['open_positions'], 'closed_trades':snapshot['closed_trades'],
            'realized_pnl':snapshot['realized_pnl'], 'win_rate_pct':snapshot['win_rate_pct'],
            'queue':0, 'last_summary':{'shortlisted':worker.get('evaluated_symbols',[])},
            'per_strategy':[]}


def status():
    from sindhu_web.api.intelligence import _postgres_shared_wallet
    from trading_intelligence import cloud_shared_scanner
    from paper_trading import config
    wallet,ident=_postgres_shared_wallet()
    return account_status(wallet.snapshot(ident),cloud_shared_scanner.status(),dry_run=config.load().get('dry_run',True))


def control(operation):
    from paper_trading import kill_switch
    from data_engine import feature_toggles
    from sindhu_web.api.intelligence import _postgres_shared_wallet
    from trading_intelligence import cloud_shared_scanner
    if operation not in ('start','stop'):
        raise ValueError('Unknown shared paper operation')
    if operation=='start' and (kill_switch.is_active() or feature_toggles.is_master_paused()):
        raise ValueError('Kill switch or master pause active; safeguards preserved')
    wallet,ident=_postgres_shared_wallet()
    if operation=='start':
        cloud_shared_scanner.start()
    # Stop pauses new entries. The child continues protective monitoring.
    wallet.event(ident,'dashboard-'+operation+'-'+uuid.uuid4().hex,'control',{'paused':operation=='stop'})
    return {'ok':True,'account_mode':'shared_wallet','entries_paused':operation=='stop'}

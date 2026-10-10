"""Read-only operations views shared by Main and Cloud; never fetch market data."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from data_engine import storage, db_backend

router = APIRouter()
STATIC = Path(__file__).resolve().parents[1] / 'static'


def safe_text(value):
    text = str(value or '')
    text = re.sub(r'\b(?:postgres(?:ql)?|https?)://\S+', '[URL redacted]', text, flags=re.I)
    text = re.sub(r'\b\d{6,}:[A-Za-z0-9_-]{15,}\b', '[token redacted]', text)
    text = re.sub(r'(?i)(password|secret|token|api[_-]?key)\s*[=:]\s*[^\s,;]+', r'\1=[redacted]', text)
    return text[:400]


def tables(conn):
    sql = ("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
           if db_backend.IS_POSTGRES else "SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in conn.execute(sql).fetchall()}


def setting(conn, present, key, filename):
    if db_backend.IS_POSTGRES:
        if 'cloud_settings' not in present:
            return {}
        row = conn.execute('SELECT value_json FROM cloud_settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else {}
    from data_engine.paths import CONFIG_DIR
    path = Path(CONFIG_DIR) / filename
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


@router.get('/control-room')
@router.get('/preview')
def control_room():
    html = (STATIC / 'control_room.html').read_text(encoding='utf-8')
    for asset in ('js/control_room.js', 'css/control_room.css'):
        version = (STATIC / asset).stat().st_mtime_ns
        html = html.replace(f'/static/{asset}"', f'/static/{asset}?v={version}"')
    return HTMLResponse(html, headers={'Cache-Control': 'no-store'})


@router.get('/api/quality/preview')
def preview():
    # Public guest view has no database connection and no private measurements.
    return {'mode': 'guest', 'data_label': 'preview', 'private_data_available': False,
            'message': 'Read-only layout preview. Sign in for measured data and protected controls.'}


def build_diagnostics(conn, now=None):
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=24)).isoformat()
    present = tables(conn)
    cfg = setting(conn, present, 'paper_trading_settings', 'paper_trading_settings.json')
    from paper_trading.engine import engine
    safe_start = os.environ.get('SINDHU_SAFE_START') == '1'
    running = engine.is_running()
    blockers = []
    if safe_start:
        blockers.append('Safe startup disables background scanning and delivery.')
    if not cfg.get('engine_enabled', False):
        blockers.append('Saved engine_enabled is false; restart will not resume the scanner.')
    if not running:
        blockers.append('Scanner worker is stopped in this process.')
    if cfg.get('dry_run', True):
        blockers.append('Paper engine dry_run is enabled; candidates cannot open paper positions.')
    tg_dry = os.environ.get('SINDHU_TELEGRAM_DRY_RUN') == '1'
    if tg_dry:
        blockers.append('Telegram dry-run blocks network delivery.')
    owner = os.environ.get('SINDHU_PUBLIC_SIGNAL_OWNER', 'cloud')
    if owner not in ('main', 'cloud'):
        blockers.append('Public signal publisher is disabled.')
    counts = {'saved_decisions': None, 'rejected': None, 'accepted': None, 'no_trade': None,
              'scans': None, 'coins_scanned': None, 'candidates': None}
    latest = None
    reasons = []
    if 'paper_decision_log' in present:
        rows = conn.execute('SELECT decision,count(*) FROM paper_decision_log WHERE created_at>=? GROUP BY decision', (since,)).fetchall()
        grouped = dict(rows)
        counts.update(saved_decisions=sum(grouped.values()), rejected=grouped.get('rejected', 0),
                      accepted=grouped.get('opened', 0)+grouped.get('dry_run', 0), no_trade=grouped.get('no_trade', 0))
        latest = conn.execute('SELECT max(created_at) FROM paper_decision_log').fetchone()[0]
        reasons = [{'reason': safe_text(r), 'count': n} for r, n in conn.execute(
            "SELECT reason,count(*) AS n FROM paper_decision_log WHERE created_at>=? AND decision IN ('rejected','no_trade') GROUP BY reason ORDER BY n DESC LIMIT 8", (since,)).fetchall()]
    coverage = 'NOT INSTRUMENTED: decision rows cannot establish scan or candidate counts.'
    last_success = None
    market_data={'freshness':None,'status':'UNAVAILABLE: no persisted live candle receipt; archives are not live prices.'}
    if 'paper_scan_log' in present:
        row = conn.execute('SELECT count(*),sum(coins_scanned),sum(candidates),min(started_at) FROM paper_scan_log WHERE started_at>=?', (since,)).fetchone()
        counts.update(scans=row[0], coins_scanned=row[1] or 0, candidates=row[2] or 0)
        coverage = 'Available receipts only; collection starts at first instrumented scan. No pre-upgrade scan counts inferred.'
        last_success = conn.execute("SELECT max(completed_at) FROM paper_scan_log WHERE outcome='complete'").fetchone()[0]
        row=conn.execute("SELECT market_json FROM paper_scan_log WHERE market_json<>'[]' ORDER BY completed_at DESC LIMIT 1").fetchone()
        if row:
            receipts=json.loads(row[0])
            now_ms=int(now.timestamp()*1000)
            stale=sum(now_ms-r['last_closed_at_ms']>r['period_ms'] for r in receipts)
            market_data={'freshness':'stale' if stale else 'recent_at_last_scan',
                         'status':f'Last scan recorded {len(receipts)} candle receipts; {stale} are now stale. This is scanner evidence, not a live price feed.'}
    notifications = {'attempts': None, 'delivered': None, 'errors': None, 'by_type': []}
    if 'telegram_message_log' in present:
        rows = conn.execute('SELECT trigger_type,success,count(*) FROM telegram_message_log WHERE sent_at>=? GROUP BY trigger_type,success', (since,)).fetchall()
        notifications = {'attempts': sum(r[2] for r in rows), 'delivered': sum(r[2] for r in rows if r[1]==1),
                         'errors': sum(r[2] for r in rows if r[1]!=1),
                         'by_type': [{'type': safe_text(t), 'success': bool(s), 'count': n} for t,s,n in rows]}
    enabled = conn.execute('SELECT count(*) FROM paper_strategy_config WHERE enabled=1').fetchone()[0] if 'paper_strategy_config' in present else None
    if enabled == 0:
        blockers.append('No strategy is enabled for paper trading.')
    kill = conn.execute('SELECT active FROM kill_switch_state LIMIT 1').fetchone() if 'kill_switch_state' in present else None
    if kill and kill[0]:
        blockers.append('Kill switch is active.')
    # Load only configuration presence flags; no credential value leaves this function.
    tg = setting(conn, present, 'telegram_settings', 'telegram_settings.json')
    return {'as_of_utc': now.isoformat(), 'window_start_utc': since, 'window': 'rolling 24 hours UTC',
            'mode': 'cloud' if os.environ.get('SINDHU_CLOUD_MODE')=='1' else 'main',
            'database': {'connected': conn.execute('SELECT 1').fetchone()[0]==1,
                         'backend': 'postgresql' if db_backend.IS_POSTGRES else 'sqlite'},
            'scanner': {'running': running, 'engine_enabled': cfg.get('engine_enabled', False),
                        'safe_start': safe_start, 'last_successful_scan': last_success,
                        'last_tick_this_process': engine._last_tick_at, 'enabled_strategies': enabled},
            'counts': counts, 'telemetry_coverage': coverage, 'latest_saved_decision': latest,
            'blockers': blockers, 'top_rejections': reasons, 'notifications': notifications,
            'telegram': {'dry_run': tg_dry, 'master_send_enabled': bool(tg.get('master_send_enabled', True)),
                         'token_present': bool(tg.get('bot_token') or os.environ.get('TELEGRAM_BOT_TOKEN')),
                         'private_target_present': bool(tg.get('personal_chat_id')),
                         'public_owner': owner if owner in ('main','cloud') else 'disabled'},
            'market_data':market_data,
            'risk': {k: cfg.get(k) for k in ('cooldown_minutes','max_open_trades','max_open_positions_per_coin','risk_pct_default')},
            'no_trade_policy': 'Preserve conservative entry, freshness, risk and duplicate gates. No thresholds lowered.'}


@router.get('/api/quality/diagnostics')
def diagnostics():
    try:
        with storage.get_conn() as conn:
            return build_diagnostics(conn)
    except Exception:
        raise HTTPException(503, 'Operational measurements unavailable; no values inferred.') from None


@router.get('/api/quality/journal')
def journal(limit: int = Query(50, ge=1, le=100)):
    with storage.get_conn() as conn:
        rows = conn.execute('SELECT created_at,symbol,strategy_name,decision,reason,confidence FROM paper_decision_log ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    keys = ('at_utc','symbol','strategy','decision','reason','confidence')
    return {'entries': [dict(zip(keys, [safe_text(v) if i<5 else v for i,v in enumerate(r)])) for r in rows]}


@router.get('/api/quality/strategies')
@router.get('/api/paper-trading/catalog/strategies')
def strategies():
    from trading_intelligence.catalog import strategy_library
    return {'strategies': strategy_library(), 'automatic_promotion': False}


@router.get('/api/paper-trading/catalog/lessons')
def lessons():
    # Lightweight catalog used by paper trading on both runners.
    return {'lessons': storage.list_lessons(status='active')}

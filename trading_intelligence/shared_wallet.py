"""One append-only, restart-safe educational cash wallet across all strategies.

This ledger has no exchange order or Telegram client. Legacy tables are never
read or changed. Decisions must pass the scanner's existing safety gates before
being submitted here; wallet checks are an additional layer, not a replacement.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
import sqlite3
import uuid


def number(value):
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError('Non-finite accounting input')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


class SharedWallet:
    """Dedicated SQLite journal. Every write takes the wallet's database lock."""
    def __init__(self, path, *, initialize=True):
        self.path = str(path)
        if not initialize:
            from pathlib import Path
            if not Path(path).is_file():
                raise ValueError('Shared wallet database is not initialized')
            return
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS shared_sessions(
                    session_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL, data_label TEXT NOT NULL,
                    archive_sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS shared_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES shared_sessions(session_id),
                    event_id TEXT NOT NULL, at_utc TEXT NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(session_id,event_id));
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            with conn:
                yield conn
        finally:
            conn.close()

    def _begin(self, conn):
        conn.execute('BEGIN IMMEDIATE')

    def create(self, name, archive_sha256, data_label='live'):
        if data_label not in ('live', 'synthetic') or not name:
            raise ValueError('Explicit wallet identity and data label required')
        if len(archive_sha256) != 64 or any(c not in '0123456789abcdef' for c in archive_sha256):
            raise ValueError('Verified archive SHA-256 required')
        with self.connect() as conn:
            self._begin(conn)
            row = conn.execute('SELECT session_id,archive_sha256,data_label FROM shared_sessions WHERE name=?', (name,)).fetchone()
            if row:
                if row[1:] != (archive_sha256, data_label):
                    raise ValueError('Existing wallet identity differs; no overwrite allowed')
                ident = row[0]
            else:
                ident = 'paper-' + uuid.uuid4().hex
                conn.execute('INSERT INTO shared_sessions VALUES (?,?,?,?,?)', (ident, name, now(), data_label, archive_sha256))
        return self.snapshot(ident)

    def _load(self, conn, ident):
        row = conn.execute('SELECT created_at,data_label,archive_sha256 FROM shared_sessions WHERE session_id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Shared session not found')
        state = dict(session_id=ident, created_at=row[0], data_label=row[1], archive_sha256=row[2],
                     cash=Decimal(100), positions={}, closed=[], paused=True, marks={}, events=[], equity_curve=[Decimal(100)])
        for seq, at, kind, raw in conn.execute('SELECT sequence,at_utc,kind,payload FROM shared_events WHERE session_id=? ORDER BY sequence', (ident,)):
            p = json.loads(raw)
            if kind == 'open':
                state['cash'] -= number(p['cost']) + number(p['entry_fee'])
                state['positions'][p['position_id']] = p
                state['marks'][p['symbol']] = p['entry_price']
            elif kind == 'close':
                entry = state['positions'].pop(p['position_id'])
                state['cash'] += number(p['proceeds']) - number(p['exit_fee'])
                state['closed'].append({**entry, **p, 'closed_at': at})
            elif kind == 'mark':
                state['marks'].update(p['prices'])
            elif kind == 'control':
                state['paused'] = p['paused']
            state['events'].append((at, kind, p))
            state['equity_curve'].append(self._equity(state))
        return state

    @staticmethod
    def _equity(s):
        return s['cash'] + sum(number(p['quantity']) * number(s['marks'][p['symbol']]) for p in s['positions'].values())

    @staticmethod
    def _append(conn, ident, event_id, kind, payload, at=None):
        if not event_id:
            raise ValueError('Idempotency key required')
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        prior = conn.execute('SELECT kind,payload FROM shared_events WHERE session_id=? AND event_id=?', (ident, event_id)).fetchone()
        if prior:
            if prior != (kind, encoded):
                raise ValueError('Idempotency key reused with different content')
            return False
        conn.execute('INSERT INTO shared_events(session_id,event_id,at_utc,kind,payload) VALUES (?,?,?,?,?)', (ident, event_id, at or now(), kind, encoded))
        return True

    def event(self, ident, event_id, kind, payload):
        if kind not in ('scan', 'candidate', 'rejection', 'no_trade', 'delivery', 'control', 'mark', 'notification_queued'):
            raise ValueError('Unsupported external journal event')
        if kind == 'control' and (set(payload) != {'paused'} or type(payload['paused']) is not bool):
            raise ValueError('Explicit paused boolean required')
        if kind == 'mark':
            if set(payload) != {'prices'} or not isinstance(payload['prices'], dict):
                raise ValueError('Explicit prices required')
            if any(number(v) <= 0 for v in payload['prices'].values()):
                raise ValueError('Positive mark prices required')
        with self.connect() as conn:
            self._begin(conn)
            self._load(conn, ident)
            self._append(conn, ident, event_id, kind, payload)
        return self.snapshot(ident)

    def open(self, ident, event_id, *, position_id, strategy_id, symbol, price, stop, target,
             quantity, gates_passed, fee_bps=10, slippage_bps=5, spread_bps=3, entered_at_ms=None):
        """Spot long/flat only; an explicit fully specified candidate is required."""
        values = [number(v) for v in (price, stop, target, quantity, fee_bps, slippage_bps, spread_bps)]
        price, stop, target, quantity, fee, slip, spread = values
        if not all((position_id, strategy_id, symbol)) or min(price, stop, target, quantity) <= 0 or min(fee, slip, spread) < 0:
            raise ValueError('Invalid position or cost inputs')
        fill = price * (1 + (slip + spread) / 10000)
        if not stop < fill < target or (target-fill)/(fill-stop) < 2:
            raise ValueError('Invalid protective plan or planned RR below 2')
        cost = fill * quantity
        entry_fee = cost * fee / 10000
        stop_fill = stop * (1 - (slip + spread) / 10000)
        risk = (fill-stop_fill)*quantity + entry_fee + stop_fill*quantity*fee/10000
        p = dict(position_id=position_id, strategy_id=strategy_id, symbol=symbol,
                 entry_price=str(fill), stop=str(stop), target=str(target), quantity=str(quantity),
                 cost=str(cost), entry_fee=str(entry_fee), risk=str(risk), planned_rr=str((target-fill)/(fill-stop)),
                 fee_bps=str(fee), slippage_bps=str(slip), spread_bps=str(spread))
        p['entered_at_ms']=entered_at_ms
        with self.connect() as conn:
            self._begin(conn)
            s = self._load(conn, ident)
            prior = conn.execute('SELECT 1 FROM shared_events WHERE session_id=? AND event_id=?', (ident, event_id)).fetchone()
            if prior:
                self._append(conn, ident, event_id, 'open', p)
                return self._snapshot(s)
            if s['paused'] or gates_passed is not True:
                raise ValueError('Paused wallet or upstream safety gates not passed')
            if position_id in s['positions'] or any(x['position_id'] == position_id for x in s['closed']):
                raise ValueError('Duplicate position')
            if any(x['symbol'] == symbol for x in s['positions'].values()):
                raise ValueError('Symbol conflict or duplicate across strategies')
            equity = self._equity(s)
            peak = max(s['equity_curve'])
            today = now()[:10]
            daily_pnl = sum(number(x['pnl']) for x in s['closed'] if x['closed_at'].startswith(today))
            if daily_pnl <= -3 or equity <= peak * Decimal('.9'):
                raise ValueError('Daily loss or drawdown circuit breaker')
            if len(s['positions']) >= 5 or cost+entry_fee > s['cash']:
                raise ValueError('Shared wallet exposure or cash cap')
            if risk > equity * Decimal('.01') or sum(number(x['risk']) for x in s['positions'].values()) + risk > equity * Decimal('.03'):
                raise ValueError('Shared wallet risk cap')
            self._append(conn, ident, event_id, 'open', p)
        return self.snapshot(ident)

    def close(self, ident, event_id, position_id, price, reason):
        price = number(price)
        if price <= 0 or not reason:
            raise ValueError('Positive exit price and explicit reason required')
        with self.connect() as conn:
            self._begin(conn)
            s = self._load(conn, ident)
            prior = conn.execute('SELECT payload FROM shared_events WHERE session_id=? AND event_id=? AND kind=?', (ident, event_id, 'close')).fetchone()
            if prior:
                p = json.loads(prior[0])
                if p['position_id'] != position_id or p['quoted_exit'] != str(price) or p['reason'] != reason:
                    raise ValueError('Different close under existing idempotency key')
                return self._snapshot(s)
            entry = s['positions'].get(position_id)
            if not entry:
                raise ValueError('Open position not found')
            fill = price * (1-(number(entry['slippage_bps'])+number(entry['spread_bps']))/10000)
            proceeds = fill * number(entry['quantity'])
            fee = proceeds * number(entry['fee_bps']) / 10000
            pnl = proceeds-fee-number(entry['cost'])-number(entry['entry_fee'])
            self._append(conn, ident, event_id, 'close', dict(position_id=position_id, quoted_exit=str(price),
                         exit_price=str(fill), proceeds=str(proceeds), exit_fee=str(fee), pnl=str(pnl), reason=reason))
        return self.snapshot(ident)

    def snapshot(self, ident):
        with self.connect() as conn:
            return self._snapshot(self._load(conn, ident))

    def _snapshot(self, s):
        closed = s['closed']
        pnl = sum(number(x['pnl']) for x in closed)
        equity = self._equity(s)
        today = now()[:10]
        day_start = Decimal(100)
        for i, (at, kind, p) in enumerate(s['events']):
            if at[:10] < today:
                day_start = s['equity_curve'][i+1]
        wins = sum(number(x['pnl']) > 0 for x in closed)
        losses = sum(number(x['pnl']) < 0 for x in closed)
        peak = Decimal(100)
        dd = Decimal(0)
        for equity in s['equity_curve']:
            peak = max(peak, equity)
            dd = max(dd, (peak-equity)/peak*100)
        def totals(day=None):
            events = [(kind,p) for at,kind,p in s['events'] if day is None or at.startswith(day)]
            counts = Counter(kind for kind,p in events)
            trades = [x for x in closed if day is None or x['closed_at'].startswith(day)]
            return {'scans_completed':sum(kind=='scan' and p.get('success') is True for kind,p in events),
                    'candidates':counts['candidate'], 'accepted':counts['open'], 'no_trade':counts['no_trade'],
                    'rejected':counts['rejection'], 'rejection_reasons':dict(Counter(p.get('reason','unspecified') for kind,p in events if kind=='rejection')),
                    'delivery_success':sum(kind=='delivery' and p.get('status')=='sent' for kind,p in events),
                    'delivery_failure':sum(kind=='delivery' and p.get('status')=='failed' for kind,p in events),
                    'closed_trades':len(trades),'wins':sum(number(x['pnl'])>0 for x in trades),
                    'losses':sum(number(x['pnl'])<0 for x in trades),
                    'starting_equity':float(day_start) if day else 100.0,
                    'current_equity':float(equity),
                    'realized_pnl':float(sum(number(x['pnl']) for x in trades)),
                    'net_pnl':float(equity-(day_start if day else Decimal(100)))}
        gross_win = sum(number(x['pnl']) for x in closed if number(x['pnl'])>0)
        gross_loss = -sum(number(x['pnl']) for x in closed if number(x['pnl'])<0)
        scans = [(at,p) for at,kind,p in s['events'] if kind=='scan']
        return dict(session_id=s['session_id'], created_at=s['created_at'], data_label=s['data_label'],
                    archive_sha256=s['archive_sha256'], initial_balance=100.0, cash=float(s['cash']), equity=float(self._equity(s)),
                    open_positions=len(s['positions']), closed_trades=len(closed), wins=wins, losses=losses,
                    net_pnl=float(equity-100), realized_pnl=float(pnl),
                    unrealized_pnl=float(equity-100-pnl),
                    win_rate_pct=100*wins/len(closed) if closed else None,
                    profit_factor=float(gross_win/gross_loss) if len(closed)>=30 and gross_loss else None,
                    realized_average_r=float(sum(number(x['pnl'])/number(x['risk']) for x in closed)/len(closed)) if len(closed)>=30 else None,
                    expectancy=float(pnl/len(closed)) if closed else None, max_drawdown_pct=float(dd), paused=s['paused'],
                    daily_utc=totals(now()[:10]), lifetime=totals(), last_scan=scans[-1] if scans else None,
                    positions=list(s['positions'].values()), real_money=False, network_orders=0,
                    cost_assumptions={'fee_bps_per_side':10,'slippage_bps_per_side':5,'spread_bps_per_side':3},
                    warning='Educational spot simulation; PF/average R require 30 closes. Historical trades excluded.')

"""Additional shared-wallet checks after the existing paper approval chain.

No new strategy rules, public messages or real exchange orders are introduced.
Only the explicitly constructed local review engine installs this adapter.
"""
from datetime import datetime, timezone
import hashlib

from trading_intelligence.shared_wallet import number


class SharedExecution:
    def __init__(self, wallet, session_id, engine, quote_provider=None):
        self.wallet, self.session_id, self.engine = wallet, session_id, engine
        self.quote_provider=quote_provider

    def __call__(self, book, exchange, symbol, pick, snapshot, settings, upstream_size, upstream_risk):
        from data_engine.config import env_flag
        if env_flag('SINDHU_SAFE_START'):
            raise ValueError('Safe startup blocks shared execution')
        state=self.wallet.snapshot(self.session_id)
        # Symbol lock, cash/risk caps and sequential event dedup are shared
        # across every participating strategy, even after process restart.
        candle=snapshot.get('candle_receipt') or {}
        closed_at=candle.get('last_closed_at_ms')
        if closed_at is None:
            self.engine._log_decision(exchange,symbol,pick,'rejected','Shared execution requires verified closed-candle receipt.',snapshot)
            return 0,1
        from trading_intelligence.research import INTERVALS
        period=INTERVALS.get(pick.get('timeframe'))
        if not period:return 0,1
        signal_closed_at=closed_at//period*period
        identity='|'.join(map(str,(self.session_id,book,pick.get('strategy_version'),symbol,signal_closed_at,pick.get('direction'))))
        ident=hashlib.sha256(identity.encode()).hexdigest()
        try:
            if pick.get('direction')!='bullish':
                raise ValueError('Shared educational wallet is spot long/flat; short execution unsupported')
            if pick.get('stop_loss') is None or pick.get('take_profit') is None:
                raise ValueError('Explicit protective stop and target required')
            if self.quote_provider is None:
                raise ValueError('Fresh observed spot quote unavailable')
            price,observed_at=self.quote_provider(symbol)
            current_ms=int(datetime.now(timezone.utc).timestamp()*1000)
            if not 0<=current_ms-observed_at<=15000:
                raise ValueError('Stale or future entry quote')
            price=number(price);stop=number(pick['stop_loss'])
            fill=price*number('1.0008');stop_fill=stop*number('.9992')
            per_unit=fill-stop_fill+(fill+stop_fill)*number('.001')
            if per_unit<=0:raise ValueError('Invalid loss budget')
            size=min(number(upstream_size),number(state['equity'])*number('.01')/per_unit,
                     number(state['cash'])/(fill*number('1.001')))
            # Preserve configured cooldown, additionally scoped to the new
            # journal rather than relying on legacy historical close rows.
            with self.wallet.connect() as conn:
                prior=conn.execute('SELECT 1 FROM shared_events WHERE session_id=? AND event_id=?',(self.session_id,ident)).fetchone()
                if prior:return 0,0
                ledger=self.wallet._load(conn,self.session_id)
                cooldown=settings.get('cooldown_minutes',15)*60
                for trade in ledger['closed']:
                    if trade['symbol']==symbol and (datetime.now(timezone.utc)-datetime.fromisoformat(trade['closed_at'])).total_seconds()<cooldown:
                        raise ValueError('Shared wallet symbol cooldown active')
            self.wallet.open(self.session_id,ident,position_id=ident,strategy_id=book,symbol=symbol,
                             price=price,stop=stop,target=pick['take_profit'],quantity=size,gates_passed=True,
                             entered_at_ms=current_ms)
            # Deliberately queued/unsent: the owner approved one private test,
            # not an automatic stream of messages to any public destination.
            self.wallet.event(self.session_id,ident+'-notification','notification_queued',
                              {'position_id':ident,'private_only':True,'status':'awaiting_private_verification'})
            self.engine._log_decision(exchange,symbol,pick,'opened','Shared educational wallet position opened.',snapshot)
            return 1,0
        except ValueError as exc:
            self.engine._log_decision(exchange,symbol,pick,'rejected',str(exc),snapshot)
            return 0,1

    def monitor(self, symbol, frame, receipt):
        """Stops first if a closed candle touches both protective boundaries."""
        state=self.wallet.snapshot(self.session_id)
        for p in state['positions']:
            if p['symbol']!=symbol:continue
            stop=number(p['stop']);target=number(p['target'])
            entered=p.get('entered_at_ms')
            if entered is None:raise ValueError('Position entry timestamp missing')
            for at,row in frame.iterrows():
                opened=int(at.timestamp()*1000);closed=opened+receipt['period_ms']
                if closed<=entered:continue
                low=number(row['low']);high=number(row['high'])
                # Conservative ambiguity: an entry-bar stop may be treated
                # as hit; never award a target from before the entry time.
                stop_hit=low<=stop
                target_hit=opened>=entered and high>=target
                if stop_hit or target_hit:
                    price=min(stop,number(row['open'])) if stop_hit and opened>=entered else stop if stop_hit else target
                    key=p['position_id']+'-exit-'+str(closed)
                    self.wallet.close(self.session_id,key,p['position_id'],price,'stop' if stop_hit else 'target')
                    break
        self.wallet.event(self.session_id,'mark-'+symbol+'-'+str(receipt['last_closed_at_ms']),
                          'mark',{'prices':{symbol:str(frame.iloc[-1]['close'])}})

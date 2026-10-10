"""Pure virtual accounting and dry-run delivery; no broker/network integration."""
import hashlib
import json
from html import escape
import math


class VirtualLedger:
    def __init__(self,session_id,initial_balance,*,data_label):
        if not session_id or session_id=='legacy' or data_label not in ('synthetic','historical','live') or not math.isfinite(initial_balance) or initial_balance<=0:
            raise ValueError('An isolated session, data label and positive virtual balance are required')
        self.session_id=session_id;self.initial_balance=initial_balance;self.balance=initial_balance
        self.data_label=data_label;self.positions={};self.closed=[]

    def open(self,position_id,price,quantity,*,reason,fee_bps=10):
        if position_id in self.positions or any(p['id']==position_id for p in self.closed):raise ValueError('Duplicate position id')
        if not reason or not all(math.isfinite(x) for x in (price,quantity,fee_bps)) or min(price,quantity)<=0 or fee_bps<0:raise ValueError('Invalid virtual entry')
        cost=price*quantity;fee=cost*fee_bps/10000
        if cost+fee>self.balance:raise ValueError('Insufficient virtual cash')
        self.balance-=cost+fee
        self.positions[position_id]={'id':position_id,'session_id':self.session_id,'entry_price':price,'quantity':quantity,'cost':cost,'entry_fee':fee,'reason':reason,'data_label':self.data_label}

    def close(self,position_id,price,*,fee_bps=10):
        if not all(math.isfinite(x) for x in (price,fee_bps)) or price<=0 or fee_bps<0:raise ValueError('Invalid virtual exit')
        p=self.positions.pop(position_id);proceeds=p['quantity']*price;fee=proceeds*fee_bps/10000
        self.balance+=proceeds-fee
        p.update(exit_price=price,exit_fee=fee,pnl=proceeds-fee-p['cost']-p['entry_fee']);self.closed.append(p)
        return dict(p)

    def snapshot(self):
        return {'session_id':self.session_id,'initial_balance':self.initial_balance,'cash':self.balance,
                'realized_pnl':sum(p['pnl'] for p in self.closed),'open_positions':len(self.positions),
                'data_label':self.data_label,'real_money':False}


def signal_key(session_id,strategy_id,version,symbol,closed_at,direction):
    parts=(session_id,strategy_id,version,symbol,closed_at,direction)
    if any(x is None or not str(x).strip() for x in parts):raise ValueError('Incomplete signal identity')
    return hashlib.sha256(json.dumps(parts,separators=(',',':')).encode()).hexdigest()


def claim_signal(conn,key,owner,*,configured_owner):
    """Call only on an explicitly provisioned sandbox/session DB, never during import."""
    if owner not in ('main','cloud') or owner!=configured_owner:return False
    cur=conn.execute('INSERT INTO intelligence_signal_claims(signal_key,owner) VALUES (?,?) ON CONFLICT(signal_key) DO NOTHING',(key,owner))
    conn.commit()
    return cur.rowcount==1


def dry_run_message(result,symbol='SYNTHETIC'):
    reason='; '.join(result.get('reasons',[]))
    return {'mode':'dry-run','sent':False,'network_calls':0,
            'text':f"<b>SINDHU PAPER RESEARCH</b>\n{escape(symbol)}\nData: {escape(result.get('data_label','synthetic'))}\nDecision: {escape(result['decision'])}\nReason: {escape(reason)}\nNo order or public signal sent."}

"""Measured paper outcomes, separated by strategy version; no automatic approval."""
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3


def read_closed_trades(limit=20000):
    columns='id,strategy_id,strategy_name,strategy_version,pnl,pnl_pct,risk_amount,entry_price,stop_loss,take_profit,market_state,created_at,closed_at'
    url=os.environ.get('DATABASE_URL')
    if url:
        import psycopg2
        conn=psycopg2.connect(url,connect_timeout=10)
        conn.set_session(readonly=True)
    else:
        from data_engine.paths import DB_PATH
        if not Path(DB_PATH).exists():return [],False
        conn=sqlite3.connect(Path(DB_PATH).as_uri()+'?mode=ro',uri=True)
    try:
        cur=conn.cursor()
        cur.execute(f"SELECT {columns} FROM paper_positions WHERE status='closed' ORDER BY closed_at,id LIMIT {int(limit)+1}")
        rows=cur.fetchall();names=[d[0] for d in cur.description]
        return [dict(zip(names,r)) for r in rows[:limit]],len(rows)>limit
    finally:conn.close()


def metrics(rows):
    measured=[r for r in rows if r.get('pnl') is not None and math.isfinite(float(r['pnl']))]
    measured.sort(key=lambda r:(r.get('closed_at') or '',r.get('id') or ''))
    pnl=[float(r['pnl']) for r in measured];n=len(pnl)
    if not n:return {'trades':0,'status':'NOT TESTED','win_rate_pct':None,'profit_factor':None,'expectancy':None,'max_drawdown':None,'max_drawdown_pct':None}
    wins=sum(x>0 for x in pnl);gross_win=sum(x for x in pnl if x>0);loss=-sum(x for x in pnl if x<0)
    total=0.0;peak=0.0;dd=0.0
    for value in pnl:total+=value;peak=max(peak,total);dd=max(dd,peak-total)
    returns=[float(r['pnl_pct']) for r in measured if r.get('pnl_pct') is not None and math.isfinite(float(r['pnl_pct']))]
    rr=[]
    for r in measured:
        e,s,t=r.get('entry_price'),r.get('stop_loss'),r.get('take_profit')
        if all(x is not None and math.isfinite(float(x)) for x in (e,s,t)) and e!=s:
            rr.append(abs(t-e)/abs(e-s))
    p=wins/n;z=1.96;den=1+z*z/n;center=(p+z*z/(2*n))/den
    margin=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    pf=gross_win/loss if loss else None
    regimes=defaultdict(list)
    for row in measured:regimes[row.get('market_state') or 'NOT TESTED'].append(float(row['pnl']))
    return {'trades':n,'missing_pnl_rows':len(rows)-n,'win_rate_pct':p*100,'win_rate_95pct_interval':[100*(center-margin),100*(center+margin)],
            'profit_factor':pf,'profit_factor_note':'No losses in sample; ratio undefined' if not loss else None,
            'average_return_pct':sum(returns)/len(returns) if returns else None,'expectancy':sum(pnl)/n,
            'net_pnl':sum(pnl),'max_drawdown':dd,'max_drawdown_pct':None,
            'drawdown_basis':'Recorded realized PnL in chronological order; initial balance/intratrade equity unavailable',
            'average_risk_reward':sum(rr)/len(rr) if rr else None,
            'risk_reward_basis':'Planned target distance / initial stop distance; not realized R',
            'by_regime':{k:{'trades':len(v),'pnl':sum(v),'expectancy':sum(v)/len(v)} for k,v in regimes.items()},
            'test_period':[measured[0].get('closed_at'),measured[-1].get('closed_at')],
            'dataset_sha256':hashlib.sha256(json.dumps(measured,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest(),
            'sample_warning':'Small sample (<30)' if n<30 else 'Observational paper sample; independent validation required',
            'costs_verified':False,'status':'REJECT' if n>=30 and sum(pnl)<0 else 'REVIEW',
            'paper_approved':False}


def leaderboard(trades=None,definitions=None):
    from trading_intelligence.catalog import strategy_library
    incomplete=False
    if trades is None:trades,incomplete=read_closed_trades()
    definitions=strategy_library() if definitions is None else definitions
    groups=defaultdict(list)
    for row in trades:groups[(row.get('strategy_id'),row.get('strategy_version'))].append(row)
    rows=[]
    for (ident,version),items in groups.items():
        rows.append({'strategy_id':ident,'version':version,'name':items[0].get('strategy_name'),**metrics(items)})
    for d in definitions:
        if (d['id'],d.get('version')) not in groups:
            rows.append({'strategy_id':d['id'],'version':d.get('version'),'name':d.get('name'),**metrics([])})
    # Sample size first; never present the best small-sample win rate as a winner.
    rows.sort(key=lambda r:(-r['trades'],str(r.get('name'))))
    return {'rows':rows,'source':'Recorded closed paper positions','truncated':incomplete,
            'ranking':'Sample count; not a profitability ranking','automatic_promotion':False,
            'historical_open_positions_included':False}

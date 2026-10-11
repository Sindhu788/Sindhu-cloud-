import concurrent.futures
import sqlite3

import pytest

from trading_intelligence.shared_wallet import SharedWallet


def wallet(tmp_path):
    w = SharedWallet(tmp_path/'wallet.db')
    s = w.create('owner-fresh', 'a'*64)
    return w, s['session_id']


def opening(w, s, key='open-1', strategy='strategy-a', symbol='BTCUSDT', **extra):
    args = dict(position_id=key, strategy_id=strategy, symbol=symbol, price=100,
                stop=95, target=115, quantity=.1, gates_passed=True)
    args.update(extra)
    return w.open(s, key, **args)


def test_fresh_once_and_restart(tmp_path):
    w,s = wallet(tmp_path)
    r = w.snapshot(s)
    assert (r['cash'],r['equity'],r['net_pnl'],r['max_drawdown_pct']) == (100,100,0,0)
    assert all(r[k] == 0 for k in ('open_positions','closed_trades','wins','losses'))
    assert all(r[k] is None for k in ('win_rate_pct','profit_factor','realized_average_r'))
    assert r['paused'] and r['created_at'].endswith('+00:00')
    assert SharedWallet(w.path).create('owner-fresh','a'*64)['session_id'] == s
    with pytest.raises(ValueError,match='overwrite'):
        w.create('owner-fresh','b'*64)


def test_two_strategies_one_wallet_costed_roundtrip(tmp_path):
    w,s = wallet(tmp_path)
    w.event(s,'resume','control',{'paused':False})
    opening(w,s)
    opening(w,s,'open-2','strategy-b','ETHUSDT')
    r = SharedWallet(w.path).snapshot(s)
    assert r['cash'] == pytest.approx(79.963984)
    assert r['equity'] == pytest.approx(99.979984)
    assert r['lifetime']['accepted'] == 2
    w.close(s,'close-1','open-1',115,'target')
    r = w.close(s,'close-2','open-2',95,'stop')
    assert (r['wins'],r['losses'],r['closed_trades'],r['open_positions']) == (1,1,2,0)
    assert r['cash'] == pytest.approx(100+r['net_pnl'])
    assert r['max_drawdown_pct'] > 0
    assert r['profit_factor'] is None
    assert r == SharedWallet(w.path).snapshot(s)


def test_idempotency_and_conflicts(tmp_path):
    w,s = wallet(tmp_path)
    w.event(s,'resume','control',{'paused':False})
    a=opening(w,s)
    assert opening(w,s) == a
    with pytest.raises(ValueError,match='different content'):
        opening(w,s,quantity=.11)
    with pytest.raises(ValueError,match='Symbol conflict'):
        opening(w,s,'other','other-strategy')
    a=w.close(s,'close','open-1',115,'target')
    assert w.close(s,'close','open-1',115,'target') == a
    with pytest.raises(ValueError,match='Different close'):
        w.close(s,'close','open-1',120,'target')


def test_parallel_strategy_entries_share_cash_and_symbol_lock(tmp_path):
    w,s=wallet(tmp_path)
    w.event(s,'resume','control',{'paused':False})
    def enter(i):
        try:
            opening(w,s,str(i),str(i))
            return True
        except ValueError:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(enter,range(8))) == 1
    assert w.snapshot(s)['open_positions'] == 1


@pytest.mark.parametrize('kwargs',[
    {'stop':101}, {'target':101}, {'quantity':10}, {'quantity':float('nan')},
    {'quantity':-.1}, {'fee_bps':-1}, {'gates_passed':False},
])
def test_risk_rejections_do_not_debit(tmp_path,kwargs):
    w,s=wallet(tmp_path)
    w.event(s,'resume','control',{'paused':False})
    with pytest.raises(ValueError):
        opening(w,s,**kwargs)
    assert w.snapshot(s)['cash'] == 100


def test_pause_blocks_entry_but_preserves_protective_exit(tmp_path):
    w,s=wallet(tmp_path)
    with pytest.raises(ValueError,match='Paused'):
        opening(w,s)
    w.event(s,'resume','control',{'paused':False})
    opening(w,s)
    w.event(s,'pause','control',{'paused':True})
    assert w.close(s,'close','open-1',95,'stop')['open_positions'] == 0


def test_daily_lifetime_and_duplicate_delivery_count(tmp_path):
    w,s=wallet(tmp_path)
    with w.connect() as conn:
        w._append(conn,s,'yesterday','scan',{'success':True},'2025-01-01T12:00:00+00:00')
    w.event(s,'today','scan',{'success':True,'symbols':['BTCUSDT']})
    for _ in range(2):
        w.event(s,'delivery','delivery',{'status':'sent','private_verified':True})
    r=w.snapshot(s)
    assert r['daily_utc']['scans_completed'] == 1
    assert r['lifetime']['scans_completed'] == 2
    assert r['lifetime']['delivery_success'] == 1


def test_no_legacy_table_writes(tmp_path):
    path=tmp_path/'wallet.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE paper_positions(id TEXT,pnl REAL)')
        conn.execute("INSERT INTO paper_positions VALUES('historical',-5)")
    w=SharedWallet(path)
    s=w.create('fresh','a'*64)['session_id']
    assert w.snapshot(s)['closed_trades'] == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT * FROM paper_positions').fetchall() == [('historical',-5)]

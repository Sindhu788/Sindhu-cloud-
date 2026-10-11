"""Retry exactly seven failed frozen cases into a separate evidence directory."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(DATABASE_URL='', SINDHU_SAFE_START='1', SINDHU_TELEGRAM_DRY_RUN='1',
                  SINDHU_PUBLIC_SIGNAL_OWNER='disabled', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
if os.name == 'nt':
    platform._wmi_query = lambda *a, **k: (_ for _ in ()).throw(OSError('WMI unavailable'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    from market_history.core import sha256
    from market_history.downloader import atomic_json, writer_lock
    from trading_intelligence.catalog import strategy_library, load_strategy_config
    from trading_intelligence.historical_lab import verified_manifest, load_source, derive_validate, run_case, TIMEFRAMES
    original = Path('D:/sindhu/data/overnight_workspace/data/overnight_qa/research_lab')
    source = Path('D:/sindhu/data/market_history')
    old = json.loads((original/'latest.json').read_text())
    if old['run_id'] != '4450a2ba369d1a4dcdeb':
        raise ValueError('Unexpected original research run')
    failures = [r for r in old['results'] if r['status'] == 'NOT_TESTABLE']
    expected = {'872544b77a57', 'd62e5015a93b', 'e117bb9c6b9b', '909e02bad309', 'b36687e8401a', 'b397a95c9d43', 'fb090ba34aa8'}
    if len(failures) != 7 or {r['strategy_id'] for r in failures} != expected or any(r['coin'] != 'BTCUSDT' for r in failures):
        raise ValueError('Failed-case scope differs')
    files = [original/'latest.json', original/'progress.json'] + [original/old['run_id']/('BTCUSDT-'+ident+'.json') for ident in sorted(expected)]
    preserved = {str(p): sha256(p) for p in files}
    manifest, receipt = verified_manifest(source)
    if receipt['manifest_sha256'] != old['dataset']['manifest_sha256']:
        raise ValueError('Dataset identity differs')
    items = {x['id']: x for x in strategy_library()}
    for ident in expected:
        if items[ident]['definition_sha256'] != old['identity']['definitions'][ident]:
            raise ValueError('Frozen strategy definition differs: '+ident)
    args.output.mkdir(parents=True, exist_ok=False)
    with writer_lock(args.output):
        identity = {'original_run_id': old['run_id'], 'original_hashes': preserved,
                    'manifest_sha256': receipt['manifest_sha256'], 'replay_seconds': 120,
                    'frozen_replication_selection': old['replication_selection'],
                    'code_sha256': {name: sha256(ROOT/name) for name in ('scripts/retry_failed_research.py', 'trading_intelligence/historical_lab.py', 'backtest_engine/engine.py', 'backtest_engine/mtf_context.py')},
                    'selection_policy': 'Diagnostic retries only; original ranking and cross-coin selections unchanged.'}
        atomic_json(args.output/'identity.json', identity)
        atomic_json(args.output/'progress.json', {'stage':'SOURCE_VALIDATION','completed':0})
        candles = load_source(source, 'BTCUSDT', manifest)
        frames = {'1m': candles}
        derived = []
        for tf in TIMEFRAMES:
            frames[tf], check = derive_validate(candles, tf)
            derived.append(check)
        results = []
        # Resolve alignment failures first; original time limits stay intact.
        ordered = sorted(expected, key=lambda ident: ident in {'872544b77a57','d62e5015a93b','e117bb9c6b9b'})
        for ident in ordered:
            atomic_json(args.output/'progress.json', {'stage':'REPLAY','strategy_id':ident,'completed':len(results)})
            started = time.monotonic()
            try:
                row = run_case(items[ident], load_strategy_config(ident), frames, 'BTCUSDT')
            except Exception as exc:
                row = {'strategy_id':ident,'coin':'BTCUSDT','status':'NOT_TESTABLE','reason':type(exc).__name__+': '+str(exc)[:250]}
            row['retry_elapsed_seconds'] = round(time.monotonic()-started, 3)
            atomic_json(args.output/('BTCUSDT-'+ident+'.json'), row)
            results.append(row)
            print(json.dumps({'strategy_id':ident,'status':row['status'],'seconds':row['retry_elapsed_seconds']}), flush=True)
        if any(sha256(Path(p)) != digest for p,digest in preserved.items()):
            raise ValueError('Original research preservation check failed')
        result = {'identity':identity,'derived':derived,'results':results,'counts':dict(Counter(r['status'] for r in results)),
                  'original_preserved':True,'completed_at':datetime.now(timezone.utc).isoformat()}
        atomic_json(args.output/'latest.json', result)
        atomic_json(args.output/'progress.json', {'stage':'COMPLETED','completed':len(results),'counts':result['counts']})
        print(json.dumps({'counts':result['counts'],'original_preserved':True}), flush=True)


if __name__ == '__main__':
    main()

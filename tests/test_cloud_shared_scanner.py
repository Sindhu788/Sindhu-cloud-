import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from trading_intelligence import cloud_shared_scanner as cloud


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(cloud, '_process', None)
    for key in ('SINDHU_SHARED_PAPER_ENABLED','DATABASE_URL','SINDHU_TELEGRAM_DRY_RUN','SINDHU_PUBLIC_SIGNAL_OWNER'):
        monkeypatch.delenv(key, raising=False)


def approved(monkeypatch):
    for key,value in {'SINDHU_SHARED_PAPER_ENABLED':'1','DATABASE_URL':'test-placeholder','SINDHU_TELEGRAM_DRY_RUN':'1','SINDHU_PUBLIC_SIGNAL_OWNER':'disabled'}.items():
        monkeypatch.setenv(key,value)


def test_default_never_starts_worker(monkeypatch):
    launch=Mock();monkeypatch.setattr(cloud.subprocess,'Popen',launch)
    with pytest.raises(ValueError,match='disabled'):cloud.start()
    launch.assert_not_called()


@pytest.mark.parametrize('missing',['DATABASE_URL','SINDHU_TELEGRAM_DRY_RUN','SINDHU_PUBLIC_SIGNAL_OWNER'])
def test_delivery_or_database_missing_blocks_start(monkeypatch,missing):
    approved(monkeypatch);monkeypatch.delenv(missing)
    launch=Mock();monkeypatch.setattr(cloud.subprocess,'Popen',launch)
    with pytest.raises(ValueError):cloud.start()
    launch.assert_not_called()


def test_start_uses_only_shared_child_and_never_duplicates(monkeypatch):
    approved(monkeypatch)
    process=SimpleNamespace(poll=lambda:None)
    launch=Mock(return_value=process);monkeypatch.setattr(cloud.subprocess,'Popen',launch)
    cloud.start();cloud.start()
    launch.assert_called_once()
    command=launch.call_args.args[0]
    assert command[-3:]==['--cloud','--cycles','0']
    assert command[1].endswith('run_shared_paper.py')


def test_duplicate_database_worker_refused(monkeypatch):
    from trading_intelligence import shared_postgres
    lock=Mock();lock.cursor.return_value.fetchone.return_value=(False,)
    monkeypatch.setattr(shared_postgres,'configured_wallet',lambda:SimpleNamespace(connection_factory=lambda:lock))
    with pytest.raises(RuntimeError,match='Another'):cloud.cloud_wallet()
    lock.close.assert_called_once()


def test_stale_receipt_cannot_claim_worker_running(tmp_path,monkeypatch):
    from data_engine import paths
    monkeypatch.setattr(paths,'DATA_DIR',tmp_path)
    (tmp_path/'shared_paper').mkdir()
    (tmp_path/'shared_paper/scanner_state.json').write_text(json.dumps({'state':'RUNNING','cycles_completed':50}))
    result=cloud.status()
    assert result['running'] is False and result['cycles_completed']==0


def test_frozen_cloud_allowlist_matches_existing_rules():
    from trading_intelligence.paper_eligibility import select_eligible
    manifest=json.loads((Path(__file__).resolve().parents[1]/'cloud_runtime/paper_allowlist.json').read_text())
    selected=select_eligible(manifest,isolated=False)
    assert len(selected)==2


def test_shutdown_terminates_owned_child(monkeypatch):
    process=Mock();process.poll.return_value=None
    monkeypatch.setattr(cloud,'_process',process)
    cloud.stop()
    process.terminate.assert_called_once();process.wait.assert_called_once_with(timeout=10)
    assert cloud._process is None

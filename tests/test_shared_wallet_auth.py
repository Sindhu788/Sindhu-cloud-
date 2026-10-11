"""Unauthenticated HTTP must never reach the shared wallet or its controls."""
import pytest


@pytest.mark.parametrize('method,path',[
    ('get','/api/intelligence/shared-wallet'),
    ('post','/api/intelligence/shared-wallet/pause'),
    ('post','/api/intelligence/shared-wallet/resume'),
])
def test_shared_wallet_requires_real_login(method,path,tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sindhu_web.api.intelligence import router
    from sindhu_web import security
    from data_engine import paths
    # No credential/session substitute: a request with no cookie must fail
    # before any wallet file is opened or initialized.
    monkeypatch.setattr(paths,'DATA_DIR',tmp_path)
    app=FastAPI();app.include_router(router)
    app.middleware('http')(security.token_guard_middleware)
    client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',50000))
    response=getattr(client,method)(path)
    assert response.status_code==401
    assert response.json()=={'detail':'login required'}
    assert not (tmp_path/'shared_paper').exists()

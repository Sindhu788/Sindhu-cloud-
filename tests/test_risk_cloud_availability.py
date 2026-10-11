"""Missing local-only provenance must not imply that cloud safety gates passed."""
import pytest
from sindhu_web.api import risk_department as risk


def unavailable(*args, **kwargs):
    raise RuntimeError('Local-only table unavailable')


def test_cloud_missing_extraction_is_unknown_not_unlocked(monkeypatch):
    monkeypatch.setattr(risk, 'CLOUD_MODE', True)
    monkeypatch.setattr(risk.strategy_library, 'list_all', lambda: [{'id': 'one'}])
    monkeypatch.setattr(risk.extraction_lock, 'check_strategy_locks_bulk', unavailable)
    result = risk._incomplete_lock_summary()
    assert result['status'] == 'UNAVAILABLE'
    assert result['locked_count'] is None and result['locked_strategy_ids'] is None


def test_cloud_missing_evolution_does_not_invent_zero_rollbacks(monkeypatch):
    monkeypatch.setattr(risk, 'CLOUD_MODE', True)
    monkeypatch.setattr(risk.storage, 'list_evolution_comparisons', unavailable)
    result = risk._evolution_gate_summary()
    assert result['status'] == 'UNAVAILABLE'
    assert result['recent_rollbacks'] is None and result['recent_comparisons_checked'] is None


def test_main_errors_are_not_hidden_by_cloud_fallback(monkeypatch):
    monkeypatch.setattr(risk, 'CLOUD_MODE', False)
    monkeypatch.setattr(risk.storage, 'list_evolution_comparisons', unavailable)
    with pytest.raises(RuntimeError, match='Local-only'):
        risk._evolution_gate_summary()


def test_available_cloud_provenance_still_reports_real_locks(monkeypatch):
    monkeypatch.setattr(risk, 'CLOUD_MODE', True)
    monkeypatch.setattr(risk.strategy_library, 'list_all', lambda: [{'id': 'one'}, {'id': 'two'}])
    monkeypatch.setattr(risk.extraction_lock, 'check_strategy_locks_bulk',
                        lambda ids: {'one': {'locked': True}, 'two': {'locked': False}})
    assert risk._incomplete_lock_summary()['locked_strategy_ids'] == ['one']

"""Master Task Expansion, Part 6: mounted sindhu_web/api/system.py's
existing Health Dashboard/Error Center endpoint onto cloud_runtime/app.py
too. This tests the one real code change that made that safe:
_active_background_processes() must never import evolution_engine.engine
when running in cloud mode, since cloud_runtime/app.py's own tests
(test_cloud_runtime.py) assert that module is never pulled into a cloud
process at all -- calling this function on a real cloud deployment must
not be the thing that first breaks that.
"""
import sys
from unittest.mock import patch

from sindhu_web import security
from sindhu_web.api.system import _active_background_processes


def test_cloud_mode_never_imports_evolution_engine_engine():
    with patch.object(security, "CLOUD_MODE", True):
        before = set(sys.modules)
        _active_background_processes()
        after = set(sys.modules)
    newly_imported = after - before
    assert "evolution_engine.engine" not in newly_imported
    assert "evolution_engine.governor" not in newly_imported


def test_cloud_mode_reports_paper_trading_but_never_evolution():
    with patch.object(security, "CLOUD_MODE", True), \
         patch("paper_trading.engine.engine") as fake_paper_engine, \
         patch("sindhu_web.jobs.job_manager.list_jobs", return_value=[]):
        fake_paper_engine.is_running.return_value = True
        items = _active_background_processes()
    names = {i["name"] for i in items}
    assert "paper_trading" in names
    assert "evolution" not in names


def test_local_mode_still_reports_evolution_when_running():
    with patch.object(security, "CLOUD_MODE", False), \
         patch("paper_trading.engine.engine") as fake_paper_engine, \
         patch("evolution_engine.engine.engine") as fake_evo_engine, \
         patch("sindhu_web.jobs.job_manager.list_jobs", return_value=[]):
        fake_paper_engine.is_running.return_value = False
        fake_evo_engine.is_running.return_value = True
        items = _active_background_processes()
    names = {i["name"] for i in items}
    assert "evolution" in names

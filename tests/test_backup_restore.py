import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_restore_script_verifies_counts_and_refuses_to_overwrite(tmp_path):
    exp = tmp_path / "export"
    exp.mkdir()
    (exp / "alpha.jsonl").write_text("\n".join(json.dumps({"id": i, "val": {"k": i}}) for i in range(3)) + "\n", encoding="utf-8")
    (exp / "empty_t.jsonl").write_text("", encoding="utf-8")
    json.dump({"alpha": [3, 3], "empty_t": [0, 0], "auth_credentials": "SKIPPED (credentials)"}, open(exp / "_manifest.json", "w"))
    target = tmp_path / "restored.db"
    env = dict(os.environ, SINDHU_DATA_DIR=str(tmp_path))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "restore_export_to_sqlite.py"), str(exp), str(target)],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 ok, 0 mismatched, 1 skipped" in r.stdout and "rows restored: 3" in r.stdout
    again = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "restore_export_to_sqlite.py"), str(exp), str(target)],
                           capture_output=True, text=True, env=env, timeout=120)
    assert again.returncode != 0 and "refusing to overwrite" in (again.stdout + again.stderr)


def test_backup_script_never_prints_or_stores_the_connection_string():
    text = open(os.path.join(ROOT, "scripts", "backup_cloud_export.py"), encoding="utf-8").read()
    assert "default_transaction_read_only=on" in text and "exist_ok=False" in text
    assert "print(_url" not in text and "SKIPPED (credentials)" in text

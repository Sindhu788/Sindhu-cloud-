"""Master plan V2 R10 (N5 + P35): the owner can see and reset the dashboard account locally; nothing secret is printed."""
import pytest

from sindhu_web import auth
from tools import reset_dashboard_user as tool


@pytest.fixture
def creds(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "_CRED_FILE", f"test_creds_{tmp_path.name}.json")
    monkeypatch.setattr(auth, "_SESSIONS_FILE", f"test_sessions_{tmp_path.name}.json")
    yield


def test_list_without_an_account(creds):
    out = []
    assert tool.main(["--list"], out=out.append) == 0
    assert "no dashboard account" in out[0] and "owner" in out[1]


def test_reset_then_login_works_and_old_sessions_are_signed_out(creds):
    auth.set_credentials("forgotten_name", "old-password-1")
    tok = auth.create_session()
    assert auth.is_valid_session(tok)
    out = []
    answers = iter(["new-password-2", "new-password-2"])
    tool.main(["--reset", "sindhu"], ask=lambda prompt: next(answers), out=out.append)
    assert auth.verify_password("sindhu", "new-password-2")
    assert not auth.verify_password("forgotten_name", "old-password-1")
    assert not auth.is_valid_session(tok)
    printed = " ".join(out)
    assert "new-password-2" not in printed and "password_hash" not in printed
    out.clear()
    tool.main(["--list"], out=out.append)
    assert "'sindhu'" in out[0]


def test_short_or_mismatched_password_changes_nothing(creds):
    auth.set_credentials("keep", "keep-password-1")
    with pytest.raises(SystemExit):
        tool.main(["--reset", "x"], ask=lambda p: "short", out=lambda s: None)
    answers = iter(["aaaaaaaa1", "bbbbbbbb2"])
    with pytest.raises(SystemExit):
        tool.main(["--reset", "x"], ask=lambda p: next(answers), out=lambda s: None)
    assert auth.verify_password("keep", "keep-password-1")


def test_cloud_without_database_url_refuses(creds, monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(tool, "ROOT", str(tmp_path))
    with pytest.raises(SystemExit) as e:
        tool.main(["--list", "--cloud"], out=lambda s: None)
    assert "DATABASE_URL" in str(e.value)

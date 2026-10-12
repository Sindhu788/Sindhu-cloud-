import json
import pytest
from sindhu_web.local_account_recovery import restore_unconfigured_account


def record():
    return {"username":"isolated-owner", "salt":"ab"*16, "password_hash":"cd"*32}


def test_seeded_empty_file_can_restore_existing_account(tmp_path):
    source=tmp_path/"source.json";target=tmp_path/"auth.json"
    source.write_text(json.dumps(record()));target.write_text("{}")
    assert restore_unconfigured_account(source,target)=="EXISTING_OWNER_ACCOUNT_RESTORED"
    assert json.loads(target.read_text())==record()
    backups=list(tmp_path.glob("auth.json.unconfigured.*"))
    assert len(backups)==1 and backups[0].read_text()=="{}"


def test_configured_or_partial_account_is_never_overwritten(tmp_path):
    source=tmp_path/"source.json";target=tmp_path/"auth.json"
    source.write_text(json.dumps(record()))
    for saved in [record(), {"username":"different-owner"}]:
        target.write_text(json.dumps(saved));before=target.read_bytes()
        assert restore_unconfigured_account(source,target)=="EXISTING_ACCOUNT_PRESERVED"
        assert target.read_bytes()==before


def test_invalid_source_refuses_recovery(tmp_path):
    source=tmp_path/"source.json";target=tmp_path/"auth.json"
    source.write_text('{"username":"owner"}');target.write_text("{}")
    with pytest.raises(ValueError,match="owner-controlled"):
        restore_unconfigured_account(source,target)
    assert target.read_text()=="{}"


def test_missing_source_never_creates_account(tmp_path):
    target=tmp_path/"auth.json"
    assert restore_unconfigured_account(tmp_path/"absent",target)=="OWNER_RECOVERY_REQUIRED"
    assert not target.exists()

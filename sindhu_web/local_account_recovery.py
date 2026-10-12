"""Recover an unconfigured local copy; never replace an existing account."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def restore_unconfigured_account(source, target):
    source, target = Path(source), Path(target)
    current = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    if current:
        return "EXISTING_ACCOUNT_PRESERVED"
    if not source.is_file():
        return "OWNER_RECOVERY_REQUIRED"
    original = json.loads(source.read_text(encoding="utf-8"))
    try:
        valid = (bool(original["username"]) and len(bytes.fromhex(original["salt"])) == 16
                 and len(bytes.fromhex(original["password_hash"])) == 32)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Existing owner account record is invalid; owner-controlled recovery required")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copy2(target, target.with_name(target.name + ".unconfigured." + stamp))
    temporary = target.with_name(target.name + ".recovering")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(original, stream)
    temporary.replace(target)
    return "EXISTING_OWNER_ACCOUNT_RESTORED"

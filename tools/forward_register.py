"""Pre-register a strategy for the forward test (Day 7). Append-only: adds one candidate to `manifest/forward_registry.json` (a .bak copy is kept) with its id,
config hash, code commit and ITS OWN window start = the next UTC midnight after registration (so nothing already seen can count). Refuses a strategy that is already
registered. Usage: python tools/forward_register.py --strategy-id <id> [--registry <file>] [--library <dir>]"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_REGISTRY = r"D:\sindhu_data\manifest\forward_registry.json"


def next_midnight(now):
    d = (now + dt.timedelta(days=1)).date()
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


def register(registry_path, strategy_id, config_hash, commit, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    reg = json.load(open(registry_path, encoding="utf-8"))
    if any(c.get("strategy_id") == strategy_id for c in reg.get("candidates", [])):
        raise ValueError(f"{strategy_id} is already registered")
    shutil.copyfile(registry_path, registry_path + ".bak")
    entry = {"strategy_id": strategy_id, "config_hash": config_hash, "code_commit": commit, "registered_at": now.isoformat(timespec="seconds"),
             "window_start_utc": next_midnight(now).strftime("%Y-%m-%dT%H:%M:%SZ")}
    reg.setdefault("candidates", []).append(entry)
    tmp = registry_path + ".tmp"
    json.dump(reg, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, registry_path)
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy-id", required=True)
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    ap.add_argument("--library", default=os.environ.get("SINDHU_STRATEGY_LIBRARY_DIR", r"D:\sindhu_runtime\strategy_library"))
    a = ap.parse_args(argv)
    os.environ["SINDHU_STRATEGY_LIBRARY_DIR"] = a.library
    from backtest_engine import strategy_library
    from data_platform import experiments
    cfg = strategy_library.load(a.strategy_id)
    e = register(a.registry, a.strategy_id, experiments.config_hash(cfg.to_dict()), experiments.code_commit())
    print("registered:", json.dumps(e))


if __name__ == "__main__":
    main()

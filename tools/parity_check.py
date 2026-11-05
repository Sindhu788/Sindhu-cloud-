"""Master plan A22 (P12): local vs Cloud effective config, by the SAFE (non-secret) summary of paper_trading/self_check.py.
Local side: computed in a fresh process against the real local data folder (read only). Cloud side: GET /health/details (public, no
secrets). Prints the config hashes and every differing key. Usage (stable venv): python tools/parity_check.py [--local-data D:\\sindhu\\data]
[--cloud https://sindhu-cloud-1.onrender.com]"""
import argparse
import json
import os
import subprocess
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def local_summary(data_dir):
    code = ("import json,sys; sys.path.insert(0, %r); from paper_trading import self_check as s; "
            "o,h=s.safe_config_summary(); print(json.dumps({'summary':o,'hash':h}))" % ROOT)
    env = dict(os.environ, SINDHU_DATA_DIR=data_dir)
    env.pop("DATABASE_URL", None)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    return json.loads(out.stdout.strip().splitlines()[-1])


def flatten(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local-data", default=r"D:\sindhu\data")
    ap.add_argument("--cloud", default="https://sindhu-cloud-1.onrender.com")
    a = ap.parse_args()
    loc = local_summary(a.local_data)
    try:
        r = requests.get(a.cloud.rstrip("/") + "/health/details", timeout=60)
        cloud = r.json() if r.status_code == 200 else None
    except Exception as e:
        cloud = None
        print(f"Cloud /health/details not reachable: {type(e).__name__}")
    print(f"local hash {loc['hash']}")
    if cloud is None or "config_summary" not in cloud:
        print("Cloud: no /health/details yet (deployed before master plan A17?)")
        return
    print(f"cloud hash {cloud['config_hash']} (commit {cloud.get('commit')})")
    L, C = flatten(loc["summary"]), flatten(cloud["config_summary"])
    diffs = [(k, L.get(k), C.get(k)) for k in sorted(set(L) | set(C)) if L.get(k) != C.get(k)]
    print("| Key | Local | Cloud |\n|---|---|---|")
    for k, l, c in diffs:
        print(f"| {k} | {l} | {c} |")
    print(f"{len(diffs)} differences")


if __name__ == "__main__":
    main()

"""Full dataset verification (Day 7 Step 3). Read-only: re-hashes EVERY file the manifest calls 'ok', compares the parquet row count, finds files on disk
that the manifest does not know and manifest lines whose file is missing. Writes a JSON report next to the manifest in a NEW file (never overwrites).
Usage (venv with pyarrow): python tools/verify_dataset.py [root]   (default D:\\sindhu_data)"""
import datetime as dt
import hashlib
import json
import os
import sys

import pyarrow.parquet as pq


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def path_for(root, key, entry):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_platform import store
    sym, period = key.split("/")
    return (store.month_path if len(period) == 7 else store.day_path)("binance", sym, period, root)


def main(root=None):
    root = root or (sys.argv[1] if len(sys.argv) > 1 else r"D:\sindhu_data")
    man = json.load(open(os.path.join(root, "manifest", "manifest.json"), encoding="utf-8"))
    files = {}
    for dp, _, fs in os.walk(os.path.join(root, "candles")):
        for f in fs:
            if f.endswith(".parquet"):
                files[os.path.join(dp, f)] = True
    rep = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "manifest_entries": len(man), "ok_entries": 0, "files_on_disk": len(files),
           "hash_mismatch": [], "row_mismatch": [], "missing_file": [], "unlisted_file": [], "rows_total": 0}
    seen = set()
    for key, e in sorted(man.items()):
        if len(key.split("/")) != 2 or e.get("status") != "ok":
            continue
        rep["ok_entries"] += 1
        p = path_for(root, key, e)
        seen.add(p)
        if not os.path.exists(p):
            rep["missing_file"].append(key); continue
        if sha256_file(p) != e["sha256"]:
            rep["hash_mismatch"].append(key)
        n = pq.ParquetFile(p).metadata.num_rows
        rep["rows_total"] += n
        if n != e["rows"]:
            rep["row_mismatch"].append(key)
    rep["unlisted_file"] = sorted(os.path.relpath(f, root) for f in files if f not in seen)[:20]
    rep["unlisted_count"] = len([f for f in files if f not in seen])
    rep["verdict"] = "PASS" if not (rep["hash_mismatch"] or rep["row_mismatch"] or rep["missing_file"] or rep["unlisted_count"]) else "PROBLEMS"
    out = os.path.join(root, "manifest", f"full_verify_{dt.datetime.now():%Y%m%d_%H%M%S}.json")
    with open(out, "x", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in rep.items()}, indent=1))
    print("report:", out)
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

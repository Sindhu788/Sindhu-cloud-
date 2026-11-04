"""Dataset audit: every finished file on disk must be in the manifest with a matching sha256, and the other way round. Also runs the full quality
check on the 12-month window and writes docs-ready numbers. Usage: python -m data_platform.audit  (numpy + pyarrow only)"""
import datetime as dt
import glob
import json
import os
import sys

from data_platform import downloader, quality, store, universe


def main():
    root = store.root()
    man = downloader.Manifest(root)
    snap = man.snapshot()
    on_disk = {}
    for p in glob.glob(os.path.join(root, "candles", "binance", "*", "1m", "*.parquet")):
        sym, per = p.replace("\\", "/").split("/")[-3], os.path.basename(p)[:-8]
        on_disk[f"{sym}/{per}"] = p
    for p in glob.glob(os.path.join(root, "candles", "binance", "*", "1m_daily", "*.parquet")):
        sym, per = p.replace("\\", "/").split("/")[-3], os.path.basename(p)[:-8]
        on_disk[f"{sym}/{per}"] = p
    ok_keys = {k for k, v in snap.items() if v.get("status") == "ok" and len(k.split("/")) == 2}
    missing_in_manifest = sorted(set(on_disk) - ok_keys)
    missing_on_disk = sorted(ok_keys - set(on_disk))
    bad_sha = []
    for k in sorted(ok_keys & set(on_disk)):
        if snap[k].get("sha256") != store.sha256_file(on_disk[k]):
            bad_sha.append(k)
    adopted = 0
    for k in missing_in_manifest:
        rows, sha = downloader._verify_existing(on_disk[k])
        man.put(k, {"status": "ok", "rows": rows, "sha256": sha, "note": "adopted existing file (audit)", "checked_at": downloader._now()})
        adopted += 1
    uni = universe.load_latest(root)
    today = dt.datetime.now(dt.timezone.utc).date()
    end_month = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    months = downloader.month_list(end_month, 12)
    rep = quality.check_dataset(uni["symbols"][:50], months, base=root)
    quality.save_report(rep, "full_quality.json", root)
    out = {"files_on_disk": len(on_disk), "manifest_ok_entries": len(ok_keys), "adopted_into_manifest": adopted, "manifest_entries_without_file": missing_on_disk,
           "sha_mismatch": bad_sha, "summary": rep["summary"]}
    json.dump(out, open(os.path.join(root, "manifest", "audit.json"), "w"), indent=1)
    print(json.dumps(out, indent=1)[:3000])


if __name__ == "__main__":
    main()

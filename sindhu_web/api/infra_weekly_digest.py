"""Automated Weekly Digest (Grand Feature Expansion, Phase 7 Feature 10):
a weekly SYSTEM/INFRASTRUCTURE health digest -- backups created, incidents
opened/resolved, current disk/database size. Deliberately distinct
content from the 3 report types that already exist and are already
correctly scoped to their own subject matter: paper_trading.weekly_report
(trading performance), evolution_engine.weekly_review (tuning/evolution
activity, Phase 6), paper_trading.monthly_report (30-day trading). A
literal 4th remix of the SAME trading+evolution content would be
redundant and mean a 3rd weekly Telegram message -- this instead covers
content none of those 3 touch at all, matching this phase's own name
(Infrastructure & Sync). Mirrors weekly_report.py's exact generate/gate/
scheduler/Telegram-send shape."""

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from data_engine import storage, feature_toggles
from data_engine.paths import disk_usage_bytes
from paper_trading import telegram_bot
from sindhu_web.api import backup, weekly_snapshot

router = APIRouter()

DIGEST_INTERVAL_DAYS = 7


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _fmt_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def generate_infra_weekly_digest():
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=DIGEST_INTERVAL_DAYS)).isoformat()

    backups_this_week = [b for b in backup.list_backups()["backups"] if b["modified_at"] >= since_iso]
    weekly_snapshots_this_week = [s for s in weekly_snapshot.list_weekly_snapshots() if s["modified_at"] >= since_iso]

    all_incidents = storage.list_incidents(limit=1000)
    opened_this_week = [i for i in all_incidents if (i.get("detected_at") or i.get("created_at") or "") >= since_iso]
    resolved_this_week = [i for i in all_incidents if i.get("resolved_at") and i["resolved_at"] >= since_iso]
    still_open = [i for i in all_incidents if i["status"] != "resolved"]

    db_size = storage.db_file_size_bytes()
    data_size = disk_usage_bytes()

    lines = [
        f"Infrastructure Weekly Digest -- {now.strftime('%Y-%m-%d')}",
        "",
        f"Backups: {len(backups_this_week)} rolling backup(s) + {len(weekly_snapshots_this_week)} weekly snapshot(s) created this week.",
        f"Incidents: {len(opened_this_week)} opened, {len(resolved_this_week)} resolved this week; {len(still_open)} still open overall.",
        f"Database size: {_fmt_bytes(db_size)}. Total data folder size: {_fmt_bytes(data_size)}.",
    ]
    if still_open:
        lines.append("")
        lines.append("Still-open incidents:")
        for i in still_open[:5]:
            lines.append(f"  - ({i['severity']}) {i['title']}")

    report_text = "\n".join(lines)
    report_data = {
        "backups_this_week": len(backups_this_week), "weekly_snapshots_this_week": len(weekly_snapshots_this_week),
        "incidents_opened": len(opened_this_week), "incidents_resolved": len(resolved_this_week),
        "incidents_still_open": len(still_open),
        "database_size_bytes": db_size, "disk_usage_bytes": data_size,
    }
    storage.save_infra_weekly_digest(since_iso, now.isoformat(), json.dumps(report_data), report_text, _now_iso())
    return {"report_text": report_text, "report_data": report_data}


def maybe_generate_infra_weekly_digest():
    """Called periodically by the scheduler thread -- only generates a new
    digest if 7+ days have passed since the last one (or none exists yet).
    Also sends it to Telegram, same as weekly_report.py -- the 7-day gate
    already prevents more than one send per week."""
    if not feature_toggles.is_enabled("infra_weekly_digest_enabled"):
        return None
    last = storage.get_latest_infra_weekly_digest()
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.now(timezone.utc) - last_dt < timedelta(days=DIGEST_INTERVAL_DAYS):
            return None
    result = generate_infra_weekly_digest()
    if telegram_bot._master_enabled():
        ok, err = telegram_bot._raw_send(result["report_text"])
        storage.log_telegram_message(
            None, None, None, "infra_weekly_digest", result["report_text"], ok, err, _now_iso(),
        )
        result["telegram_sent"] = ok
        result["telegram_error"] = err
    return result


def start_infra_weekly_digest_scheduler_thread():
    """Runs once at server startup; checks every few hours whether a new
    digest is due -- same shape as backup.start_auto_backup_thread and
    paper_trading.weekly_report's own scheduler."""
    import threading
    import time
    from data_engine.logging_setup import log

    def _loop():
        while True:
            try:
                result = maybe_generate_infra_weekly_digest()
                if result:
                    log("[infra-weekly-digest] generated a new infrastructure weekly digest")
            except Exception as e:
                log(f"[infra-weekly-digest] generation failed: {e!r}")
            time.sleep(6 * 3600)  # check every 6 hours; the 7-day gate above prevents over-generating

    threading.Thread(target=_loop, daemon=True).start()


@router.get("/api/infra-weekly-digest")
def get_infra_weekly_digests(limit: int = 20):
    return {"digests": storage.list_infra_weekly_digests(limit=limit)}


@router.post("/api/infra-weekly-digest/generate-now")
def generate_infra_weekly_digest_now():
    """Manual trigger, bypassing the 7-day gate -- for testing/on-demand use."""
    result = generate_infra_weekly_digest()
    return {"ok": True, "report_text": result["report_text"]}

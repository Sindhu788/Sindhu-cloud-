"""Grand Master Batch, Phase 4 Item 6: "Cost of Running This System" tracker.

No automatic billing API exists for Render or the various AI providers
this project can use (and none is assumed here rather than faking one) --
so this is a simple, honest CEO-entered ledger of known recurring costs
(hosting plan, an AI API subscription, anything else), converted to one
comparable monthly total. Uses the same Postgres-aware persistence
pattern as every other settings blob in this codebase (data_engine.
config.load_persistent/save_persistent) so entries survive a cloud
redeploy instead of living only on Render's ephemeral filesystem.
"""

import uuid
from datetime import datetime, timezone

from data_engine import config as base_config

_CLOUD_KEY = "cost_tracker_items"
_FILE = "cost_tracker.json"
_DEFAULTS = {"items": []}

PERIODS = ("monthly", "yearly", "one_time")

_MONTHLY_MULTIPLIER = {"monthly": 1.0, "yearly": 1 / 12, "one_time": 0.0}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def list_costs():
    return base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)["items"]


def add_cost(label, amount_usd, period="monthly", note=None):
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}")
    if amount_usd < 0:
        raise ValueError("amount_usd must not be negative")
    data = base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)
    item = {
        "id": uuid.uuid4().hex[:12], "label": label, "amount_usd": round(float(amount_usd), 2),
        "period": period, "note": note, "added_at": _now_iso(),
    }
    data["items"].append(item)
    base_config.save_persistent(_CLOUD_KEY, _FILE, data)
    return item


def remove_cost(cost_id):
    data = base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i["id"] != cost_id]
    if len(data["items"]) == before:
        return False
    base_config.save_persistent(_CLOUD_KEY, _FILE, data)
    return True


def summary():
    """Every entry as-is, plus a single comparable monthly total -- a
    one_time cost contributes 0 to the recurring monthly total (it isn't
    an ongoing cost) but is still listed and included in its own
    all-time-spent figure."""
    items = list_costs()
    monthly_total = sum(i["amount_usd"] * _MONTHLY_MULTIPLIER[i["period"]] for i in items)
    one_time_total = sum(i["amount_usd"] for i in items if i["period"] == "one_time")
    return {
        "items": items,
        "monthly_total_usd": round(monthly_total, 2),
        "yearly_total_usd": round(monthly_total * 12, 2),
        "one_time_total_usd": round(one_time_total, 2),
    }

"""Grand Master Batch, Phase 5 Item 8: "Frozen" vs "Active" learning
toggle per strategy -- stops ONE specific strategy from being touched by
Evolution (new generations) or Self-Learning (lesson auto-apply) without
disabling either engine globally. Paper trading itself is completely
unaffected either way -- a frozen strategy keeps opening/closing real
positions exactly as normal, it just stops being mutated or having
patterns auto-applied to it.
"""

from data_engine import config as base_config

_CLOUD_KEY = "learning_freeze_strategy_ids"
_FILE = "learning_freeze.json"
_DEFAULTS = {"frozen_strategy_ids": []}


def list_frozen():
    return base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)["frozen_strategy_ids"]


def is_frozen(strategy_id):
    return strategy_id in list_frozen()


def set_frozen(strategy_id, frozen):
    data = base_config.load_persistent(_CLOUD_KEY, _FILE, _DEFAULTS)
    ids = set(data["frozen_strategy_ids"])
    if frozen:
        ids.add(strategy_id)
    else:
        ids.discard(strategy_id)
    data["frozen_strategy_ids"] = sorted(ids)
    base_config.save_persistent(_CLOUD_KEY, _FILE, data)
    return data["frozen_strategy_ids"]

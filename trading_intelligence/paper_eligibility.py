"""Frozen, explicit paper-only allowlists; no automatic strategy promotion."""
from backtest_engine.validator import validate
from trading_intelligence.catalog import strategy_library, load_strategy_config


def select_eligible(manifest, *, isolated):
    required_mode="isolated_qa" if isolated else "owner_approved_paper"
    if manifest.get("mode") != required_mode or not manifest.get("strategies"):
        raise ValueError("Explicit session paper allowlist/owner approval required")
    catalog={x["id"]:x for x in strategy_library()}
    selected=[];seen=set()
    for frozen in manifest["strategies"]:
        ident=frozen["strategy_id"]
        if ident in seen:raise ValueError("Duplicate allowlisted strategy")
        seen.add(ident);item=catalog.get(ident)
        if not item or item.get("archived") or item.get("status")=="rejected":
            raise ValueError("Allowlisted strategy is missing, archived or blocked")
        if (item["version"] != frozen["version"] or item["definition_sha256"] != frozen["definition_sha256"]):
            raise ValueError("Frozen strategy definition changed; renewed review required")
        cfg=load_strategy_config(ident,item["version"])
        supported=(set((cfg.timeframes or {}).values())=={"1h"} and
                   (cfg.long_entry_type or cfg.entry_type)=="market" and not cfg.exit_conditions and
                   not any((cfg.partial_take_profit,cfg.trailing_stop,cfg.time_exit_bars,cfg.breakeven_at_rr)))
        if not supported or validate(cfg):
            raise ValueError("Strategy is incompatible with the shared protective paper adapter")
        selected.append(dict(strategy_id=ident,strategy_name=item["name"],strategy_version=item["version"],priority=5,config=cfg))
    return selected

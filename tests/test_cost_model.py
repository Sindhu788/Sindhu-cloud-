import numpy as np

from data_platform import cost_model as cm


def test_tiers_scale_with_liquidity_and_volatility():
    a, b, c = cm.settings_for(1, 0.05), cm.settings_for(15, 0.05), cm.settings_for(40, 0.05)
    assert a["slippage_pct"] < b["slippage_pct"] < c["slippage_pct"] and a["spread_pct"] < b["spread_pct"] < c["spread_pct"]
    assert cm.settings_for(1, 0.5)["slippage_pct"] > a["slippage_pct"]            # a faster market costs more
    assert a["commission_pct"] == 0.10 and cm.settings_for(1, 0.05, 2.0)["commission_pct"] == 0.20


def test_reprice_is_exact_at_x1_and_frictionless_at_zero():
    trades = [{"pnl": -10.0, "commission_cost": 2.0, "slippage_cost": 1.0, "spread_cost": 0.5},
              {"pnl": 5.0, "commission_cost": 2.0, "slippage_cost": 1.0, "spread_cost": 0.0}]
    assert cm.reprice(trades, 1.0) == [-10.0, 5.0]
    assert cm.reprice(trades, 0.0) == [-6.5, 8.0]                                 # gross = net + all costs
    assert cm.reprice(trades, 2.0) == [-13.5, 2.0]                                # every cost doubled

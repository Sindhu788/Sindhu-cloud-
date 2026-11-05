import math

import pytest

from data_platform import metrics, protocol_analyze


def leg(pnl, risk, entry=1, exit_=2, side="long", sym="X", comm=0.0, slip=0.0, spr=0.0):
    return {"symbol": sym, "side": side, "entry_time": entry, "exit_time": exit_, "pnl": pnl, "risk_amount": risk,
            "commission_cost": comm, "slippage_cost": slip, "spread_cost": spr}


def test_profit_factor_known_values():
    assert metrics.profit_factor([10, -5, 10, -5]) == pytest.approx(2.0)
    assert metrics.profit_factor([3, 2]) == float("inf")           # no losses
    assert metrics.profit_factor([-3, -2]) == 0.0                  # no wins
    assert metrics.profit_factor([]) == 0.0 and metrics.profit_factor([0, 0]) == 0.0


def test_win_rate_expectancy_known_values():
    assert metrics.win_rate([1, -1, 2, 0]) == 0.5                  # zero is not a win
    assert metrics.expectancy([1, 2, 3, -6]) == 0.0
    assert metrics.win_rate([]) == 0.0 and metrics.expectancy([]) == 0.0


def test_t_stat_known_value_and_edge_cases():
    v = [1, 2, 3, 4, 5]                                            # mean 3, sd sqrt(2.5), n 5
    assert metrics.t_stat(v) == pytest.approx(3 / (math.sqrt(2.5) / math.sqrt(5)))
    assert metrics.t_stat([1, 1, 1]) is None                       # zero variance
    assert metrics.t_stat([1, 2]) is None and metrics.t_stat([]) is None   # too few


def test_max_drawdown_known_value_losing_streak():
    assert metrics.max_drawdown([5, -2, -3, 4, -1]) == 5.0         # equity 5,3,0,4,3 -> peak 5 to trough 0
    assert metrics.max_drawdown([-1, -1, -1]) == 3.0               # streak from the starting equity
    assert metrics.max_drawdown([]) == 0.0 and metrics.max_drawdown([2, 3]) == 0.0


def test_fees_are_inside_pnl_so_net_metrics_see_them():
    gross = [10.0, -10.0, 10.0, -10.0]
    net = [g - 1.0 for g in gross]                                 # $1 cost per trade
    assert metrics.profit_factor(gross) == 1.0
    assert metrics.profit_factor(net) == pytest.approx(18 / 22)    # 2*9 / 2*11


def test_legs_of_one_entry_are_one_position():
    legs = [leg(8.0, 8.0, entry=1, exit_=5), leg(-3.0, 2.0, entry=1, exit_=9), leg(-4.0, 10.0, entry=20, exit_=30)]
    pos = metrics.aggregate_positions(legs)
    assert len(pos) == 2
    assert pos[0]["pnl"] == 5.0 and pos[0]["risk_amount"] == 10.0 and pos[0]["exit_time"] == 9 and pos[0]["legs"] == 2
    assert [round(x, 4) for x in metrics.r_multiples(pos)] == [0.5, -0.4]


def test_zero_and_one_trade_inputs_do_not_crash():
    assert metrics.aggregate_positions([]) == []
    one = metrics.aggregate_positions([leg(2.0, 1.0)])
    assert metrics.t_stat(metrics.r_multiples(one)) is None
    assert metrics.profit_factor([p["pnl"] for p in one]) == float("inf")


def two_leg_book(n=60):
    """Daily-Liquidity-Scalping in miniature: 80 % leg wins +1.2 R of its risk, the 20 % remainder leg either stops at -1 R (risk 2) or hits +2.7 R.
    Money result is negative while the per-LEG R average is positive."""
    legs = []
    for i in range(n):
        t0 = 1000 + i * 10
        legs.append(leg(0.9, 8.0, entry=t0, exit_=t0 + 1))          # partial TP leg: small win in money (+0.9 on risk 8)
        if i % 3 == 0:
            legs.append(leg(5.4, 2.0, entry=t0, exit_=t0 + 5))                        # remainder: +2.7 R of its small risk
        else:
            legs.append(leg(-9.0, 10.0, entry=t0, exit_=t0 + 5))                      # stop-out with the big risk of the whole entry
    return legs


def test_leg_average_r_would_mislead_but_position_metrics_do_not():
    legs = two_leg_book()
    leg_r = [l["pnl"] / l["risk_amount"] for l in legs]
    assert sum(leg_r) / len(leg_r) > 0 and sum(l["pnl"] for l in legs) < 0     # the old (per-leg) view: "positive", while money is negative
    pos = metrics.aggregate_positions(legs)
    assert len(pos) == 60 and sum(p["pnl"] for p in pos) == pytest.approx(sum(l["pnl"] for l in legs))
    assert metrics.t_stat(metrics.r_multiples(pos)) < 0                         # position view agrees with the money


def test_analyzer_counts_positions_and_agrees_in_sign_with_money():
    legs = [dict(l, symbol=None) for l in two_leg_book()]
    for l in legs:
        l.pop("symbol")
    by_coin = {"X": {"trades": legs, "start_ms": 0, "end_ms": 10_000}}
    edges = [0, 2500, 5000, 7500, 10_000]
    res = protocol_analyze.analyze_strategy("sid", by_coin, 0, 10_000, edges)
    assert res["trades"] == 60                                                  # positions, not 100 legs
    assert res["pf_x1"] < 1.0 and res["t_stat"] < 0 and res["net_total"] < 0

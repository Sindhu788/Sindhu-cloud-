from datetime import datetime, timezone

from paper_trading import signal_rules as sr

# the 6 signals actually sent from Cloud (docs/SIGNAL_QUALITY.md section 2): id, time, coin, side, entry, stop, target
SENT = [
    (56, "2026-11-03T19:12:00+00:00", "PUMPUSDT", "long", 0.004274, 0.003927, 0.007708),
    (57, "2026-11-03T21:33:00+00:00", "BTCUSDT", "long", 77944.32, 76377.30, 92929.01),
    (60, "2026-11-03T21:38:00+00:00", "BTCUSDT", "short", 77833.30, 79065.66, 74385.43),
    (65, "2026-11-04T03:46:00+00:00", "ETHUSDT", "long", 2243.73, 2208.73, 2341.57),
    (68, "2026-11-04T08:42:00+00:00", "ETHUSDT", "short", 2324.77, 2362.99, 2217.55),
    (70, "2026-11-04T08:55:00+00:00", "ZECUSDT", "short", 1290.46, 1312.67, 1227.95),
]


def pos(row):
    _, _, sym, side, e, sl, tp = row
    return {"symbol": sym, "direction": side, "entry_price": e, "stop_loss": sl, "take_profit": tp}


def test_everything_is_off_by_default():
    assert sr.opposite_window_minutes({}) is None and sr.max_target_stop_ratio({}) is None
    for row in SENT:
        assert sr.check_target_stop_cap(pos(row), env={})[0] is True
        assert sr.check_opposite_direction(pos(row), lambda *a: "someone", env={})[0] is True


def test_flag_parsing_and_defaults():
    assert sr.opposite_window_minutes({"SINDHU_BLOCK_OPPOSITE_SIGNAL": "1"}) == 30
    assert sr.opposite_window_minutes({"SINDHU_BLOCK_OPPOSITE_SIGNAL": "on", "SINDHU_OPPOSITE_SIGNAL_WINDOW_MIN": "10"}) == 10
    assert sr.opposite_window_minutes({"SINDHU_BLOCK_OPPOSITE_SIGNAL": "1", "SINDHU_OPPOSITE_SIGNAL_WINDOW_MIN": "junk"}) == 30
    assert sr.opposite_window_minutes({"SINDHU_BLOCK_OPPOSITE_SIGNAL": "0"}) is None
    assert sr.max_target_stop_ratio({"SINDHU_MAX_TARGET_STOP_RATIO": "5"}) == 5.0
    assert sr.max_target_stop_ratio({"SINDHU_MAX_TARGET_STOP_RATIO": "0"}) is None
    assert sr.max_target_stop_ratio({"SINDHU_MAX_TARGET_STOP_RATIO": "abc"}) is None


def test_target_to_stop_ratio_known_values():
    assert abs(sr.target_stop_ratio({"entry_price": 100, "stop_loss": 95, "take_profit": 110}) - 2.0) < 1e-12
    assert abs(sr.target_stop_ratio({"entry_price": 100, "stop_loss": 105, "take_profit": 90}) - 2.0) < 1e-12     # short
    assert sr.target_stop_ratio({"entry_price": 100, "stop_loss": 100, "take_profit": 110}) is None             # zero risk
    assert sr.target_stop_ratio({"entry_price": 100}) is None


def test_cap_blocks_only_the_two_extreme_targets_of_the_six_sent_signals():
    env = {"SINDHU_MAX_TARGET_STOP_RATIO": "5"}
    blocked = [r[0] for r in SENT if not sr.check_target_stop_cap(pos(r), env=env)[0]]
    assert blocked == [56, 57]
    ok, reason = sr.check_target_stop_cap(pos(SENT[1]), env=env)
    assert not ok and "9.6" in reason


def test_opposite_rule_blocks_only_the_five_minute_btc_pair_with_the_default_window():
    env = {"SINDHU_BLOCK_OPPOSITE_SIGNAL": "1"}
    sent_log = []                                  # (time, coin, side) of signals already sent

    def lookup_at(now):
        def lookup(symbol, direction, since_iso):
            for t, c, d in sent_log:
                if c == symbol and d == direction and t.isoformat() >= since_iso:
                    return "Earlier Strategy"
            return None
        return lookup

    blocked = []
    for row in SENT:
        now = datetime.fromisoformat(row[1])
        ok, _ = sr.check_opposite_direction(pos(row), lookup_at(now), now=now, env=env)
        if ok:
            sent_log.append((now, row[2], row[3]))
        else:
            blocked.append(row[0])
    assert blocked == [60]                                      # BTC long 21:33 -> BTC short 21:38
    # a 6-hour window would also have blocked the ETH pair (04:56 apart)
    sent_log.clear(); blocked.clear()
    env6 = dict(env, SINDHU_OPPOSITE_SIGNAL_WINDOW_MIN="360")
    for row in SENT:
        now = datetime.fromisoformat(row[1])
        ok, _ = sr.check_opposite_direction(pos(row), lookup_at(now), now=now, env=env6)
        (sent_log.append((now, row[2], row[3])) if ok else blocked.append(row[0]))
    assert blocked == [60, 68]


def test_same_direction_and_missing_fields_never_block():
    env = {"SINDHU_BLOCK_OPPOSITE_SIGNAL": "1"}
    calls = []
    sr.check_opposite_direction({"symbol": "X", "direction": "long"}, lambda s, d, i: calls.append(d), env=env)
    assert calls == ["short"]                                   # it asks about the OPPOSITE side only
    assert sr.check_opposite_direction({"symbol": None, "direction": "long"}, lambda *a: "x", env=env)[0] is True
    assert sr.check_opposite_direction({"symbol": "X", "direction": "weird"}, lambda *a: "x", env=env)[0] is True

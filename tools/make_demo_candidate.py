"""Builds the documented DEMO candidate used to prove the candidate workflow (Day 7 Step 14): '4h breakout above the 20-bar high while price is above the SMA(50),
long only, ATR stop and target'. Written into a scratch library (never the real library). Usage: python tools/make_demo_candidate.py <scratch_library_dir>"""
import copy, json, os, shutil, sys

SRC = r"D:\sindhu_runtime\strategy_library\125a27fc0a6e"
CID = "demo4hbreak01"


def main(lib):
    dst = os.path.join(lib, CID)
    if os.path.exists(dst):
        print("exists:", dst); return dst
    shutil.copytree(SRC, dst)
    meta = json.load(open(os.path.join(dst, "meta.json"), encoding="utf-8"))
    meta.update(id=CID, name="DEMO candidate: 4h breakout above SMA50 (long only)", tags=["demo_candidate", "4h", "breakout"], backtest_snapshot=None)
    json.dump(meta, open(os.path.join(dst, "meta.json"), "w", encoding="utf-8"), indent=1)
    vp = os.path.join(dst, "versions", "v1.json")
    cfg = json.load(open(vp, encoding="utf-8"))
    cfg["name"] = meta["name"]
    cfg["raw_text"] = "Demo candidate for the Day 7 workflow test: buy when the close is above the SMA(50) and breaks above the highest high of the last 20 candles, 4h chart, long only, stop 2 ATR, target 4 ATR."
    cfg["timeframes"] = {"entry": "4h"}
    for ind in cfg["indicators"]:
        if ind["name"] == "sma":
            ind["params"]["period"] = 50
    cond = []
    for c in cfg["long_entry_conditions"]:
        c = copy.deepcopy(c)
        if c.get("indicator") == "sma":
            c["params"] = {"period": 50}
        cond.append(c)
    cfg["long_entry_conditions"] = [c for c in cond if c.get("indicator") in ("sma", "highest_high")]
    cfg["short_entry_conditions"] = []
    cfg["stop_loss"] = {"type": "atr_multiple", "value": 2.0, "level": None, "atr_period": 14}
    cfg["take_profit"] = {"type": "atr_multiple", "value": 4.0, "level": None, "atr_period": 14}
    cfg["risk_pct"] = 1.0
    cfg["tags"] = ["demo_candidate", "4h", "breakout"]
    json.dump(cfg, open(vp, "w", encoding="utf-8"), indent=1)
    print("built", dst)
    return dst


if __name__ == "__main__":
    main(sys.argv[1])

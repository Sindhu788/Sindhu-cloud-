"""Day 6 Step 16: does the stored confidence predict wins? Read-only on the local paper_positions (closed trades). Chronological split only (train on the
older part, test on the newer part); numpy only. Usage: python tools/confidence_analysis.py"""
import sqlite3, json
import numpy as np

c = sqlite3.connect("file:D:/sindhu/data/database/sindhu.db?mode=ro", uri=True, timeout=10)
rows = c.execute("select entry_time, confidence, pnl, direction, market_state, session, timeframe, strategy_id, exit_reason from paper_positions "
                 "where status='closed' and confidence is not null and pnl is not null order by entry_time").fetchall()
t = [r[0] for r in rows]; conf = np.array([float(r[1]) for r in rows]); y = np.array([1.0 if r[2] > 0 else 0.0 for r in rows])
n = len(y); print("closed trades with confidence:", n, "| entry range", __import__("datetime").datetime.utcfromtimestamp(rows[0][0]/1000 if rows[0][0] > 1e11 else rows[0][0]).date(), "->", __import__("datetime").datetime.utcfromtimestamp(rows[-1][0]/1000 if rows[-1][0] > 1e11 else rows[-1][0]).date(), "| base win rate", round(y.mean(), 4))
print("confidence: min %.1f median %.1f max %.1f | distinct values %d" % (conf.min(), np.median(conf), conf.max(), len(set(conf.round(1)))))

def auc(score, label):
    s = np.asarray(score, float); l = np.asarray(label)
    if l.sum() == 0 or l.sum() == len(l): return float("nan")
    order = np.argsort(s, kind="mergesort"); ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
    # average ranks for ties
    for v in np.unique(s):
        m = s == v
        if m.sum() > 1: ranks[m] = ranks[m].mean()
    n1 = l.sum(); n0 = len(l) - n1
    return float((ranks[l == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def brier(p, label): return float(np.mean((np.asarray(p) - label) ** 2))

def boot_auc(score, label, nb=500, seed=1):
    rng = np.random.default_rng(seed); v = []
    for _ in range(nb):
        i = rng.integers(0, len(label), len(label)); a = auc(score[i], label[i])
        if a == a: v.append(a)
    return np.percentile(v, [2.5, 97.5]).round(3).tolist()

cut = int(n * 0.6); tr, te = slice(0, cut), slice(cut, n)
print("train n=%d (win %.3f) | test n=%d (win %.3f)" % (cut, y[tr].mean(), n - cut, y[te].mean()))
base = y[tr].mean()
print("TEST raw confidence : AUC %.3f CI95 %s | Brier %.4f (constant base-rate guess %.4f)" % (auc(conf[te], y[te]), boot_auc(conf[te], y[te]), brier(conf[te] / 100, y[te]), brier(np.full(n - cut, base), y[te])))
print("ALL  raw confidence : AUC %.3f CI95 %s" % (auc(conf, y), boot_auc(conf, y)))

# (1) recalibrate confidence alone: 10-wide buckets learned on the train part
b = (conf // 10).astype(int); rate = {k: (y[tr][b[tr] == k].mean(), (b[tr] == k).sum()) for k in np.unique(b[tr])}
p1 = np.array([rate[k][0] if k in rate and rate[k][1] >= 25 else base for k in b[te]])
print("TEST bucket recalibration of confidence: AUC %.3f | Brier %.4f" % (auc(p1, y[te]), brier(p1, y[te])))

# (2) logistic regression on simple, outcome-free features known at entry (trained on the older 60 %)
def onehot(vals, keep):
    return np.array([[1.0 if v == k else 0.0 for k in keep] for v in vals])
dirs = [r[3] for r in rows]; ms = [r[4] for r in rows]; ses = [r[5] for r in rows]; tf = [r[6] for r in rows]
keep_ms = sorted({m for m in ms[:cut] if m})[:6]; keep_ses = sorted({m for m in ses[:cut] if m})[:6]
X = np.column_stack([np.ones(n), (conf - conf[tr].mean()) / (conf[tr].std() + 1e-9), onehot(dirs, ["bullish", "long"]), onehot(ms, keep_ms), onehot(ses, keep_ses)])
def fit(X, y, l2=5.0, it=50):
    w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ w)); g = X.T @ (p - y) + l2 * w; H = (X.T * (p * (1 - p))) @ X + l2 * np.eye(len(w))
        w -= np.linalg.solve(H, g)
    return w
w = fit(X[tr], y[tr]); p2 = 1 / (1 + np.exp(-X[te] @ w))
print("TEST logistic (confidence + direction + market_state + session): AUC %.3f CI95 %s | Brier %.4f" % (auc(p2, y[te]), boot_auc(p2, y[te]), brier(p2, y[te])))
# which single factors separate wins in the TEST part?
for name, vals in (("direction", dirs), ("market_state", ms), ("session", ses)):
    d = {}
    for v, yy in zip(np.array(vals, dtype=object)[te], y[te]): d.setdefault(v, []).append(yy)
    print(name, {k: (len(v), round(float(np.mean(v)), 3)) for k, v in sorted(d.items(), key=lambda kv: -len(kv[1]))[:6]})
# per-strategy: confidence is partly a per-strategy constant (version bonus) -> how much of its variance is between strategies?
sid = np.array([r[7] for r in rows]); means = {s: conf[sid == s].mean() for s in np.unique(sid)}
between = np.var([means[s] for s in sid]); print("share of confidence variance explained by the strategy alone: %.2f" % (between / np.var(conf)))

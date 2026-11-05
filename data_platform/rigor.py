"""Statistical rigour layer (Day 6 Step 6). numpy only. Nothing here changes a strategy; it only makes the verdict harder to fool.

1. cluster_bootstrap(): confidence intervals for profit factor and mean per position, resampling whole DAYS (trades on one day/coin set are not
   independent, so a per-trade bootstrap would be too optimistic).
2. bh_fdr(): Benjamini-Hochberg false-discovery-rate control across the 42 strategies (a "lucky" strategy is not called robust).
3. null_returns(): RANDOM-ENTRY NULL MODEL. Same side mix, same holding times (time in market) and same round-trip costs as the strategy, but entries
   at random times on the same coin. The strategy's mean net return per position is compared with the null distribution (one-sided p-value).
   Limitation (stated in docs): the null reproduces the strategy's holding TIME, not its stop/target path, so it tests "does the entry timing add
   anything over luck" with the exit timing held fixed.
4. Baselines (same cost model): buy_and_hold(), sma_cross_4h(), rsi_reversion_1h().
Labelling rules that use these live in protocol_analyze.py (ROBUST needs: PF CI lower bound > 1, null-model p < 0.05, BH-FDR pass, beats baselines).
"""
import numpy as np


def _rng(seed):
    return np.random.default_rng(seed)


def cluster_bootstrap(pnl, cluster_ids, n_boot=2000, seed=0, alpha=0.05):
    """pnl: money per position; cluster_ids: any hashable per position (e.g. exit day). Returns dict with pf/mean point values and (lo, hi) intervals."""
    pnl = np.asarray(pnl, dtype=float)
    if len(pnl) == 0:
        return {"n": 0, "pf": 0.0, "pf_ci": (None, None), "mean": 0.0, "mean_ci": (None, None), "clusters": 0}
    uniq, inv = np.unique(np.asarray(cluster_ids), return_inverse=True)
    k = len(uniq)
    gp = np.bincount(inv, weights=np.where(pnl > 0, pnl, 0.0), minlength=k)
    gl = np.bincount(inv, weights=np.where(pnl < 0, -pnl, 0.0), minlength=k)
    sm = np.bincount(inv, weights=pnl, minlength=k)
    cnt = np.bincount(inv, minlength=k).astype(float)
    rng = _rng(seed)
    idx = rng.integers(0, k, size=(n_boot, k))
    bgp, bgl, bsm, bcnt = gp[idx].sum(1), gl[idx].sum(1), sm[idx].sum(1), cnt[idx].sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        bpf = np.where(bgl > 0, bgp / bgl, np.where(bgp > 0, np.inf, 0.0))
        bmean = bsm / bcnt
    lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)
    point_pf = float(gp.sum() / gl.sum()) if gl.sum() > 0 else (float("inf") if gp.sum() > 0 else 0.0)
    return {"n": int(len(pnl)), "clusters": int(k), "pf": point_pf, "pf_ci": (float(np.percentile(bpf, lo)), float(np.percentile(bpf, hi))),
            "mean": float(pnl.mean()), "mean_ci": (float(np.percentile(bmean, lo)), float(np.percentile(bmean, hi)))}


def bh_fdr(pvalues, q=0.05):
    """Benjamini-Hochberg. Returns a boolean array: True = discovery that survives false-discovery-rate control at level q."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    if m == 0:
        return np.array([], dtype=bool)
    order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    keep = np.zeros(m, dtype=bool)
    if passed.any():
        keep[order[: np.max(np.nonzero(passed)[0]) + 1]] = True
    return keep


def null_returns(times, closes, durations_ms, sides, rt_cost_pct, n_sims=1000, seed=0, window=None):
    """Random-entry null for ONE coin. times/closes: 1-minute grid (sorted, ms / price). durations_ms and sides (+1 long, -1 short) come from the
    strategy's positions on this coin. Returns an array (n_sims,) of the MEAN NET return per position (fraction, e.g. 0.001 = 0.1 %) of a random
    book with the same number of positions, side mix, durations and round-trip cost. `window` = (start_ms, end_ms) allowed entry range."""
    times = np.asarray(times); closes = np.asarray(closes, dtype=float)
    dur = np.asarray(durations_ms, dtype=np.int64); sd = np.asarray(sides, dtype=float)
    n = len(dur)
    if n == 0 or len(times) < 2:
        return np.zeros(n_sims)
    lo, hi = (times[0], times[-1]) if window is None else window
    rng = _rng(seed)
    out = np.empty(n_sims)
    for s in range(n_sims):
        latest = np.maximum(hi - dur, lo + 1)
        entry = lo + (rng.random(n) * (latest - lo)).astype(np.int64)
        ie = np.clip(np.searchsorted(times, entry, side="left"), 0, len(times) - 1)
        ix = np.clip(np.searchsorted(times, entry + dur, side="left"), 0, len(times) - 1)
        gross = sd * (closes[ix] / closes[ie] - 1.0)
        out[s] = float((gross - rt_cost_pct / 100.0).mean())
    return out


def one_sided_p(observed, null):
    """P(null >= observed), with the +1 correction so p is never exactly 0."""
    null = np.asarray(null)
    return float((np.sum(null >= observed) + 1) / (len(null) + 1))


def _net_from_trades(rets, rt_cost_pct):
    r = np.asarray(rets, dtype=float) - rt_cost_pct / 100.0
    gp, gl = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": int(len(r)), "mean_net": float(r.mean()) if len(r) else 0.0, "pf": float(gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0),
            "total": float(r.sum())}


def buy_and_hold(closes, rt_cost_pct):
    """One long position over the whole period; net of one round trip."""
    c = np.asarray(closes, dtype=float)
    return {"return": float(c[-1] / c[0] - 1.0 - rt_cost_pct / 100.0)}


def _sma(x, n):
    c = np.cumsum(np.insert(np.asarray(x, dtype=float), 0, 0.0))
    out = np.full(len(x), np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def sma_cross_4h(closes_4h, rt_cost_pct, fast=20, slow=50):
    """Long when SMA(fast) > SMA(slow), flat otherwise; trades on the NEXT bar's open is approximated by the next close (conservative: signal at bar i
    uses closes up to i, position return is taken from close i to the close when the signal ends)."""
    c = np.asarray(closes_4h, dtype=float)
    f, s = _sma(c, fast), _sma(c, slow)
    on = (f > s) & ~np.isnan(s)
    rets, entry = [], None
    for i in range(len(c)):
        if on[i] and entry is None:
            entry = c[i]
        elif not on[i] and entry is not None:
            rets.append(c[i] / entry - 1.0); entry = None
    if entry is not None:
        rets.append(c[-1] / entry - 1.0)
    return _net_from_trades(rets, rt_cost_pct)


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = np.zeros(len(c)), np.zeros(len(c))
    if len(c) <= n:
        return np.full(len(c), np.nan)
    au[n], ad[n] = up[1:n + 1].mean(), dn[1:n + 1].mean()
    for i in range(n + 1, len(c)):
        au[i] = (au[i - 1] * (n - 1) + up[i]) / n
        ad[i] = (ad[i - 1] * (n - 1) + dn[i]) / n
    rs = np.where(ad > 0, au / np.where(ad > 0, ad, 1), np.inf)
    out = 100 - 100 / (1 + rs)
    out[:n] = np.nan
    return out


def rsi_reversion_1h(closes_1h, rt_cost_pct, buy_below=30.0, exit_above=50.0):
    """Long-only mean reversion: buy when RSI(14) < 30, sell when RSI > 50."""
    c = np.asarray(closes_1h, dtype=float)
    r = _rsi(c)
    rets, entry = [], None
    for i in range(len(c)):
        if np.isnan(r[i]):
            continue
        if entry is None and r[i] < buy_below:
            entry = c[i]
        elif entry is not None and r[i] > exit_above:
            rets.append(c[i] / entry - 1.0); entry = None
    return _net_from_trades(rets, rt_cost_pct)

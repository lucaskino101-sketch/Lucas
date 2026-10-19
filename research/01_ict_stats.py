"""Exploratory statistics that test ICT claims mechanically (IN-SAMPLE ONLY: 2005-2014).

Outputs go to results/research/01_*.csv and stdout.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ictmodel.data import load_m1  # noqa: E402
from ictmodel.sessions import add_time_keys, daily_levels  # noqa: E402

IS_START, IS_END = "2005-01-01", "2015-01-01"
OUT = os.path.join(ROOT, "results", "research")


def tod_extremes(df, day):
    """Bucket (30 min) of the RTH high and low, split by up/down RTH days."""
    rth = df[(df["mod"] >= 570) & (df["mod"] < 960)]
    hi_t = rth.groupby("tday")["high"].idxmax()
    lo_t = rth.groupby("tday")["low"].idxmin()
    b = lambda ts: (ts.hour * 60 + ts.minute - 570) // 30
    up = (day["rth_close"] > day["rth_open"]).reindex(hi_t.index)
    res = pd.DataFrame({
        "bucket": [f"{(570 + 30 * k) // 60:02d}:{(570 + 30 * k) % 60:02d}" for k in range(13)],
    })
    hb, lb = b(pd.DatetimeIndex(hi_t.values)), b(pd.DatetimeIndex(lo_t.values))
    for name, mask in (("all", np.ones(len(up), bool)), ("up", up.values), ("down", ~up.values)):
        res[f"HOD_{name}%"] = np.bincount(hb[mask], minlength=13)[:13] / mask.sum() * 100
        res[f"LOD_{name}%"] = np.bincount(lb[mask], minlength=13)[:13] / mask.sum() * 100
    return res


def sweep_reclaim_stats(df, day, level_cols, side, start=570, end=690, reclaim_within=15,
                        exit_mod=960, rr=2.0):
    """For each level: first sweep in [start,end), reclaim (close back through) within N bars.

    side='low' -> level is support-side liquidity (sell-side), we study longs after sweep+reclaim.
    Trade sim: entry=reclaim close, stop=sweep extreme, target=rr*R, else exit at exit_mod close.
    Conservative: if stop and target in same bar -> stop.
    """
    rows = []
    days = df.groupby("tday")
    atr = (day["day_high"] - day["day_low"]).rolling(14).mean().shift(1)
    for tday, g in days:
        if tday not in day.index:
            continue
        lv = day.loc[tday]
        mod = g["mod"].to_numpy()
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        rth_idx = np.where((mod >= 570) & (mod < exit_mod))[0]
        if len(rth_idx) < 300 or not np.isfinite(atr.get(tday, np.nan)):
            continue
        a = atr[tday]
        for col in level_cols:
            L = lv[col]
            if not np.isfinite(L):
                continue
            # must start the window on the right side of the level
            first = rth_idx[0]
            if side == "low" and o[first] <= L:
                continue
            if side == "high" and o[first] >= L:
                continue
            win = rth_idx[(mod[rth_idx] >= start) & (mod[rth_idx] < end)]
            hit = win[(l[win] < L) if side == "low" else (h[win] > L)]
            if len(hit) == 0:
                rows.append(dict(tday=tday, level=col, swept=0))
                continue
            i = hit[0]
            # find reclaim
            j_end = min(i + reclaim_within, rth_idx[-1])
            ext = l[i] if side == "low" else h[i]
            rec = None
            for j in range(i, j_end + 1):
                ext = min(ext, l[j]) if side == "low" else max(ext, h[j])
                if (side == "low" and c[j] > L) or (side == "high" and c[j] < L):
                    rec = j
                    break
            row = dict(tday=tday, level=col, swept=1, sweep_mod=mod[i], reclaimed=int(rec is not None),
                       depth_atr=((L - ext) if side == "low" else (ext - L)) / a)
            if rec is not None:
                entry = c[rec]
                stop = ext
                risk = (entry - stop) if side == "low" else (stop - entry)
                row["risk_atr"] = risk / a
                if risk > 0:
                    tgt = entry + rr * risk if side == "low" else entry - rr * risk
                    R = None
                    for k in range(rec + 1, rth_idx[-1] + 1):
                        if side == "low":
                            if l[k] <= stop: R = -1.0; break
                            if h[k] >= tgt: R = rr; break
                        else:
                            if h[k] >= stop: R = -1.0; break
                            if l[k] <= tgt: R = rr; break
                    if R is None:
                        last = rth_idx[-1]
                        R = ((c[last] - entry) if side == "low" else (entry - c[last])) / risk
                    row["R"] = R
                    fwd = c[rth_idx[-1]] - entry
                    row["fwd_close_atr"] = (fwd if side == "low" else -fwd) / a
            rows.append(row)
    return pd.DataFrame(rows)


def summarize(t):
    out = []
    for lvl, g in t.groupby("level"):
        s = g[g.swept == 1]
        r = s[s.reclaimed == 1]
        rr = r.dropna(subset=["R"])
        out.append(dict(level=lvl, days=len(g), swept_pct=100 * len(s) / max(len(g), 1),
                        reclaim_pct=100 * len(r) / max(len(s), 1), n_trades=len(rr),
                        win_pct=100 * (rr.R > 0).mean() if len(rr) else np.nan,
                        avg_R=rr.R.mean() if len(rr) else np.nan,
                        fwd_close_atr=r.fwd_close_atr.mean() if len(r) else np.nan,
                        med_depth_atr=s.depth_atr.median()))
    return pd.DataFrame(out)


if __name__ == "__main__":
    inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
    df = add_time_keys(load_m1(inst, IS_START, IS_END))
    day = daily_levels(df)
    pd.set_option("display.width", 200)

    tod = tod_extremes(df, day)
    tod.to_csv(os.path.join(OUT, f"01_tod_extremes_{inst}.csv"), index=False)
    print(f"\n### {inst} time-of-day of RTH high/low (IS 2005-2014), % of days")
    print(tod.round(1).to_string(index=False))

    lows = ["onl", "pdl", "asia_low", "london_low", "pre_low", "prev_rth_low", "pwl"]
    highs = ["onh", "pdh", "asia_high", "london_high", "pre_high", "prev_rth_high", "pwh"]
    for side, cols in (("low", lows), ("high", highs)):
        t = sweep_reclaim_stats(df, day, cols, side)
        t.to_csv(os.path.join(OUT, f"01_sweeps_{side}_{inst}.csv"), index=False)
        print(f"\n### {inst} NY-AM (9:30-11:30) sweep of {side}-side levels -> reclaim within 15m -> fade, stop=sweep extreme, 2R target, exit 16:00")
        print(summarize(t).round(3).to_string(index=False))

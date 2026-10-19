"""Anatomy of the regime-gated continuation candidate (IN-SAMPLE ONLY)."""
import sys

import numpy as np
import pandas as pd

from common import Params, days_for, evaluate

LO = ("onl", "pdl", "pre_low", "asia_low", "london_low", "prev_rth_low")
HI = ("onh", "pdh", "pre_high", "asia_high", "london_high", "prev_rth_high")
for inst, cost in (("NAS100_USD", 1.0), ("SPX500_USD", 0.5)):
    days = days_for(inst, "IS")
    atr = pd.Series([d.atr for d in days], index=pd.DatetimeIndex([d.tday for d in days]))
    ratio = atr / atr.rolling(100, min_periods=50).mean()
    ps = {"ce/level/eod": Params(mode="continuation", tf=15, entry_at="ce", stop_mode="level", target="eod",
                                 cost_pts=cost, sweep_levels=LO, target_levels=HI, min_risk_atr=0.05,
                                 max_risk_atr=0.6, sweep_end=690, entry_end=720),
          "edge/level/rr3": Params(mode="continuation", tf=15, entry_at="edge", stop_mode="level", target="rr",
                                   rr=3.0, cost_pts=cost, sweep_levels=LO, target_levels=HI, min_risk_atr=0.05,
                                   max_risk_atr=0.6, sweep_end=690, entry_end=720)}
    res = evaluate(list(ps.values()), inst=inst, keep_trades=True)
    for (name, p), r in zip(ps.items(), res):
        t = r["trades"]
        t = t.assign(ratio=ratio.reindex(pd.to_datetime(t.tday)).to_numpy())
        s = t[t.ratio >= 1.1].copy()
        s["year"] = pd.to_datetime(s.tday).dt.year
        R = s.r_net
        top = R.sort_values(ascending=False)
        print(f"\n##### {inst} {name} gate>=1.1: n={len(s)} E={R.mean():+.3f} median={R.median():+.2f} "
              f"win={100*(R>0).mean():.1f}% sum={R.sum():+.1f}R | sum without top5 = {top.iloc[5:].sum():+.1f}R "
              f"| top5 = {list(top.iloc[:5].round(1))}")
        print("  long :", f"n={int((s.side==1).sum())} E={s[s.side==1].r_net.mean():+.3f}",
              "| short:", f"n={int((s.side==-1).sum())} E={s[s.side==-1].r_net.mean():+.3f}")
        print("  avg risk (ATR):", round((s.risk / s.atr).mean(), 3), " exit reasons:", s.reason.value_counts().to_dict())
        print(s.groupby("year").r_net.agg(["size", "sum", "mean"]).round(2).T.to_string())

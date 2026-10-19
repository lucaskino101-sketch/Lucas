"""ICT Market-Maker sequence: opposite-side raid FIRST, then breakaway continuation (IN-SAMPLE ONLY)."""
import itertools
import sys

import numpy as np
import pandas as pd

from common import Params, days_for, evaluate
from ictmodel.metrics import summarize

LO = ("onl", "pdl", "pre_low", "asia_low", "london_low", "prev_rth_low")
HI = ("onh", "pdh", "pre_high", "asia_high", "london_high", "prev_rth_high")
for inst, cost in (("NAS100_USD", 1.0), ("SPX500_USD", 0.5)):
    days = days_for(inst, "IS")
    atr = pd.Series([d.atr for d in days], index=pd.DatetimeIndex([d.tday for d in days]))
    ratio = atr / atr.rolling(100, min_periods=50).mean()
    variants, labels = [], []
    for tf, ea, sm, tgt, opp in itertools.product((5, 15), ("edge", "ce"), ("level", "fvg"), ("eod", "rr3"), (False, True)):
        kw = dict(mode="continuation", tf=tf, entry_at=ea, stop_mode=sm, cost_pts=cost, sweep_levels=LO,
                  target_levels=HI, min_risk_atr=0.05, max_risk_atr=0.6, sweep_end=690, entry_end=720,
                  need_opp_sweep=opp)
        kw.update(dict(target="rr", rr=3.0) if tgt == "rr3" else dict(target="eod"))
        variants.append(Params(**kw))
        labels.append(f"{inst[:3]} tf={tf:2d} {ea:4s} {sm:5s} {tgt:4s} opp={int(opp)}")
    res = evaluate(variants, inst=inst, keep_trades=True)
    for r, lab in zip(res, labels):
        t = r["trades"]
        t = t.assign(ratio=ratio.reindex(pd.to_datetime(t.tday)).to_numpy())
        out = []
        for th in (0.0, 1.1):
            s = t[t.ratio >= th]
            y = pd.to_datetime(s.tday).dt.year
            if len(s) < 5:
                out.append(f"th={th}: n<5"); continue
            top = s.r_net.sort_values(ascending=False)
            out.append(f"th={th:.1f}: n={len(s):4d} E={s.r_net.mean():+.3f} t={s.r_net.mean()/s.r_net.std()*np.sqrt(len(s)):+.1f} "
                       f"H1={s[y<2010].r_net.mean():+.2f} H2={s[y>=2010].r_net.mean():+.2f} ex-top5={top.iloc[5:].mean():+.3f}")
        print(f"{lab} | " + " | ".join(out))

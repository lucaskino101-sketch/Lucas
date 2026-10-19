"""Volatility-regime gate for the continuation model (IN-SAMPLE ONLY).

Regime = ATR14 / ATR100 of daily ranges, known before the day starts. Because the
gate is per day and days are independent in the engine, filtering trades by the
day's regime is identical to not trading on gated days.
"""
import itertools
import sys

import numpy as np
import pandas as pd

from common import Params, days_for, evaluate
from ictmodel.metrics import summarize

inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
cost = {"NAS100_USD": 1.0, "SPX500_USD": 0.5}[inst]
LO = ("onl", "pdl", "pre_low", "asia_low", "london_low", "prev_rth_low")
HI = ("onh", "pdh", "pre_high", "asia_high", "london_high", "prev_rth_high")
variants, labels = [], []
for tf, ea, sm, tgt in itertools.product((5, 15), ("edge", "ce"), ("level", "fvg"), ("eod", "rr3", "eod_be")):
    kw = dict(mode="continuation", tf=tf, entry_at=ea, stop_mode=sm, cost_pts=cost, sweep_levels=LO,
              target_levels=HI, min_risk_atr=0.05, max_risk_atr=0.6, sweep_end=690, entry_end=720)
    kw.update(dict(target="rr", rr=3.0) if tgt == "rr3" else dict(target="eod", be_at_r=1.0 if tgt == "eod_be" else 0.0))
    variants.append(Params(**kw))
    labels.append(f"tf={tf:2d} {ea:4s} stop={sm:5s} {tgt:6s}")
res = evaluate(variants, inst=inst, keep_trades=True)
days = days_for(inst, "IS")
reg = pd.Series([d.atr for d in days], index=[d.tday for d in days])
ratio = reg / reg.rolling(100, min_periods=50).mean()
alld = pd.DatetimeIndex(reg.index)
print(f"### {inst}: continuation, net of {cost}pt; gate = ATR14/ATR100 >= theta")
for r, lab in zip(res, labels):
    t = r["trades"]
    t = t.assign(ratio=ratio.reindex(pd.to_datetime(t.tday)).to_numpy())
    out = []
    for th in (0.0, 1.0, 1.1, 1.2):
        s = t[t.ratio >= th]
        y = pd.to_datetime(s.tday).dt.year
        a = summarize(s, alld)
        out.append(f"th={th:.1f}: n={a['trades']:3d} E={a['expectancy_R']:+.2f} t={a['t_stat']:+.1f} "
                   f"H1={s[y < 2010].r_net.mean():+.2f} H2={s[y >= 2010].r_net.mean():+.2f}")
    print(f"{lab} | " + " | ".join(out))

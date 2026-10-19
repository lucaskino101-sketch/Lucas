"""Frozen EBM on markets never used to develop it: EUR/USD, GBP/USD, XAU/USD, 2005-2020.

Same rules; costs in price units; risk floor = 2 x conservative cost (the rule used for NQ/ES).
"""
import os

import pandas as pd

from common import ROOT, evaluate
from ictmodel.model import ebm

FX = {"EUR_USD": (0.00010, 0.00006, 0.00001), "GBP_USD": (0.00015, 0.00009, 0.00001), "XAU_USD": (0.40, 0.25, 0.01)}
rows = []
for inst, (cons, real, tick) in FX.items():
    for cname, c in (("conservative", cons), ("realistic", real)):
        p = ebm("NAS100_USD").replace(cost_pts=c, min_risk_pts=2 * cons, tick=tick)
        for period in ("IS", "OOS"):
            a = evaluate([p], inst=inst, period=period, procs=1)[0]
            s = a["all"]
            rows.append(dict(inst=inst, cost=cname, period=period, n=s.get("trades", 0),
                             win=round(100 * s.get("win_rate", 0), 1), E=round(s.get("expectancy_R", 0), 3),
                             t=round(s.get("t_stat", 0), 2), PF=round(s.get("profit_factor", 0), 2),
                             DD=round(100 * s.get("max_dd", 0), 1)))
df = pd.DataFrame(rows)
df.to_csv(os.path.join(ROOT, "results", "holdout", "generalization_fx.csv"), index=False)
print(df.to_string(index=False))

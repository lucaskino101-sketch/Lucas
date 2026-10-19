"""DodgysDD iFVG with EQH/EQL and LRLR targets (session liquidity only as fallback)."""
import itertools
import os

import pandas as pd

from common import ROOT, evaluate
from ictmodel.model import dodgy

rows = []
grid = list(itertools.product((1, 5), ("sweep", "all"), ("close", "wick")))
for inst in ("NAS100_USD", "SPX500_USD"):
    vs = [dodgy(inst, "conservative", tf, g, "kz", st, "liq").replace(ifvg_target="eqh_lrlr", max_rr=8.0) for tf, g, st in grid]
    for period in ("IS", "OOS"):
        for (tf, g, st), r in zip(grid, evaluate(vs, inst=inst, period=period, ctx=(0, 960))):
            a = r["all"]
            rows.append(dict(inst=inst, period=period, tf=tf, grade=g, stop=st, trades=a["trades"],
                             win=round(100 * a["win_rate"], 1), E=round(a["expectancy_R"], 3),
                             gross=round(r["gross_E"], 3), t=round(a["t_stat"], 1), PF=round(a["profit_factor"], 2)))
df = pd.DataFrame(rows)
df.to_csv(os.path.join(ROOT, "results", "dodgysdd", "eqh_lrlr_summary.csv"), index=False)
base = pd.read_csv(os.path.join(ROOT, "results", "dodgysdd", "summary.csv"))
base = base[(base.cost == "conservative") & (base.session == "kz") & (base.exit == "liq") & base.grade.isin(["sweep", "all"])]
df = df.merge(base[["inst", "period", "tf", "grade", "stop", "expectancy_R"]].rename(columns={"expectancy_R": "E_old_target"}),
              on=["inst", "period", "tf", "grade", "stop"])
print(df.to_string(index=False))

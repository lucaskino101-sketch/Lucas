"""ONE-TIME holdout run (2015-01 .. 2020-05) of every pre-registered model.

Run once after freezing ictmodel/model.py. Writes results/holdout/.
"""
import json
import os

import pandas as pd

from common import ROOT, days_for, evaluate
from ictmodel.metrics import by_year, summarize
from ictmodel.model import COSTS, ebm, reference_models

OUT = os.path.join(ROOT, "results", "holdout")
rows = []
for inst in ("NAS100_USD", "SPX500_USD"):
    for cost in ("conservative", "realistic"):
        models = {"EBM (primary: hold to 15:55)": ebm(inst, cost),
                  "EBM alt: 3R target": ebm(inst, cost, "rr3"),
                  "EBM alt: breakeven at +1R": ebm(inst, cost, "eod_be")}
        models.update(reference_models(inst, cost))
        for period in ("IS", "OOS"):
            res = evaluate(list(models.values()), inst=inst, period=period, keep_trades=True)
            for (name, p), r in zip(models.items(), res):
                a = r["all"]
                rows.append(dict(inst=inst, cost=cost, period=period, model=name, **{k: a.get(k) for k in (
                    "trades", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat",
                    "profit_factor", "total_R", "cagr", "max_dd", "sharpe", "max_losing_streak")}))
                if name.startswith("EBM (primary") and len(r["trades"]):
                    tag = f"{inst}_{cost}_{period}"
                    r["trades"].to_csv(os.path.join(OUT, f"ebm_trades_{tag}.csv"), index=False)
                    by_year(r["trades"]).round(3).to_csv(os.path.join(OUT, f"ebm_by_year_{tag}.csv"))
df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT, "summary.csv"), index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 52)
for (inst, cost), g in df.groupby(["inst", "cost"], sort=False):
    print(f"\n######## {inst} | costs: {cost} ({COSTS[inst][cost]} pt round trip)")
    piv = g.pivot_table(index="model", columns="period", values=["trades", "win_rate", "expectancy_R", "t_stat",
                                                                 "profit_factor", "cagr", "max_dd", "sharpe"],
                        aggfunc="first", sort=False)
    show = pd.DataFrame({
        "IS n": piv[("trades", "IS")], "IS E(R)": piv[("expectancy_R", "IS")].round(3),
        "OOS n": piv[("trades", "OOS")], "OOS win%": (100 * piv[("win_rate", "OOS")]).round(1),
        "OOS E(R)": piv[("expectancy_R", "OOS")].round(3), "OOS t": piv[("t_stat", "OOS")].round(2),
        "OOS PF": piv[("profit_factor", "OOS")].round(2), "OOS CAGR@1%": (100 * piv[("cagr", "OOS")]).round(1),
        "OOS maxDD%": (100 * piv[("max_dd", "OOS")]).round(1), "OOS Sharpe": piv[("sharpe", "OOS")].round(2)})
    print(show.to_string())

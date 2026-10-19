"""Benchmark the DodgysDD iFVG model (all 72 pre-registered variants), 2005-2014 and 2015-2020.

Nothing here selects on results: the canonical variant was fixed in ictmodel/model.py
before this ran, and every variant is written to results/dodgysdd/summary.csv.
"""
import itertools
import os

import pandas as pd

from common import ROOT, evaluate
from ictmodel.model import dodgy

OUT = os.path.join(ROOT, "results", "dodgysdd")
GRID = list(itertools.product((1, 5), ("all", "sweep", "sweep_htf"), ("ny", "kz"), ("close", "wick"), ("liq", "rr", "rr_be")))
rows = []
for inst in ("NAS100_USD", "SPX500_USD"):
    variants = [dodgy(inst, "conservative", tf, g, s, st, ex) for tf, g, s, st, ex in GRID]
    variants.append(dodgy(inst, "realistic"))          # canonical at realistic costs
    labels = [dict(tf=tf, grade=g, session=s, stop=st, exit=ex, cost="conservative") for tf, g, s, st, ex in GRID]
    labels.append(dict(tf=1, grade="sweep", session="kz", stop="close", exit="liq", cost="realistic"))
    for period in ("IS", "OOS"):
        res = evaluate(variants, inst=inst, period=period, ctx=(0, 960), keep_trades=True)
        for lab, r in zip(labels, res):
            a = r["all"]
            canon = lab["tf"] == 1 and lab["grade"] == "sweep" and lab["session"] == "kz" and lab["stop"] == "close" and lab["exit"] == "liq"
            rows.append(dict(inst=inst, period=period, canonical=canon, **lab,
                             **{k: a.get(k) for k in ("trades", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R",
                                                      "expectancy_R", "t_stat", "profit_factor", "total_R", "cagr",
                                                      "max_dd", "sharpe")},
                             gross_E=r.get("gross_E")))
            if canon and len(r["trades"]):
                r["trades"].to_csv(os.path.join(OUT, f"canonical_trades_{inst}_{lab['cost']}_{period}.csv"), index=False)
        print(inst, period, "done", flush=True)
df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT, "summary.csv"), index=False)
pd.set_option("display.width", 250)
c = df[df.canonical]
print("\n### CANONICAL DodgysDD iFVG (1m, A+ sweep, killzones, close-stop, liquidity target)")
print(c[["inst", "cost", "period", "trades", "trades_per_year", "win_rate", "expectancy_R", "gross_E", "t_stat",
         "profit_factor", "max_dd"]].round(3).to_string(index=False))
v = df[df.cost == "conservative"]
print("\n### All 72 variants, conservative costs: distribution of expectancy (R/trade)")
print(v.groupby(["inst", "period"]).expectancy_R.describe().round(3).to_string())
print("\nvariants with positive expectancy:", v.groupby(["inst", "period"]).apply(lambda g: f"{(g.expectancy_R > 0).sum()}/{len(g)}").to_string())
print("\n### Best 5 variants per instrument in 2005-2014 and what they did in 2015-2020")
for inst in ("NAS100_USD", "SPX500_USD"):
    key = ["tf", "grade", "session", "stop", "exit"]
    is_ = v[(v.inst == inst) & (v.period == "IS")].nlargest(5, "expectancy_R")
    oos = v[(v.inst == inst) & (v.period == "OOS")].set_index(key)
    for _, r in is_.iterrows():
        o = oos.loc[tuple(r[k] for k in key)]
        print(f"  {inst} {dict((k, r[k]) for k in key)} IS E={r.expectancy_R:+.3f} (n={r.trades}) -> OOS E={o.expectancy_R:+.3f} (n={o.trades})")

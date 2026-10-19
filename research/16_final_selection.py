"""Final IN-SAMPLE selection for the candidate model, with the engine's own regime gate.

Pick from a plateau (all neighbours positive on both indices and both halves),
never from a single best cell.
"""
import itertools

import numpy as np

from common import Params, evaluate
from ictmodel.metrics import summarize  # noqa: F401

LO = ("onl", "pdl", "pre_low", "asia_low", "london_low", "prev_rth_low")
HI = ("onh", "pdh", "pre_high", "asia_high", "london_high", "prev_rth_high")
COSTS = {"NAS100_USD": {"cons": 1.0, "real": 0.5}, "SPX500_USD": {"cons": 0.5, "real": 0.25}}
FLOOR = {"NAS100_USD": (0, 2, 4, 6), "SPX500_USD": (0, 1, 2, 3)}
for inst in COSTS:
    for cname, cost in COSTS[inst].items():
        variants, labels = [], []
        for th, fl, ex in itertools.product((0.0, 1.0, 1.1, 1.2), FLOOR[inst], ("eod", "rr3", "eod_be")):
            kw = dict(mode="continuation", tf=15, entry_at="ce", stop_mode="level", sweep_levels=LO,
                      target_levels=HI, min_risk_atr=0.05, max_risk_atr=0.6, sweep_end=690, entry_end=720,
                      regime_min=th, min_risk_pts=float(fl), cost_pts=cost)
            kw.update(dict(target="rr", rr=3.0) if ex == "rr3" else dict(target="eod", be_at_r=1.0 if ex == "eod_be" else 0.0))
            variants.append(Params(**kw))
            labels.append((th, fl, ex))
        res = evaluate(variants, inst=inst)
        print(f"\n### {inst} cost={cname} ({cost}pt): expectancy R net  [H1 | H2]  (n)")
        grid = {}
        for r, lab in zip(res, labels):
            a = r["all"]
            grid[lab] = (a.get("expectancy_R", np.nan), r.get("h1", {}).get("expectancy_R", np.nan),
                         r.get("h2", {}).get("expectancy_R", np.nan), a.get("trades", 0), a.get("t_stat", 0))
        for ex in ("eod", "rr3", "eod_be"):
            print(f"  exit={ex}")
            for th in (0.0, 1.0, 1.1, 1.2):
                cells = [f"floor={fl}: {grid[(th, fl, ex)][0]:+.2f} [{grid[(th, fl, ex)][1]:+.2f}|{grid[(th, fl, ex)][2]:+.2f}] "
                         f"(n={grid[(th, fl, ex)][3]}, t={grid[(th, fl, ex)][4]:+.1f})" for fl in FLOOR[inst]]
                print(f"    gate>={th:.1f}  " + "  ".join(cells))

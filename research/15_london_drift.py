"""London-open drift in equity index CFDs and the ICT 'Judas swing' entry (IN-SAMPLE ONLY).

A) Unconditional time-window longs (gross bps, t-stats, both halves).
B) Engine: sweep of the Asian low (or PDL) after midnight, reclaim/shift, long; exits 05:00 / 09:30.
"""
import sys

import numpy as np
import pandas as pd

from common import Params, days_for, evaluate, line

inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
cost = {"NAS100_USD": 1.0, "SPX500_USD": 0.5}[inst]
days = days_for(inst, "IS", 0, 960)

print(f"### {inst} A) time-window long, gross bps/day and net with {cost}pt")
for a, b in ((60, 180), (90, 180), (90, 240), (0, 300), (90, 570), (0, 570), (120, 300)):
    rows = []
    for d in days:
        i, j = np.searchsorted(d.mod, a), np.searchsorted(d.mod, b)
        if i >= len(d.mod) or j >= len(d.mod) or d.mod[i] > a + 5 or d.mod[j] > b + 5:
            continue
        rows.append((d.tday, (d.o[j] / d.o[i] - 1) * 1e4, (d.o[j] - d.o[i] - cost) / d.o[i] * 1e4))
    r = pd.DataFrame(rows, columns=["tday", "g", "n"])
    y = r.tday.dt.year
    t = lambda s: s.mean() / s.std() * np.sqrt(len(s))
    print(f"  {a//60:02d}:{a%60:02d}->{b//60:02d}:{b%60:02d} days={len(r)} gross={r.g.mean():+.2f}bps t={t(r.g):+.2f} "
          f"(H1 {r.g[y<2010].mean():+.2f} t={t(r.g[y<2010]):+.1f}, H2 {r.g[y>=2010].mean():+.2f} t={t(r.g[y>=2010]):+.1f}) "
          f"net={r.n.mean():+.2f}bps t={t(r.n):+.2f}")

print(f"\n### {inst} B) ICT Judas swing at London (engine), net of {cost}pt")
base = dict(ctx_start=0, sweep_start=0, sweep_end=150, entry_end=210, cost_pts=cost,
            sweep_levels=("asia_low", "pdl", "prev_rth_low"), target_levels=("asia_high", "pdh", "prev_rth_high"),
            min_risk_atr=0.05, max_risk_atr=0.6, max_level_dist_atr=1.0)
variants, labels = [], []
for tf, et in ((1, "mss_close"), (5, "mss_close"), (5, "fvg"), (15, "fvg")):
    for ex in (300, 570):
        for sides in ("long", "both"):
            variants.append(Params(**base, tf=tf, entry_type=et, exit_mod=ex, target="eod", sides=sides,
                                   mss_timeout=max(60, 6 * tf)))
            labels.append(f"tf={tf:2d} {et:9s} exit={ex//60:02d}:{ex%60:02d} {sides}")
res = evaluate(variants, inst=inst, ctx=(0, 960))
for r, lab in zip(res, labels):
    print(line(r, lab))

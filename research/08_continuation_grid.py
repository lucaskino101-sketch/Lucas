"""Breakaway-FVG continuation after a liquidity run (IN-SAMPLE ONLY)."""
import itertools
import sys

from common import Params, evaluate, line

inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
cost = {"NAS100_USD": 1.0, "SPX500_USD": 0.5}[inst]
lv_hi = ("onh", "pdh", "pre_high", "asia_high", "london_high", "prev_rth_high")
lv_lo = ("onl", "pdl", "pre_low", "asia_low", "london_low", "prev_rth_low")
variants, labels = [], []
for tf, ea, sm, tgt, win in itertools.product((1, 5, 15), ("edge", "ce"), ("fvg", "level"),
                                             ("rr2", "rr3", "eod", "eod_be"), ("am", "day")):
    kw = dict(mode="continuation", tf=tf, entry_at=ea, stop_mode=sm, cost_pts=cost,
              sweep_levels=lv_lo, target_levels=lv_hi, min_risk_atr=0.05, max_risk_atr=0.6,
              max_level_dist_atr=1.5)
    if tgt.startswith("rr"):
        kw.update(target="rr", rr=float(tgt[2:]))
    else:
        kw.update(target="eod", be_at_r=1.0 if tgt == "eod_be" else 0.0)
    if win == "am":
        kw.update(sweep_start=570, sweep_end=690, entry_end=720)
    else:
        kw.update(sweep_start=570, sweep_end=870, entry_end=900)
    variants.append(Params(**kw))
    labels.append(f"{inst[:6]} cont tf={tf:2d} {ea:4s} stop={sm:5s} {tgt:6s} {win}")
res = evaluate(variants, inst=inst)
order = sorted(range(len(res)), key=lambda i: -res[i]["all"].get("expectancy_R", -9))
for i in order:
    print(line(res[i], labels[i]))

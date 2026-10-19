"""ICT reversal model on FX and gold, London and NY killzones (IN-SAMPLE ONLY)."""
import itertools
import sys

from common import Params, evaluate, line

COST = {"EUR_USD": (0.0001, 0.00001), "GBP_USD": (0.00015, 0.00001), "XAU_USD": (0.40, 0.01)}
SESS = {
    # London killzone: sweep Asia range / previous day, exit before NY lunch
    "london": dict(sweep_start=120, sweep_end=300, entry_end=360, exit_mod=690,
                   sweep_levels=("asia_low", "pdl", "pwl"), target_levels=("asia_high", "pdh", "pwh")),
    # NY killzone: sweep London/Asia/previous-day levels
    "ny": dict(sweep_start=420, sweep_end=600, entry_end=630, exit_mod=900,
               sweep_levels=("london_low", "asia_low", "pdl"), target_levels=("london_high", "asia_high", "pdh")),
}
inst = sys.argv[1]
cost, tick = COST[inst]
variants, labels = [], []
for sess, tf, et, tgt in itertools.product(SESS, (1, 5, 15), ("fvg", "mss_close"), ("rr", "liq")):
    variants.append(Params(**SESS[sess], tf=tf, entry_type=et, target=tgt, min_risk_atr=0.05,
                           max_risk_atr=0.6, mss_timeout=max(60, 6 * tf), cost_pts=cost, tick=tick,
                           ctx_start=0))
    labels.append(f"{inst} {sess:6s} tf={tf:2d} {et:9s} tgt={tgt}")
res = evaluate(variants, inst=inst, ctx=(0, 960))
for r, lab in zip(res, labels):
    print(line(r, lab))

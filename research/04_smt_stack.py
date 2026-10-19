"""Do SMT divergence (NQ vs ES) or a deeper liquidity stack rescue the reversal model? (IS ONLY)"""
from common import Params, evaluate, line

base = Params(max_risk_atr=0.6)
variants, labels = [], []
for tf, et in ((1, "fvg"), (5, "fvg"), (5, "mss_close"), (15, "fvg"), (15, "ifvg")):
    for smt in (0, 1, 2):
        for stack in (1, 2):
            variants.append(base.replace(tf=tf, entry_type=et, smt=smt, stack_min=stack,
                                         mss_timeout=max(60, 6 * tf), min_risk_atr=0.05))
            labels.append(f"tf={tf:2d} {et:9s} smt={smt} stack>={stack}")
res = evaluate(variants, other="SPX500_USD")
for r, lab in zip(res, labels):
    print(line(r, lab))

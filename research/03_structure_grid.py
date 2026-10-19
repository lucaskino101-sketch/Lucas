"""Grid over structural choices of the sweep->shift->entry model (IN-SAMPLE ONLY)."""
import itertools
import sys

from common import Params, evaluate, line

base = Params()
variants, labels = [], []
for tf, n, et, tgt, mr in itertools.product((1, 3, 5, 15), (1, 2), ("fvg", "ifvg", "mss_close"),
                                           ("rr", "liq", "eod"), (0.03, 0.1)):
    variants.append(base.replace(tf=tf, swing_n=n, entry_type=et, target=tgt, min_risk_atr=mr,
                                 max_risk_atr=0.6, mss_timeout=max(60, 6 * tf)))
    labels.append(f"tf={tf:2d} n={n} {et:9s} tgt={tgt:3s} minrisk={mr}")
res = evaluate(variants, procs=4)
order = sorted(range(len(res)), key=lambda i: -res[i]["all"].get("expectancy_R", -9))
for i in order:
    print(line(res[i], labels[i]))

"""Daily Power-of-Three (AMD) as a once-a-day trade (IN-SAMPLE ONLY).

At check time T the session has a 'manipulation' extreme (LOD so far for longs).
Long if: the low so far swept a sell-side level (ONL / PDL / pre-market low) AND
price at T is back above the RTH open (displacement away from the raid).
Stop = LOD so far - buffer; exit = 15:55 (distribution leg) or stop.
Mirror for shorts. Compared against the same entry without the raid condition.
"""
import sys

import numpy as np
import pandas as pd

from common import days_for

inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
COST = {"NAS100_USD": 1.0, "SPX500_USD": 0.5}[inst]
days = days_for(inst, "IS")


def study(check_mod, buf_atr=0.0, need_raid=True, above="open", levels=("onl", "pdl", "pre_low"),
          exit_mod=955, max_risk_atr=1.0):
    rows = []
    for d in days:
        m = d.mod
        s = np.searchsorted(m, 570)
        t = np.searchsorted(m, check_mod) - 1          # last bar closed before T
        x = np.searchsorted(m, exit_mod)
        if t <= s or x >= len(m) or m[s] > 575:
            continue
        o, h, l, c = d.o, d.h, d.l, d.c
        op = o[s]
        lo, hi = l[s:t + 1].min(), h[s:t + 1].max()
        px = c[t]
        ref = {"open": op, "mid": d.levels.get("midnight_open", op)}[above] if above != "none" else None
        for side in (1, -1):
            if side == 1:
                lv = [d.levels[k] for k in levels if k in d.levels and d.levels[k] < op]
                raid = any(lo < v for v in lv)
                cond = (ref is None or px > ref)
                stop = lo - buf_atr * d.atr
                risk = px - stop
            else:
                hk = [k.replace("low", "high").replace("onl", "onh").replace("pdl", "pdh") for k in levels]
                lv = [d.levels[k] for k in hk if k in d.levels and d.levels[k] > op]
                raid = any(hi > v for v in lv)
                cond = (ref is None or px < ref)
                stop = hi + buf_atr * d.atr
                risk = stop - px
            if (need_raid and not raid) or not cond or risk <= 0 or risk > max_risk_atr * d.atr:
                continue
            # walk forward from T+1 to exit
            ex = None
            for k in range(t + 1, x + 1):
                if side == 1 and l[k] <= stop:
                    ex = min(stop, o[k]); break
                if side == -1 and h[k] >= stop:
                    ex = max(stop, o[k]); break
            if ex is None:
                ex = o[x]
            pnl = side * (ex - px)
            rows.append(dict(tday=d.tday, side=side, R=(pnl - COST) / risk, Rg=pnl / risk, risk=risk / d.atr))
    return pd.DataFrame(rows)


print(f"### {inst} AMD once-a-day, exit 15:55, cost {COST}pt")
for T in (600, 630, 660, 690):
    for need_raid in (True, False):
        for above in ("open", "none"):
            for buf in (0.0, 0.1):
                r = study(T, buf, need_raid, above)
                if len(r) == 0:
                    continue
                y = pd.to_datetime(r.tday).dt.year
                h1, h2 = r[y < 2010].R, r[y >= 2010].R
                print(f"T={T//60}:{T%60:02d} raid={int(need_raid)} vs_open={above:4s} buf={buf:.1f} n={len(r):4d} "
                      f"win={100*(r.R>0).mean():4.1f}% E={r.R.mean():+.3f} gross={r.Rg.mean():+.3f} "
                      f"t={r.R.mean()/r.R.std()*np.sqrt(len(r)):+.2f} risk={r.risk.mean():.2f}ATR "
                      f"H1={h1.mean():+.3f} H2={h2.mean():+.3f} L={r[r.side==1].R.mean():+.3f} S={r[r.side==-1].R.mean():+.3f}")

"""Is there intraday MOMENTUM in this data? Benchmarks (IN-SAMPLE ONLY).

M1  Noise-area breakout (after Zarattini, Aziz & Barbon 2024): bands around the
    open sized by the 14-day average |move from open| at each minute; checks every
    30 min; trail = band or VWAP; flat at 15:55.
M3  Opening-range breakout: first 5m close beyond the 09:30-10:00 range, stop at
    the other side of the range, exit 15:55.
Costs: 1.0 index point round trip per trade (NQ-like).
"""
import sys

import numpy as np
import pandas as pd

from common import days_for

COST = 1.0


def noise_area(days, lookback=14, check_every=30, cost=COST):
    rows = []
    hist = []  # per-day arrays of |close/open-1| at each RTH minute offset
    prev_close = None
    for d in days:
        m = d.mod
        rth = (m >= 570) & (m < 960)
        if rth.sum() < 300:
            prev_close = None
            continue
        mm, o, h, l, c = m[rth], d.o[rth], d.h[rth], d.l[rth], d.c[rth]
        off = mm - 570
        op = o[0]
        move = np.full(390, np.nan)
        move[off] = np.abs(c / op - 1)
        if len(hist) >= lookback and prev_close is not None:
            sigma = np.nanmean(np.vstack(hist[-lookback:]), axis=0)
            ub = max(op, prev_close) * (1 + sigma[off])
            lb = min(op, prev_close) * (1 - sigma[off])
            # VWAP proxy (no reliable volume in CFD data): cumulative typical price mean
            vw = np.cumsum((h + l + c) / 3) / np.arange(1, len(c) + 1)
            pos, entry, day_pnl, n_tr = 0, 0.0, 0.0, 0
            for k in range(len(c)):
                t = off[k]
                last = (mm[k] >= 955)
                if pos != 0 and (last or ((t + 1) % check_every == 0 and
                                 ((pos == 1 and c[k] < max(ub[k], vw[k])) or
                                  (pos == -1 and c[k] > min(lb[k], vw[k]))))):
                    day_pnl += pos * (c[k] - entry) - cost
                    pos = 0
                if last:
                    break
                if pos == 0 and (t + 1) % check_every == 0 and t >= 29:
                    if c[k] > ub[k]:
                        pos, entry, n_tr = 1, c[k], n_tr + 1
                    elif c[k] < lb[k]:
                        pos, entry, n_tr = -1, c[k], n_tr + 1
            rows.append(dict(tday=d.tday, pnl_pts=day_pnl, n=n_tr, atr=d.atr, px=op))
        hist.append(move)
        prev_close = c[-1]
    return pd.DataFrame(rows)


def orb(days, or_end=600, cost=COST, exit_mod=955):
    rows = []
    for d in days:
        m = d.mod
        rth = (m >= 570) & (m < 960)
        if rth.sum() < 300:
            continue
        mm, o, h, l, c = m[rth], d.o[rth], d.h[rth], d.l[rth], d.c[rth]
        orr = mm < or_end
        hi, lo = h[orr].max(), l[orr].min()
        pos = 0
        for k in np.flatnonzero(~orr):
            if pos == 0 and (mm[k] - 570) % 5 == 4 and mm[k] < 720:
                if c[k] > hi:
                    pos, entry, stop = 1, c[k], lo
                elif c[k] < lo:
                    pos, entry, stop = -1, c[k], hi
                if pos:
                    risk = abs(entry - stop)
                    continue
            if pos:
                if (pos == 1 and l[k] <= stop) or (pos == -1 and h[k] >= stop):
                    rows.append(dict(tday=d.tday, R=(-risk - cost) / risk, side=pos, risk=risk)); pos = 0; break
                if mm[k] >= exit_mod:
                    pnl = pos * (c[k] - entry)
                    rows.append(dict(tday=d.tday, R=(pnl - cost) / risk, side=pos, risk=risk)); pos = 0; break
    return pd.DataFrame(rows)


if __name__ == "__main__":
    inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
    days = days_for(inst, "IS")
    na = noise_area(days)
    na["ret"] = na.pnl_pts / na.px            # 1x notional daily return
    y = pd.to_datetime(na.tday).dt.year
    print(f"### {inst} M1 noise-area momentum, 1x notional, net of {COST}pt/trade")
    for lab, msk in (("IS all", y > 0), ("2005-09", y < 2010), ("2010-14", y >= 2010)):
        r = na.ret[msk]
        print(f"  {lab}: days={msk.sum()} trades={na.n[msk].sum()} ann.ret={252*r.mean()*100:+.1f}% "
              f"vol={np.sqrt(252)*r.std()*100:.1f}% Sharpe={np.sqrt(252)*r.mean()/r.std():+.2f}")
    print(na.assign(year=y).groupby("year").ret.agg(lambda s: f"{252*s.mean()*100:+.1f}%/yr").to_string())
    ob = orb(days)
    y2 = pd.to_datetime(ob.tday).dt.year
    print(f"\n### {inst} M3 30-min ORB, stop=other side of range, exit 15:55")
    for lab, msk in (("IS all", y2 > 0), ("2005-09", y2 < 2010), ("2010-14", y2 >= 2010)):
        r = ob.R[msk]
        print(f"  {lab}: n={msk.sum()} win={100*(r>0).mean():.1f}% E={r.mean():+.3f}R t={r.mean()/r.std()*np.sqrt(len(r)):+.2f}")

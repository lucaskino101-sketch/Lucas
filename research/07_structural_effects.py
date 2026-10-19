"""Structural effects with an economic rationale (IN-SAMPLE ONLY).

A  24h seasonality: mean return per 30-min bucket (NY time), t-stats, both IS halves.
C  Opening Range Gap (RTH open vs prior RTH close): fill probability + gap-fade expectancy.
B  Daily liquidity raid: the day trades below the prior day's low and closes back above it.
"""
import sys

import numpy as np
import pandas as pd

from common import ROOT  # noqa: F401  (sets sys.path)
from ictmodel.data import load_m1
from ictmodel.sessions import add_time_keys, daily_levels

inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
df = add_time_keys(load_m1(inst, "2005-01-01", "2015-01-01"))
lv = daily_levels(df)
pd.set_option("display.width", 220)

# ---------- A: 24h seasonality (log returns of 30-min buckets) ----------
b = (df["mod"] // 30)
px = df.groupby([df["tday"], b])["close"].last().unstack()
ret = np.log(px).diff(axis=1) * 1e4          # bps, within the trading day
order = [k for k in range(36, 48)] + [k for k in range(0, 34)]   # 18:00 .. 17:00
ret = ret.reindex(columns=order)
yr = ret.index.year
rows = []
for k in order:
    s = ret[k].dropna()
    s1, s2 = s[s.index.year < 2010], s[s.index.year >= 2010]
    t = lambda x: x.mean() / x.std() * np.sqrt(len(x))
    rows.append(dict(bucket=f"{k*30//60:02d}:{k*30%60:02d}", mean_bps=s.mean(), t=t(s),
                     H1_bps=s1.mean(), H1_t=t(s1), H2_bps=s2.mean(), H2_t=t(s2)))
A = pd.DataFrame(rows)
print(f"### A {inst}: mean 30-min return by NY time (bps), IS 2005-2014")
print(A.round(2).to_string(index=False))

# ---------- C: opening range gap ----------
rth = df[(df["mod"] >= 570) & (df["mod"] < 960)]
first_hour = rth[rth["mod"] < 690]
g = pd.DataFrame({"open": lv["rth_open"], "pc": lv["prev_rth_close"],
                  "hi_am": first_hour.groupby("tday")["high"].max(),
                  "lo_am": first_hour.groupby("tday")["low"].min(),
                  "close": lv["rth_close"], "hi": lv["rth_high"], "lo": lv["rth_low"]}).dropna()
atr = (lv["day_high"] - lv["day_low"]).rolling(14).mean().shift(1).reindex(g.index)
g["gap_atr"] = (g["open"] - g["pc"]) / atr
up = g["open"] > g["pc"]
g["filled_am"] = np.where(up, g["lo_am"] <= g["pc"], g["hi_am"] >= g["pc"])
g["filled_day"] = np.where(up, g["lo"] <= g["pc"], g["hi"] >= g["pc"])
g["ce"] = (g["open"] + g["pc"]) / 2
g["ce_hit_am"] = np.where(up, g["lo_am"] <= g["ce"], g["hi_am"] >= g["ce"])
print(f"\n### C {inst}: opening range gap fill rates by gap size (ATR units)")
bins = [0, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 9]
g["gbin"] = pd.cut(g["gap_atr"].abs(), bins)
print(g.groupby("gbin", observed=True).agg(n=("filled_am", "size"), CE_by_1130=("ce_hit_am", "mean"),
      fill_by_1130=("filled_am", "mean"), fill_by_close=("filled_day", "mean")).round(3).to_string())

# ---------- B: daily liquidity raid (turtle soup on the daily) ----------
d = lv[["day_open", "day_high", "day_low", "day_close", "pdh", "pdl"]].dropna().copy()
d["ma50"] = d["day_close"].rolling(50).mean()
d["atr"] = (d["day_high"] - d["day_low"]).rolling(14).mean()
d["next_ret"] = (d["day_close"].shift(-1) - d["day_close"]) / d["atr"]
d["next3_ret"] = (d["day_close"].shift(-3) - d["day_close"]) / d["atr"]
d["raid_low"] = (d["day_low"] < d["pdl"]) & (d["day_close"] > d["pdl"])
d["raid_high"] = (d["day_high"] > d["pdh"]) & (d["day_close"] < d["pdh"])
d["up_trend"] = d["day_close"] > d["ma50"]
print(f"\n### B {inst}: forward returns after daily liquidity raids (ATR units)")
for name, m in (("all days", d.index == d.index), ("raid of PDL (bullish)", d.raid_low),
                ("raid PDL & uptrend", d.raid_low & d.up_trend), ("raid PDL & downtrend", d.raid_low & ~d.up_trend),
                ("raid of PDH (bearish)", d.raid_high), ("raid PDH & downtrend", d.raid_high & ~d.up_trend),
                ("raid PDH & uptrend", d.raid_high & d.up_trend)):
    s = d[m]
    for lab, ss in (("H1", s[s.index.year < 2010]), ("H2", s[s.index.year >= 2010])):
        pass
    h1, h2 = s[s.index.year < 2010], s[s.index.year >= 2010]
    print(f"{name:24s} n={len(s):4d} next1={s.next_ret.mean():+.3f} (H1 {h1.next_ret.mean():+.3f} H2 {h2.next_ret.mean():+.3f}) "
          f"next3={s.next3_ret.mean():+.3f} (H1 {h1.next3_ret.mean():+.3f} H2 {h2.next3_ret.mean():+.3f})")

"""Which pre-09:30 information predicts the NY session direction? (IN-SAMPLE ONLY)

Each candidate bias feature is evaluated by: sign hit-rate vs the RTH (09:30->16:00)
return, and correlation, separately for the two halves of the in-sample period so
an effect has to show up twice to count.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ictmodel.data import load_m1  # noqa: E402
from ictmodel.sessions import add_time_keys, daily_levels  # noqa: E402

inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
df = add_time_keys(load_m1(inst, "2005-01-01", "2015-01-01"))
d = daily_levels(df)
# value at 10:00 / 11:00 (close of the 09:59 / 10:59 bar)
for hhmm, m in (("1000", 599), ("1100", 659), ("1530", 929)):
    s = df[df["mod"] <= m].groupby("tday")["close"].last()
    d[f"px_{hhmm}"] = s
atr = (d["day_high"] - d["day_low"]).rolling(14).mean().shift(1)
y = (d["rth_close"] - d["rth_open"]) / atr               # NY session return
y_rest = (d["rth_close"] - d["px_1000"]) / atr            # 10:00 -> close
y_last = (d["rth_close"] - d["px_1530"]) / atr            # last 30 min

feat = pd.DataFrame(index=d.index)
feat["open_vs_midnight"] = (d["rth_open"] - d["midnight_open"]) / atr
feat["gap_vs_prev_rth_close"] = (d["rth_open"] - d["prev_rth_close"]) / atr
feat["overnight_ret"] = (d["rth_open"] - d["day_open"]) / atr
feat["open_vs_0830"] = (d["rth_open"] - d["open_0830"]) / atr
rng = (d["pdh"] - d["pdl"]).replace(0, np.nan)
feat["prev_close_location"] = (d["pd_close"] - d["pdl"]) / rng - 0.5
feat["open_in_prev_range"] = (d["rth_open"] - d["pdl"]) / rng - 0.5
feat["trend_20d"] = (d["prev_rth_close"] - d["prev_rth_close"].rolling(20).mean()) / atr
feat["prev_rth_ret"] = (d["prev_rth_close"] - d["rth_open"].shift(1)) / atr
feat["on_range_pos"] = (d["rth_open"] - d["onl"]) / (d["onh"] - d["onl"]).replace(0, np.nan) - 0.5
feat["first30_ret"] = (d["px_1000"] - d["rth_open"]) / atr      # known at 10:00 -> predicts y_rest
feat["day_to_1530_ret"] = (d["px_1530"] - d["prev_rth_close"]) / atr  # GHLZ intraday momentum -> y_last

def evaluate(x, yy, name, target):
    rows = []
    for lab, (a, b) in (("2005-09", ("2005", "2010")), ("2010-14", ("2010", "2015"))):
        m = (x.index >= a) & (x.index < b) & x.notna() & yy.notna()
        xs, ys = x[m], yy[m]
        hit = (np.sign(xs) == np.sign(ys)).mean() * 100
        rows.append(f"{lab}: n={m.sum():4d} hit={hit:5.1f}% corr={np.corrcoef(xs, ys)[0,1]:+.3f} "
                    f"mean_y|x>0={ys[xs>0].mean():+.3f} mean_y|x<0={ys[xs<0].mean():+.3f}")
    print(f"{name:24s} -> {target:8s} | " + " | ".join(rows))

pd.set_option("display.width", 220)
print(f"### {inst}: bias features vs NY session return (units: ATR14)")
for c in feat.columns:
    if c == "first30_ret":
        evaluate(feat[c], y_rest, c, "10:00->16:00")
    elif c == "day_to_1530_ret":
        evaluate(feat[c], y_last, c, "15:30->16:00")
    else:
        evaluate(feat[c], y, c, "09:30->16:00")

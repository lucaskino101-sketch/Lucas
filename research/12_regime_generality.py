"""Is 'momentum works in volatility expansion' general? Apply the same ATR14/ATR100 gate
to the non-ICT benchmarks (ORB, noise-area) and the AMD daily model (IN-SAMPLE ONLY)."""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

from common import days_for

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
    mod = importlib.util.module_from_spec(spec)
    old = sys.argv
    sys.argv = [path, inst]
    spec.loader.exec_module(mod)
    sys.argv = old
    return mod


inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
days = days_for(inst, "IS")
atr = pd.Series([d.atr for d in days], index=pd.DatetimeIndex([d.tday for d in days]))
ratio = atr / atr.rolling(100, min_periods=50).mean()
mom = load("mom", "05_momentum_benchmarks.py")
amd = load("amd", "09_amd_daily.py")


def report(name, df, rcol):
    df = df.assign(ratio=ratio.reindex(pd.to_datetime(df.tday)).to_numpy())
    y = pd.to_datetime(df.tday).dt.year
    parts = []
    for th in (0.0, 1.0, 1.1, 1.2):
        s = df[df.ratio >= th]
        ys = y[df.ratio >= th]
        r = s[rcol]
        parts.append(f"th={th:.1f} n={len(s):4d} E={r.mean():+.3f} t={r.mean()/r.std()*np.sqrt(len(r)):+.1f} "
                     f"H1={r[ys < 2010].mean():+.3f} H2={r[ys >= 2010].mean():+.3f}")
    print(f"{name:28s} | " + " | ".join(parts))


print(f"### {inst}: regime gate applied to other models (net)")
ob = mom.orb(days)
report("ORB 30m, exit 15:55", ob, "R")
na = mom.noise_area(days)
na["ret_bps"] = na.pnl_pts / na.px * 1e4
report("noise-area (bps/day)", na[na.n > 0], "ret_bps")
for T in (630, 660):
    r = amd.study(T, 0.1, True, "open")
    report(f"AMD T={T//60}:{T%60:02d} raid vs_open", r, "R")

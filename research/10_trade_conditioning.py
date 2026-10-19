"""Do reversal / continuation trades depend on regime or trade location? (IN-SAMPLE ONLY)

Features are all known at entry. An effect must be monotonic-ish AND agree in both
halves (2005-09, 2010-14) to be worth anything.
"""
import sys

import numpy as np
import pandas as pd

from common import Params, days_for, evaluate

inst = sys.argv[1] if len(sys.argv) > 1 else "NAS100_USD"
cost = {"NAS100_USD": 1.0, "SPX500_USD": 0.5}[inst]
models = {
    "reversal tf5 mss_close": Params(tf=5, entry_type="mss_close", min_risk_atr=0.05, max_risk_atr=0.6, cost_pts=cost),
    "reversal tf15 fvg": Params(tf=15, entry_type="fvg", min_risk_atr=0.05, max_risk_atr=0.6, mss_timeout=90, cost_pts=cost),
    "continuation tf15 ce lvl eod": Params(mode="continuation", tf=15, entry_at="ce", stop_mode="level", target="eod",
                                           sweep_levels=("onl", "pdl", "pre_low", "asia_low", "london_low", "prev_rth_low"),
                                           target_levels=("onh", "pdh", "pre_high", "asia_high", "london_high", "prev_rth_high"),
                                           min_risk_atr=0.05, max_risk_atr=0.6, cost_pts=cost),
}
res = evaluate(list(models.values()), inst=inst, keep_trades=True)
days = days_for(inst, "IS")
dd = pd.DataFrame({"tday": [d.tday for d in days], "atr": [d.atr for d in days],
                   "open": [d.o[np.searchsorted(d.mod, 570)] if np.searchsorted(d.mod, 570) < len(d.mod) else np.nan for d in days],
                   "onh": [d.levels.get("onh", np.nan) for d in days], "onl": [d.levels.get("onl", np.nan) for d in days],
                   "pdh": [d.levels.get("pdh", np.nan) for d in days], "pdl": [d.levels.get("pdl", np.nan) for d in days],
                   "pc": [d.levels.get("prev_rth_close", np.nan) for d in days] if False else np.nan}).set_index("tday")
dd["atr_ratio"] = dd["atr"] / dd["atr"].rolling(100, min_periods=50).mean()
dd["on_range"] = (dd["onh"] - dd["onl"]) / dd["atr"]
dd["pd_range"] = (dd["pdh"] - dd["pdl"]) / dd["atr"]

for (name, p), r in zip(models.items(), res):
    t = r["trades"].copy()
    t = t.join(dd[["atr_ratio", "on_range", "pd_range", "open"]], on="tday")
    t["half"] = np.where(pd.to_datetime(t.tday).dt.year < 2010, "H1", "H2")
    t["entry_hr"] = (t.entry_mod // 30) * 30
    t["loc_vs_open"] = t.side * (t.entry - t.open) / t.atr      # <0 = bought below the open (discount)
    t["risk_atr"] = t.risk / t.atr
    t["dow"] = pd.to_datetime(t.tday).dt.dayofweek
    print(f"\n######## {inst} | {name} | n={len(t)} E_net={t.r_net.mean():+.3f} E_gross={t.r_gross.mean():+.3f}")
    for f, q in (("atr_ratio", 4), ("on_range", 4), ("pd_range", 4), ("loc_vs_open", 4), ("risk_atr", 4),
                 ("entry_hr", None), ("stack", None), ("dow", None)):
        if q:
            t["bin"] = pd.qcut(t[f], q, duplicates="drop")
        else:
            t["bin"] = t[f]
        g = t.groupby(["bin", "half"], observed=True)["r_gross"].mean().unstack()
        n = t.groupby("bin", observed=True).size()
        out = g.assign(n=n).round(3)
        print(f"-- {f} (gross R by half)\n" + out.to_string())

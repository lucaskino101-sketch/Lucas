"""Shared research helpers: cached Day lists and parallel evaluation of Params variants."""
import os
import pickle
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ictmodel.data import load_m1  # noqa: E402
from ictmodel.engine import Params, prepare_days, run  # noqa: E402
from ictmodel.metrics import summarize  # noqa: E402

CACHE = os.path.join(ROOT, "data", "cache")
PERIODS = {"IS": ("2005-01-01", "2015-01-01"), "OOS": ("2015-01-01", "2020-06-01")}


def days_for(inst: str, period: str, ctx_start: int = 420, end_mod: int = 960):
    tag = "" if (ctx_start, end_mod) == (420, 960) else f"_{ctx_start}_{end_mod}"
    path = os.path.join(CACHE, f"days_{inst}_{period}{tag}.pkl")
    if os.path.exists(path):
        return pickle.load(open(path, "rb"))
    a, b = PERIODS[period]
    warm = (pd.Timestamp(a) - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
    days = [d for d in prepare_days(load_m1(inst, warm, b), ctx_start, end_mod)
            if d.tday >= pd.Timestamp(a)]
    pickle.dump(days, open(path, "wb"))
    return days


_G = {}


def _init(inst, period, other, ctx):
    _G["days"] = days_for(inst, period, *ctx)
    _G["other"] = {d.tday: d for d in days_for(other, period, *ctx)} if other else None
    _G["all_days"] = pd.DatetimeIndex([d.tday for d in _G["days"]])


def _eval(p: Params):
    tr = run(_G["days"], p, _G["other"])
    out = {"params": p}
    out["all"] = summarize(tr, _G["all_days"])
    out["gross_E"] = float(tr["r_gross"].mean()) if len(tr) else np.nan
    if len(tr):
        y = pd.to_datetime(tr["tday"]).dt.year
        mid = 2010 if _G["all_days"][0].year < 2010 else 2018
        out["h1"] = summarize(tr[y < mid], _G["all_days"][_G["all_days"].year < mid])
        out["h2"] = summarize(tr[y >= mid], _G["all_days"][_G["all_days"].year >= mid])
        out["avg_risk"] = float(tr["risk"].mean())
    out["trades"] = tr
    return out


def evaluate(variants, inst="NAS100_USD", period="IS", other=None, procs=4, keep_trades=False,
             ctx=(420, 960)):
    days_for(inst, period, *ctx)
    if other:
        days_for(other, period, *ctx)
    with Pool(procs, initializer=_init, initargs=(inst, period, other, ctx)) as pool:
        res = pool.map(_eval, variants, chunksize=1)
    if not keep_trades:
        for r in res:
            r.pop("trades", None)
    return res


def line(r, label=""):
    a = r["all"]
    if a.get("trades", 0) == 0:
        return f"{label:60s} no trades"
    h1, h2 = r.get("h1", {}), r.get("h2", {})
    return (f"{label:60s} n={a['trades']:5d} win={100*a['win_rate']:4.1f}% E={a['expectancy_R']:+.3f} "
            f"(gross {r['gross_E']:+.3f}) t={a['t_stat']:+5.2f} PF={a['profit_factor']:.2f} "
            f"Sh={a['sharpe']:+.2f} DD={100*a['max_dd']:5.1f}% risk={r['avg_risk']:.1f}pt | "
            f"H1 E={h1.get('expectancy_R', np.nan):+.3f} H2 E={h2.get('expectancy_R', np.nan):+.3f}")

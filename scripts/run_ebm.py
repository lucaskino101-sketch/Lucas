"""Run the frozen Expansion Breakaway Model on any period and print its statistics.

Example:
    python3 scripts/run_ebm.py --inst NAS100_USD --start 2015-01-01 --end 2020-06-01
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ictmodel.data import load_m1  # noqa: E402
from ictmodel.engine import prepare_days, run  # noqa: E402
from ictmodel.metrics import by_year, fmt, summarize  # noqa: E402
from ictmodel.model import ebm  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--inst", default="NAS100_USD", choices=["NAS100_USD", "SPX500_USD"])
ap.add_argument("--start", default="2015-01-01")
ap.add_argument("--end", default="2020-06-01")
ap.add_argument("--cost", default="conservative", choices=["conservative", "realistic"])
ap.add_argument("--exit", default="eod", choices=["eod", "rr3", "eod_be"])
ap.add_argument("--risk", type=float, default=0.01, help="fraction of equity risked per trade")
ap.add_argument("--out", default=None, help="optional CSV path for the trade list")
a = ap.parse_args()

warm = (pd.Timestamp(a.start) - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
days = [d for d in prepare_days(load_m1(a.inst, warm, a.end)) if d.tday >= pd.Timestamp(a.start)]
trades = run(days, ebm(a.inst, a.cost, a.exit))
print(f"EBM {a.inst} {a.start}..{a.end} cost={a.cost} exit={a.exit}")
print(fmt(summarize(trades, pd.DatetimeIndex([d.tday for d in days]), risk_frac=a.risk)))
if len(trades):
    print(by_year(trades).round(2).to_string())
if a.out:
    trades.to_csv(a.out, index=False)
    print("trades ->", a.out)

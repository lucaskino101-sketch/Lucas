"""Engine integrity: no lookahead, exact long/short mirror symmetry."""
import os
import pickle

import numpy as np
import pandas as pd
import pytest

from ictmodel.engine import HIGH_LEVELS, LOW_LEVELS, Day, Params, run_day

CACHE = os.environ.get("ICT_TEST_DAYS")


def synthetic_days(n_days=60, seed=1):
    """Random-walk 1m sessions with plausible levels, so tests need no data download."""
    rng = np.random.default_rng(seed)
    days = []
    for d in range(n_days):
        mod = np.arange(420, 961)
        steps = rng.standard_t(4, size=len(mod)) * 1.5
        c = 1000 + np.cumsum(steps)
        o = np.r_[c[0], c[:-1]]
        h = np.maximum(o, c) + rng.random(len(mod)) * 1.2
        l = np.minimum(o, c) - rng.random(len(mod)) * 1.2
        pre = mod < 570
        lv = {"onl": l[pre].min(), "onh": h[pre].max(), "pre_low": l[(mod >= 480) & pre].min(),
              "pre_high": h[(mod >= 480) & pre].max(),
              "pdl": l[pre].min() - rng.random() * 20, "pdh": h[pre].max() + rng.random() * 20}
        days.append(Day(pd.Timestamp("2010-01-04") + pd.Timedelta(days=d), mod, o, h, l, c, lv, 60.0))
    return days


def negate(day: Day) -> Day:
    swap = dict(zip(LOW_LEVELS, HIGH_LEVELS)) | dict(zip(HIGH_LEVELS, LOW_LEVELS))
    lv = {swap[k]: -v for k, v in day.levels.items()}
    return Day(day.tday, day.mod, -day.o, -day.l, -day.h, -day.c, lv, day.atr)


PARAMS = [Params(), Params(entry_type="ifvg"), Params(entry_type="mss_close", target="liq"),
          Params(tf=5, target="eod", be_at_r=1.0), Params(tf=3, swing_n=2, max_trades=2),
          Params(mode="continuation", tf=5, target="eod"),
          Params(mode="continuation", tf=1, stop_mode="level", rr=3.0, max_trades=2),
          Params(mode="continuation", tf=1, need_opp_sweep=True, target="eod")]


@pytest.mark.parametrize("p", PARAMS)
def test_mirror_symmetry(p):
    p = p.replace(sweep_levels=("onl", "pdl", "pre_low"), target_levels=("onh", "pdh", "pre_high"), max_level_dist_atr=3.0,
                  min_risk_atr=0.0)
    n_trades = 0
    for day in synthetic_days():
        a = run_day(day, p)
        b = run_day(negate(day), p)
        assert len(a) == len(b)
        for x, y in zip(a, b):
            n_trades += 1
            assert x["side"] == -y["side"]
            assert x["fill_i"] == y["fill_i"] and x["exit_i"] == y["exit_i"]
            assert x["entry"] == pytest.approx(-y["entry"]) and x["exit"] == pytest.approx(-y["exit"])
            assert x["r_net"] == pytest.approx(y["r_net"])
    assert n_trades > 0


@pytest.mark.parametrize("p", PARAMS)
def test_no_lookahead(p):
    """Scrambling every bar after a fill must not change that trade's entry."""
    p = p.replace(sweep_levels=("onl", "pdl", "pre_low"), target_levels=("onh", "pdh", "pre_high"), max_level_dist_atr=3.0,
                  min_risk_atr=0.0)
    rng = np.random.default_rng(7)
    checked = 0
    for day in synthetic_days(n_days=300, seed=3):
        trades = run_day(day, p)
        if not trades:
            continue
        t0 = trades[0]
        k = t0["fill_i"] + 1
        o, h, l, c = (x.copy() for x in (day.o, day.h, day.l, day.c))
        noise = rng.normal(scale=25, size=len(o) - k)
        o[k:] += noise
        c[k:] += noise
        h[k:] = np.maximum(o[k:], c[k:]) + 5
        l[k:] = np.minimum(o[k:], c[k:]) - 5
        t1 = run_day(Day(day.tday, day.mod, o, h, l, c, day.levels, day.atr), p)[0]
        for key in ("side", "fill_i", "entry", "stop", "target", "arm_mod", "sweep_mod", "swept"):
            assert t0[key] == t1[key], key
        checked += 1
    assert checked > 5


@pytest.mark.skipif(not CACHE, reason="set ICT_TEST_DAYS to a pickled list of real Days")
def test_mirror_symmetry_real_data():
    days = pickle.load(open(CACHE, "rb"))[:300]
    for day in days:
        for p in PARAMS[:2]:
            a, b = run_day(day, p), run_day(negate(day), p)
            assert [(t["fill_i"], -t["side"]) for t in a] == [(t["fill_i"], t["side"]) for t in b]

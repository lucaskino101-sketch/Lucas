"""ICT time model: trading days, sessions, and the liquidity levels known before each session.

All times are America/New_York wall clock (tz-naive). A *trading day* (``tday``)
runs 18:00 on the prior calendar day to 17:00, the CME Globex convention, so a
Sunday-evening bar belongs to Monday.

Sessions (ICT killzone conventions):
    Asia      20:00-24:00
    London    02:00-05:00
    Pre-NY    07:00-09:30
    RTH       09:30-16:00   (cash equity session; "NY AM" is 09:30-12:00)
    Overnight 18:00-09:30
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ASIA = (20 * 60, 24 * 60)
LONDON = (2 * 60, 5 * 60)
PRE_NY = (7 * 60, 9 * 60 + 30)
RTH = (9 * 60 + 30, 16 * 60)


def add_time_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``tday`` (trading-day date), ``mod`` (minute of day) and ``dow``."""
    out = df.copy()
    idx = out.index
    tday = (idx + pd.Timedelta(hours=6)).normalize()
    out["tday"] = tday
    out["mod"] = idx.hour * 60 + idx.minute
    out["dow"] = tday.dayofweek
    # Drop the rare weekend quotes some CFD feeds emit.
    return out[out["dow"] < 5]


def _window_hl(df: pd.DataFrame, start: int, end: int, crosses_midnight: bool = False) -> pd.DataFrame:
    """High/low per tday of bars whose minute-of-day is in [start, end)."""
    m = df["mod"]
    if crosses_midnight:
        sel = (m >= start) | (m < end)
    else:
        sel = (m >= start) & (m < end)
    g = df[sel].groupby("tday")
    return pd.DataFrame({"high": g["high"].max(), "low": g["low"].min()})


def daily_levels(df: pd.DataFrame) -> pd.DataFrame:
    """One row per trading day with the ICT reference levels for that day.

    Every column is computable *before* the NY cash open (09:30) of that day,
    except the ``rth_*``/``day_*`` columns, which describe the day itself and are
    only used for research statistics, never for signals.
    """
    g = df.groupby("tday")
    day = pd.DataFrame({"day_open": g["open"].first(), "day_high": g["high"].max(),
                        "day_low": g["low"].min(), "day_close": g["close"].last()})

    rth = df[(df["mod"] >= RTH[0]) & (df["mod"] < RTH[1])].groupby("tday")
    day["rth_open"] = rth["open"].first()
    day["rth_high"] = rth["high"].max()
    day["rth_low"] = rth["low"].min()
    day["rth_close"] = rth["close"].last()

    # Previous-day levels (full Globex day and cash session).
    day["pdh"] = day["day_high"].shift(1)
    day["pdl"] = day["day_low"].shift(1)
    day["pd_close"] = day["day_close"].shift(1)
    day["prev_rth_high"] = day["rth_high"].shift(1)
    day["prev_rth_low"] = day["rth_low"].shift(1)
    day["prev_rth_close"] = day["rth_close"].shift(1)

    # Overnight (18:00 -> 09:30) belongs to the same tday by construction.
    on = df[(df["mod"] >= 18 * 60) | (df["mod"] < RTH[0])].groupby("tday")
    day["onh"] = on["high"].max()
    day["onl"] = on["low"].min()

    asia = df[df["mod"] >= ASIA[0]].groupby("tday")
    day["asia_high"] = asia["high"].max()
    day["asia_low"] = asia["low"].min()

    lon = _window_hl(df, *LONDON)
    day["london_high"] = lon["high"]
    day["london_low"] = lon["low"]

    pre = _window_hl(df, *PRE_NY)
    day["pre_high"] = pre["high"]
    day["pre_low"] = pre["low"]

    # Opening prices ICT uses as "true" opens.
    def first_open_at(minute: int) -> pd.Series:
        sel = df[(df["mod"] >= minute) & (df["mod"] < minute + 30)]
        return sel.groupby("tday")["open"].first()

    day["midnight_open"] = first_open_at(0)
    day["open_0830"] = first_open_at(8 * 60 + 30)

    # Previous week high/low (week = Mon..Fri trading days).
    wk = day.index.to_period("W-FRI")
    wk_hl = day.groupby(wk).agg(wh=("day_high", "max"), wl=("day_low", "min"))
    prev = wk_hl.shift(1)
    day["pwh"] = prev["wh"].reindex(wk).to_numpy()
    day["pwl"] = prev["wl"].reindex(wk).to_numpy()
    return day


def in_window(mod: np.ndarray, start: int, end: int) -> np.ndarray:
    return (mod >= start) & (mod < end)

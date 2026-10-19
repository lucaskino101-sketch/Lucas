"""ICT price-structure primitives, all causal (no lookahead).

Conventions: arrays are bar-aligned numpy arrays. A structure "known at bar k"
uses only bars <= k.

* Fair Value Gap (FVG): three-candle imbalance. A bullish FVG completes at bar k
  when ``low[k] > high[k-2]``; its zone is ``[high[k-2], low[k]]``. Bearish when
  ``high[k] < low[k-2]``; zone ``[high[k], low[k-2]]``. Known at the close of k.
* Consequent Encroachment (CE): the midpoint of an FVG.
* Inversion FVG (IFVG): an FVG that price later *closes* through; it flips
  polarity (a violated bearish FVG becomes support and vice versa).
* Swing high/low: fractal pivot with ``n`` bars on each side, known at bar k+n.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def resample_ohlc(o, h, l, c, bucket):
    """Aggregate bars into higher-timeframe bars by integer ``bucket`` id.

    Returns (ids, o, h, l, c, last_pos) where ``last_pos[j]`` is the position of
    the final input bar of bucket ``ids[j]``: the HTF bar is only known after it.
    """
    bucket = np.asarray(bucket)
    change = np.flatnonzero(np.diff(bucket)) + 1
    starts = np.r_[0, change]
    ends = np.r_[change, len(bucket)] - 1
    ho = o[starts]
    hh = np.maximum.reduceat(h, starts)
    hl = np.minimum.reduceat(l, starts)
    hc = c[ends]
    return bucket[starts], ho, hh, hl, hc, ends


def fvgs(h, l):
    """Bullish and bearish FVG boolean arrays (flag set on the completing bar k)."""
    h = np.asarray(h, float)
    l = np.asarray(l, float)
    bull = np.zeros(len(h), bool)
    bear = np.zeros(len(h), bool)
    if len(h) >= 3:
        bull[2:] = l[2:] > h[:-2]
        bear[2:] = h[2:] < l[:-2]
    return bull, bear


def swing_points(h, l, n=1):
    """Fractal swing highs/lows. Flag is set on the pivot bar; it is known n bars later."""
    h = np.asarray(h, float)
    l = np.asarray(l, float)
    size = len(h)
    sh = np.zeros(size, bool)
    sl = np.zeros(size, bool)
    if size < 2 * n + 1:
        return sh, sl
    win = np.lib.stride_tricks.sliding_window_view
    hw, lw = win(h, n), win(l, n)              # hw[s] = h[s : s+n]
    core = slice(n, size - n)
    left_hmax, right_hmax = hw[: size - 2 * n].max(1), hw[n + 1:].max(1)
    left_lmin, right_lmin = lw[: size - 2 * n].min(1), lw[n + 1:].min(1)
    sh[core] = (h[core] > left_hmax) & (h[core] >= right_hmax)
    sl[core] = (l[core] < left_lmin) & (l[core] <= right_lmin)
    return sh, sl


def daily_atr(day_high: pd.Series, day_low: pd.Series, n: int = 14) -> pd.Series:
    """Average daily range of the *previous* n days (known before the day starts)."""
    return (day_high - day_low).rolling(n).mean().shift(1)

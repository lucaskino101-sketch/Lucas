"""Event-driven ICT model engine on 1-minute bars.

The model logic is written once, for longs. Shorts run the same code on negated
prices: negating maps highs to lows, bearish FVGs to bullish FVGs, swing highs to
swing lows, and buy-side liquidity to sell-side liquidity, so the two sides cannot
drift apart through copy-paste bugs.

Long setup, per trading day (all times New York):

1. LIQUIDITY  Sell-side levels known before the window (overnight low, previous
   day low, Asia/London lows, pre-market low, ...) that sit below the open.
2. SWEEP      A 1m low trades through one or more untouched levels inside the
   sweep window. Every further new low updates the extreme and may sweep more
   levels (the "stack").
3. SHIFT      A structure-timeframe close above the last confirmed swing high
   that preceded the extreme (market structure shift), within ``mss_timeout``.
4. ENTRY      A limit order in the imbalance created by the shift (FVG), or in
   the inverted bearish FVG of the down-leg (IFVG), or at the shift close.
5. RISK       Stop beyond the sweep extreme. Target: fixed R, nearest opposing
   liquidity, or the time exit.

Fill rules are deliberately conservative: limits need a one-tick trade-through,
a stop and target inside the same bar count as a stop, and a fill bar that also
touches the stop is a loss.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .sessions import add_time_keys, daily_levels
from .structures import daily_atr, fvgs, resample_ohlc, swing_points

# Minute of day (NY) at which each level becomes known; -1 = before the day starts.
LEVEL_KNOWN_AT = {
    "pdh": -1, "pdl": -1, "prev_rth_high": -1, "prev_rth_low": -1, "pwh": -1, "pwl": -1,
    "asia_high": 0, "asia_low": 0, "london_high": 300, "london_low": 300,
    "onh": 570, "onl": 570, "pre_high": 570, "pre_low": 570,
}
LOW_LEVELS = ("onl", "pdl", "asia_low", "london_low", "pre_low", "prev_rth_low", "pwl")
HIGH_LEVELS = ("onh", "pdh", "asia_high", "london_high", "pre_high", "prev_rth_high", "pwh")


@dataclass(frozen=True)
class Params:
    # time windows (minute of day, New York)
    ctx_start: int = 420          # bars loaded from here (structure context)
    sweep_start: int = 570        # 09:30
    sweep_end: int = 690          # 11:30: no new sweeps after
    entry_end: int = 720          # 12:00: no new entries after
    exit_mod: int = 955           # 15:55 time exit
    # liquidity
    sweep_levels: tuple = ("onl", "pdl", "asia_low", "london_low", "pre_low")
    target_levels: tuple = ("onh", "pdh", "asia_high", "london_high", "pre_high")
    max_level_dist_atr: float = 1.5
    stack_min: int = 1
    # structure
    tf: int = 1
    swing_n: int = 1
    mss_timeout: int = 60         # minutes from the sweep extreme to the shift
    require_mss: bool = True
    entry_type: str = "fvg"       # fvg | ifvg | mss_close
    entry_at: str = "ce"          # edge | ce | far  (position inside the gap)
    fvg_min_atr: float = 0.0
    ifvg_lookback: int = 30       # structure bars before the extreme to search for IFVGs
    # risk & exits
    stop_buf_atr: float = 0.0
    min_risk_atr: float = 0.03
    min_risk_pts: float = 0.0     # absolute floor on stop distance (cost control, in price units)
    max_risk_atr: float = 0.5
    target: str = "rr"            # rr | liq | eod
    rr: float = 2.0
    min_rr: float = 1.5           # liquidity targets closer than this are skipped
    max_rr: float = 6.0           # liquidity targets are capped here
    be_at_r: float = 0.0          # move stop to entry after +x R (0 = off)
    # model family
    mode: str = "reversal"        # reversal (sweep -> shift) | continuation (run -> breakaway FVG)
    stop_mode: str = "fvg"        # continuation stop: below FVG candle 1 ("fvg") or the run level
    need_opp_sweep: bool = False  # continuation only after the opposite side's liquidity was raided first
    # ifvg mode (DodgysDD-style inversion FVG, see docs/DODGYSDD.md)
    htf: int = 15                 # higher timeframe for swing sweeps and HTF FVGs (minutes)
    grace: int = 15               # the FVG must invert within this many structure bars
    ifvg_stop: str = "close"      # wick | ifvg | close (close back through the FVG; wick = hard stop)
    ifvg_target: str = "liq"      # rr | liq | rr_be (rr with stop to entry at the origin swing)
    ifvg_series: bool = False     # merge adjacent FVGs ("Series" detection)
    require_sweep: bool = False   # A+: a higher-timeframe swing swept during the leg
    require_htf_fvg: bool = False # iFVG overlaps a live higher-timeframe FVG
    sessions: tuple = ((570, 930),)  # confirmation windows (minute of day, NY)
    # filters
    regime_min: float = 0.0       # trade only if ATR14/ATR100 >= this (volatility expansion gate)
    regime_max: float = float("inf")
    smt: int = 0                  # 0 off, 1 other market failed >=1 swept level, 2 failed all
    sides: str = "both"           # both | long | short
    max_trades: int = 1
    # execution
    cost_pts: float = 1.0         # round-trip slippage + commission, index points
    tick: float = 0.25

    def replace(self, **kw) -> "Params":
        d = asdict(self)
        d.update(kw)
        return Params(**d)


@dataclass
class Day:
    tday: pd.Timestamp
    mod: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    levels: dict
    atr: float
    regime: float = float("nan")  # ATR14 / ATR100, both from prior days only


def prepare_days(df_m1: pd.DataFrame, ctx_start: int = 420, end_mod: int = 960) -> list[Day]:
    """Slice 1m bars per trading day into numpy arrays plus that day's levels/ATR."""
    df = add_time_keys(df_m1)
    lv = daily_levels(df)
    atr = daily_atr(lv["day_high"], lv["day_low"])
    regime = atr / daily_atr(lv["day_high"], lv["day_low"], 100)
    sel = df[(df["mod"] >= ctx_start) & (df["mod"] <= end_mod)]
    days = []
    names = list(LEVEL_KNOWN_AT)
    for tday, g in sel.groupby("tday", sort=True):
        a = atr.get(tday, np.nan)
        if not np.isfinite(a) or a <= 0:
            continue
        row = lv.loc[tday]
        days.append(Day(
            tday=tday,
            mod=g["mod"].to_numpy(np.int64),
            o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
            l=g["low"].to_numpy(float), c=g["close"].to_numpy(float),
            levels={k: float(row[k]) for k in names if k in row and np.isfinite(row[k])},
            atr=float(a),
            regime=float(regime.get(tday, np.nan)),
        ))
    return days


def _aligned_cum_extreme(day: Day, other: Day | None, start_mod: int, negate: bool):
    """Other market's running low (long space) from ``start_mod``, aligned to ``day`` bars."""
    if other is None:
        return None
    lows = (-other.h) if negate else other.l
    m = other.mod >= start_mod
    om, ol = other.mod[m], lows[m]
    if len(om) == 0:
        return None
    cm = np.minimum.accumulate(ol)
    pos = np.searchsorted(om, day.mod, side="right") - 1
    out = np.full(len(day.mod), np.inf)
    ok = pos >= 0
    out[ok] = cm[pos[ok]]
    return out


IDLE, SWEPT, ARMED, IN_TRADE = 0, 1, 2, 3


def _long_candidates(mod, o, h, l, c, sweep_lv, target_lv, atr, p: Params,
                     oth_cummin=None, oth_lv=None):
    """Candidate long trades for one day in 'long space' (prices may be negated)."""
    n = len(mod)
    trades = []
    if n < 30:
        return trades
    tfb = (mod - p.ctx_start) // p.tf
    ids, to, th, tl, tc, tend = resample_ohlc(o, h, l, c, tfb)
    ntf = len(ids)
    bull, bear = fvgs(th, tl)
    sh, _ = swing_points(th, tl, p.swing_n)
    tpos = np.searchsorted(ids, tfb)
    close_at = np.full(n, -1, np.int64)
    close_at[tend] = np.arange(ntf)

    first = int(np.searchsorted(mod, p.sweep_start))
    if first >= n:
        return trades
    open_px = o[first]
    max_dist = p.max_level_dist_atr * atr
    untouched = {k: v for k, v in sweep_lv.items()
                 if LEVEL_KNOWN_AT.get(k, 9999) <= p.sweep_start and open_px - max_dist <= v < open_px}
    tgt_untouched = {k: v for k, v in target_lv.items()
                     if LEVEL_KNOWN_AT.get(k, 9999) <= p.sweep_start and v > open_px}

    state = IDLE
    ext = ext_i = 0
    swept = []
    entry = stop = target = risk = 0.0
    arm_i = fill_i = -1
    mss_i = -1
    be_armed = False
    smt_flag = False
    run_high = -np.inf
    meta = {}

    def reset():
        nonlocal state, swept, mss_i
        state, swept, mss_i = IDLE, [], -1

    for i in range(first, n):
        m = mod[i]
        hi, lo, op, cl = h[i], l[i], o[i], c[i]

        if state == IN_TRADE:
            ex_px = reason = None
            if m >= p.exit_mod:
                ex_px, reason = op, "time"
            elif lo <= stop:
                ex_px, reason = min(stop, op), ("be" if be_armed and stop >= entry else "stop")
            elif hi >= target:
                ex_px, reason = target, "target"
            if ex_px is not None:
                pnl = ex_px - entry
                meta.update(exit_i=i, exit_mod=int(m), exit=ex_px, reason=reason,
                            r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
                trades.append(meta)
                meta = {}
                reset()
                if len(trades) >= p.max_trades:
                    break
                continue
            if p.be_at_r > 0 and not be_armed and hi >= entry + p.be_at_r * risk:
                stop = max(stop, entry)
                be_armed = True
            continue

        # track tested target liquidity and the running session high (long space)
        for k in [k for k, v in tgt_untouched.items() if hi >= v]:
            del tgt_untouched[k]
        run_high = max(run_high, hi)

        if state == ARMED:
            if m >= p.entry_end:
                reset()
                continue
            if lo <= entry - p.tick:
                fill = min(entry, op)
                meta.update(fill_i=i, entry_mod=int(m), entry=fill)
                entry_px = fill
                if lo <= stop:        # filled and stopped inside the same bar
                    ex_px = min(stop, op)
                    pnl = ex_px - entry_px
                    meta.update(exit_i=i, exit_mod=int(m), exit=ex_px, reason="stop",
                                r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
                    trades.append(meta)
                    meta = {}
                    reset()
                    if len(trades) >= p.max_trades:
                        break
                    continue
                entry = entry_px
                state = IN_TRADE
                be_armed = False
                continue
            if hi >= target:          # ran to target without a retrace: setup missed
                reset()
            continue

        # IDLE / SWEPT: detect sweeps (only inside the sweep window)
        if p.sweep_start <= m < p.sweep_end:
            taken = [k for k, v in untouched.items() if lo < v]
            if taken:
                if state == IDLE:
                    state, swept = SWEPT, []
                    ext, ext_i, mss_i = lo, i, -1
                for k in taken:
                    swept.append(k)
                    del untouched[k]
            if state == SWEPT and lo < ext:
                ext, ext_i, mss_i = lo, i, -1
        elif state == SWEPT and lo < ext:
            # a new low after the sweep window voids the setup
            reset()
            continue

        if state != SWEPT:
            continue
        j = close_at[i]
        if j < 0:
            continue                       # structure only updates on structure-bar closes
        if m >= p.entry_end or (m - mod[ext_i]) > p.mss_timeout:
            if (m - mod[ext_i]) > p.mss_timeout:
                reset()
            continue
        if len(swept) < p.stack_min:
            continue
        je = tpos[ext_i]

        # market structure shift: close above the last confirmed swing high before the extreme
        if mss_i < 0:
            ref = None
            for js in range(je - 1, -1, -1):
                if sh[js] and js + p.swing_n <= j:
                    ref = th[js]
                    break
            if ref is not None and tc[j] > ref:
                mss_i = i
        if p.require_mss and mss_i < 0:
            continue

        # entry zone
        zone = None
        if p.entry_type == "fvg":
            best = None
            for k in range(j, je + 1, -1):
                if bull[k] and k - 2 >= je and (tl[k] - th[k - 2]) >= p.fvg_min_atr * atr:
                    best = (th[k - 2], tl[k])        # (bottom, top)
                    break                              # most recent qualifying FVG
            zone = best
        elif p.entry_type == "ifvg":
            for k in range(je, max(je - p.ifvg_lookback, 1), -1):
                if bear[k] and (tl[k - 2] - th[k]) >= p.fvg_min_atr * atr and tc[j] > tl[k - 2]:
                    zone = (th[k], tl[k - 2])
                    break
        elif p.entry_type == "mss_close":
            if mss_i >= 0:
                zone = (tc[j], tc[j])
        if zone is None:
            continue
        bottom, top = zone
        e = {"edge": top, "ce": 0.5 * (top + bottom), "far": bottom}[p.entry_at]
        s = ext - p.stop_buf_atr * atr
        r = e - s
        if not (max(p.min_risk_atr * atr, p.min_risk_pts) <= r <= p.max_risk_atr * atr):
            continue
        if p.target == "rr":
            t = e + p.rr * r
        elif p.target == "liq":
            cands = [v for v in tgt_untouched.values() if v >= e + p.min_rr * r]
            if run_high >= e + p.min_rr * r:
                cands.append(run_high)
            t = min(cands) if cands else e + p.max_rr * r
            t = min(t, e + p.max_rr * r)
        else:
            t = np.inf
        if p.smt and oth_cummin is not None and oth_lv is not None:
            fails = [k for k in swept if k in oth_lv and oth_cummin[i] >= oth_lv[k]]
            ok = (len(fails) >= 1) if p.smt == 1 else (len(fails) == len(swept))
            if not ok:
                continue
            smt_flag = True
        else:
            smt_flag = False
        entry, stop, target, risk = e, s, t, r
        meta = dict(sweep_mod=int(mod[ext_i]), ext=ext, swept="|".join(swept), stack=len(swept),
                    mss_mod=int(mod[mss_i]) if mss_i >= 0 else -1, arm_mod=int(m), limit=e,
                    stop=s, target=t, risk=r, smt=smt_flag)
        if p.entry_type == "mss_close":
            meta.update(fill_i=i, entry_mod=int(m), entry=e)
            state = IN_TRADE
            be_armed = False
        else:
            state = ARMED
        arm_i = i

    if state == IN_TRADE and meta:     # data ended before the time exit
        ex_px = c[n - 1]
        pnl = ex_px - entry
        meta.update(exit_i=n - 1, exit_mod=int(mod[n - 1]), exit=ex_px, reason="eod",
                    r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
        trades.append(meta)
    return trades


def _long_continuation(mod, o, h, l, c, sweep_lv, target_lv, atr, p: Params,
                       oth_cummin=None, oth_lv=None):
    """Breakaway-gap continuation (long space): buy-side liquidity is run with
    displacement, the FVG left behind is bought on the retrace.

    ``target_lv`` here are the levels being *broken* (buy-side, above the open).
    Stop sits below the first candle of the displacement FVG (``stop_mode='fvg'``)
    or below the broken level (``stop_mode='level'``) minus ``stop_buf_atr``.
    """
    n = len(mod)
    trades = []
    if n < 30:
        return trades
    tfb = (mod - p.ctx_start) // p.tf
    ids, to, th, tl, tc, tend = resample_ohlc(o, h, l, c, tfb)
    bull, _ = fvgs(th, tl)
    close_at = np.full(n, -1, np.int64)
    close_at[tend] = np.arange(len(ids))
    first = int(np.searchsorted(mod, p.sweep_start))
    if first >= n:
        return trades
    open_px = o[first]
    max_dist = p.max_level_dist_atr * atr
    levels = {k: v for k, v in target_lv.items()
              if LEVEL_KNOWN_AT.get(k, 9999) <= p.sweep_start and open_px < v <= open_px + max_dist}
    opp_levels = [v for k, v in sweep_lv.items()
                  if LEVEL_KNOWN_AT.get(k, 9999) <= p.sweep_start and v < open_px]
    opp_swept = False
    broken = {}
    state = IDLE
    meta = {}
    entry = stop = target = risk = 0.0
    be_armed = False
    for i in range(first, n):
        m = mod[i]
        hi, lo, op = h[i], l[i], o[i]
        if state == IN_TRADE:
            ex_px = reason = None
            if m >= p.exit_mod:
                ex_px, reason = op, "time"
            elif lo <= stop:
                ex_px, reason = min(stop, op), ("be" if be_armed and stop >= entry else "stop")
            elif hi >= target:
                ex_px, reason = target, "target"
            if ex_px is not None:
                pnl = ex_px - entry
                meta.update(exit_i=i, exit_mod=int(m), exit=ex_px, reason=reason,
                            r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
                trades.append(meta)
                meta, state = {}, IDLE
                if len(trades) >= p.max_trades:
                    break
                continue
            if p.be_at_r > 0 and not be_armed and hi >= entry + p.be_at_r * risk:
                stop, be_armed = max(stop, entry), True
            continue
        if state == ARMED:
            if m >= p.entry_end:
                state, meta = IDLE, {}
                continue
            if lo <= entry - p.tick:
                fill = min(entry, op)
                meta.update(fill_i=i, entry_mod=int(m), entry=fill)
                if lo <= stop:
                    ex_px = min(stop, op)
                    pnl = ex_px - fill
                    meta.update(exit_i=i, exit_mod=int(m), exit=ex_px, reason="stop",
                                r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
                    trades.append(meta)
                    meta, state = {}, IDLE
                    if len(trades) >= p.max_trades:
                        break
                    continue
                entry, state, be_armed = fill, IN_TRADE, False
                continue
            if hi >= target or (close_at[i] >= 0 and tc[close_at[i]] < meta["level"]):
                state, meta = IDLE, {}         # ran away unfilled, or breakout failed
            continue
        # IDLE: record the opposite-side raid and the levels run inside the window
        if not opp_swept and any(lo < v for v in opp_levels):
            opp_swept = True
        if p.sweep_start <= m < p.sweep_end:
            for k in [k for k, v in levels.items() if hi > v]:
                broken[k] = (levels.pop(k), i)
        j = close_at[i]
        if j < 0 or not broken or m >= p.entry_end:
            continue
        if p.need_opp_sweep and not opp_swept:
            continue
        lvl = max(v for v, _ in broken.values())
        if tc[j] <= lvl:
            continue                                   # no acceptance above the run level
        brk_i = min(bi for _, bi in broken.values())
        jb = int(np.searchsorted(ids, (mod[brk_i] - p.ctx_start) // p.tf))
        zone = None
        for k in range(j, max(jb - 1, 1), -1):        # FVG of the breakout leg
            if bull[k] and (tl[k] - th[k - 2]) >= p.fvg_min_atr * atr:
                zone = (th[k - 2], tl[k], tl[k - 2])
                break
        if zone is None:
            continue
        bottom, top, c1_low = zone
        e = {"edge": top, "ce": 0.5 * (top + bottom), "far": bottom}[p.entry_at]
        s = (c1_low if p.stop_mode == "fvg" else lvl) - p.stop_buf_atr * atr
        r = e - s
        if not (max(p.min_risk_atr * atr, p.min_risk_pts) <= r <= p.max_risk_atr * atr):
            continue
        t = e + p.rr * r if p.target == "rr" else np.inf
        entry, stop, target, risk = e, s, t, r
        meta = dict(sweep_mod=int(mod[brk_i]), ext=lvl, swept="|".join(broken), stack=len(broken),
                    mss_mod=-1, arm_mod=int(m), limit=e, stop=s, target=t, risk=r, smt=False,
                    level=lvl)
        broken = {}
        state = ARMED
    if state == IN_TRADE and meta:
        pnl = c[n - 1] - entry
        meta.update(exit_i=n - 1, exit_mod=int(mod[n - 1]), exit=c[n - 1], reason="eod",
                    r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
        trades.append(meta)
    for t in trades:
        t.pop("level", None)
    return trades


def _long_ifvg(mod, o, h, l, c, sweep_lv, target_lv, atr, p: Params, oth_cummin=None, oth_lv=None):
    """DodgysDD-style inversion-FVG model (long space), see docs/DODGYSDD.md.

    A 3-bar swing high starts a down leg. The lowest single bearish FVG of the leg
    is the candidate; a structure-bar close above its top within ``grace`` bars
    inverts it and enters at that close. The A+ filter needs a higher-timeframe
    swing low swept during the leg. Stop: the leg's wick low since the FVG
    ("wick"), the FVG bottom ("ifvg"), or a close back below the FVG with the wick
    low as hard stop ("close"). The origin swing high is the break-even level.
    """
    n1 = len(mod)
    trades = []
    if n1 < 30:
        return trades
    tfb = (mod - p.ctx_start) // p.tf
    ids, to, th, tl, tc, tend = resample_ohlc(o, h, l, c, tfb)
    nt = len(ids)
    close_at = np.full(n1, -1, np.int64)
    close_at[tend] = np.arange(nt)
    k_start = ids * p.tf + p.ctx_start                     # structure-bar start minute
    # higher-timeframe swing lows (fractal on completed HTF bars) and HTF FVG zones
    hid, _, hh, hl, _, hend = resample_ohlc(o, h, l, c, (mod - p.ctx_start) // p.htf)
    new_swings, new_zones = {}, {}
    for q in range(1, len(hid) - 1):
        if hl[q] <= hl[q - 1] and hl[q] <= hl[q + 1]:
            new_swings.setdefault(int(hend[q + 1]), []).append(hl[q])
    for q in range(2, len(hid)):
        if hl[q] > hh[q - 2]:
            new_zones.setdefault(int(hend[q]), []).append([hh[q - 2], hl[q], True])
        if hh[q] < hl[q - 2]:
            new_zones.setdefault(int(hend[q]), []).append([hh[q], hl[q - 2], False])
    swings, zones = [], []

    origin = origin_k = None
    frozen, frozen_px = False, None
    live = None
    swept_flag = False
    cands = []
    run_high = -np.inf
    tgt_untouched = dict(target_lv)
    in_trade = False
    entry = stop = hard = target = risk = fvg_bot = be_lvl = 0.0
    be_armed = False
    meta = {}

    def in_session(minute):
        return any(a <= minute < b for a, b in p.sessions)

    for i in range(n1):
        m = mod[i]
        hi, lo, op = h[i], l[i], o[i]
        k = close_at[i]

        if in_trade:
            ex_px = reason = None
            if m >= p.exit_mod:
                ex_px, reason = op, "time"
            elif lo <= hard:
                ex_px, reason = min(hard, op), ("be" if be_armed else "stop")
            elif hi >= target:
                ex_px, reason = target, "target"
            elif p.ifvg_stop == "close" and k >= 0 and tc[k] < fvg_bot:
                ex_px, reason = tc[k], "close-stop"
            if ex_px is not None:
                pnl = ex_px - entry
                meta.update(exit_i=i, exit_mod=int(m), exit=ex_px, reason=reason,
                            r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
                trades.append(meta)
                meta, in_trade = {}, False
                if len(trades) >= p.max_trades:
                    break
            elif p.ifvg_target == "rr_be" and not be_armed and hi >= be_lvl:
                hard, be_armed = max(hard, entry), True

        run_high = max(run_high, hi)
        for kk in [kk for kk, v in tgt_untouched.items() if hi >= v]:
            del tgt_untouched[kk]

        if k >= 2:
            # ---- structure update at the close of structure bar k ----
            if th[k - 1] >= th[k - 2] and th[k - 1] >= th[k]:
                origin, origin_k = th[k - 1], k - 1
                frozen, frozen_px, live, swept_flag = False, None, None, False
            if origin_k is not None:
                if frozen and tl[k - 1] < frozen_px:
                    frozen = False
                if (not frozen) and th[k] < tl[k - 2] and (k - 2) >= origin_k - 1:
                    top, bot = tl[k - 2], th[k]
                    if live is not None and live not in cands:
                        live = None
                    if live is None:
                        live = {"k1": k, "top": top, "bot": bot, "origin": origin, "origin_k": origin_k, "swept": swept_flag}
                        cands.append(live)
                    elif p.ifvg_series and live["k1"] == k - 1:
                        live["top"], live["bot"], live["k1"] = max(live["top"], top), min(live["bot"], bot), k
                    elif bot < live["bot"]:
                        cands.remove(live)
                        live = {"k1": k, "top": top, "bot": bot, "origin": origin, "origin_k": origin_k, "swept": swept_flag}
                        cands.append(live)
            hit = [s for s in swings if tl[k] < s]
            if hit:
                swings = [s for s in swings if s not in hit]
                if origin_k is not None:
                    swept_flag = True
            if live is not None:
                live["swept"] = live["swept"] or swept_flag
            if origin_k is not None and not frozen and tl[k - 1] <= tl[k - 2] and tl[k - 1] <= tl[k]:
                frozen, frozen_px = True, tl[k - 1]
            for z in zones:
                if z[2] and z[1] is not None and tl[k] < z[0]:
                    z[2] = None                              # bullish zone traded through: mitigated
                elif (not z[2]) and z[2] is not None and th[k] > z[1]:
                    z[2] = None
            # ---- inversions ----
            for cand in list(cands):
                if tc[k] > cand["top"] and k > cand["k1"]:
                    cands.remove(cand)
                    e = tc[k]
                    if in_trade or len(trades) >= p.max_trades or e >= cand["origin"]:
                        continue
                    if not in_session(int(k_start[k])) or m >= p.exit_mod:
                        continue
                    if p.require_sweep and not cand["swept"]:
                        continue
                    if p.require_htf_fvg and not any(
                            z[2] is not None and not (cand["bot"] > z[1] or cand["top"] < z[0]) for z in zones[-3:]):
                        continue
                    wick = float(tl[cand["k1"]:k + 1].min())
                    s = {"wick": wick, "close": wick, "ifvg": cand["bot"]}[p.ifvg_stop]
                    r = e - s
                    if r <= 0 or r < max(p.min_risk_atr * atr, p.min_risk_pts) or r > p.max_risk_atr * atr:
                        continue
                    if p.ifvg_target == "liq":
                        lvls = [cand["origin"]] + [v for kk, v in tgt_untouched.items() if LEVEL_KNOWN_AT.get(kk, 9999) <= m]
                        if run_high > e:
                            lvls.append(run_high)
                        ok = [v for v in lvls if v >= e + p.min_rr * r]
                        t = min(min(ok), e + p.max_rr * r) if ok else e + p.rr * r
                    else:
                        t = e + p.rr * r
                    entry, hard, target, risk, fvg_bot, be_lvl = e, s, t, r, cand["bot"], cand["origin"]
                    be_armed, in_trade = False, True
                    meta = dict(sweep_mod=int(mod[i]), ext=wick, swept="htf-sweep" if cand["swept"] else "",
                                stack=int(cand["swept"]), mss_mod=int(k_start[k]), arm_mod=int(m), limit=e,
                                stop=s, target=t, risk=r, smt=False, fill_i=i, entry_mod=int(m), entry=e)
                elif k - cand["k1"] > p.grace:
                    cands.remove(cand)
                    if cand is live:
                        live = None
        # HTF structure that completes on this bar becomes usable from the next bar
        if i in new_swings:
            swings.extend(new_swings[i])
        if i in new_zones:
            zones.extend(new_zones[i])

    if in_trade and meta:
        pnl = c[n1 - 1] - entry
        meta.update(exit_i=n1 - 1, exit_mod=int(mod[n1 - 1]), exit=c[n1 - 1], reason="eod",
                    r_gross=pnl / risk, r_net=(pnl - p.cost_pts) / risk)
        trades.append(meta)
    return trades


def run_day(day: Day, p: Params, other: Day | None = None) -> list[dict]:
    out = []
    if p.regime_min > 0 or np.isfinite(p.regime_max):
        if not (np.isfinite(day.regime) and p.regime_min <= day.regime <= p.regime_max):
            return out
    lv = day.levels
    oth_lv = other.levels if other is not None else None
    gen = {"continuation": _long_continuation, "ifvg": _long_ifvg}.get(p.mode, _long_candidates)
    if p.sides in ("both", "long"):
        oc = _aligned_cum_extreme(day, other, p.sweep_start, negate=False) if p.smt else None
        for t in gen(day.mod, day.o, day.h, day.l, day.c,
                                  {k: lv[k] for k in p.sweep_levels if k in lv},
                                  {k: lv[k] for k in p.target_levels if k in lv},
                                  day.atr, p, oc, oth_lv):
            t["side"] = 1
            out.append(t)
    if p.sides in ("both", "short"):
        # mirror: buy-side levels become sell-side in negated space and vice versa
        mirror = {lo: hi for lo, hi in zip(LOW_LEVELS, HIGH_LEVELS)}
        mirror.update({hi: lo for lo, hi in zip(LOW_LEVELS, HIGH_LEVELS)})
        s_sweep = {mirror[k]: -lv[mirror[k]] for k in p.sweep_levels if mirror.get(k) in lv}
        s_tgt = {mirror[k]: -lv[mirror[k]] for k in p.target_levels if mirror.get(k) in lv}
        oc = _aligned_cum_extreme(day, other, p.sweep_start, negate=True) if p.smt else None
        o_lv = {k: -v for k, v in oth_lv.items()} if oth_lv is not None else None
        # the SMT check compares swept names; mirrored names keep their original keys
        for t in gen(day.mod, -day.o, -day.l, -day.h, -day.c, s_sweep, s_tgt,
                     day.atr, p, oc, o_lv):
            for k in ("ext", "limit", "stop", "target", "entry", "exit"):
                if k in t:
                    t[k] = -t[k]
            t["side"] = -1
            out.append(t)
    # portfolio rule: one position at a time, at most max_trades per day, in entry order
    out = [t for t in out if "entry_mod" in t]
    out.sort(key=lambda t: (t["fill_i"], -t["side"]))
    kept, busy_until = [], -1
    for t in out:
        if len(kept) >= p.max_trades:
            break
        if t["fill_i"] <= busy_until:
            continue
        kept.append(t)
        busy_until = t["exit_i"]
    for t in kept:
        t["tday"] = day.tday
        t["atr"] = day.atr
    return kept


def run(days: list[Day], p: Params, other_days: dict | None = None) -> pd.DataFrame:
    rows = []
    for d in days:
        od = other_days.get(d.tday) if other_days is not None else None
        rows.extend(run_day(d, p, od))
    cols = ["tday", "side", "sweep_mod", "swept", "stack", "mss_mod", "arm_mod", "entry_mod",
            "exit_mod", "ext", "limit", "entry", "stop", "target", "exit", "risk", "reason",
            "r_gross", "r_net", "smt", "atr"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols]

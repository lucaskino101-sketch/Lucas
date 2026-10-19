"""Frozen model definitions.

EXPANSION BREAKAWAY MODEL (EBM)
-------------------------------
Frozen on in-sample data (2005-2014) before the 2015-2020 holdout was run.

Thesis: an ICT "breakaway gap" (the FVG a displacement leaves when it runs a
liquidity pool) only carries continuation when the market is in a volatility
*expansion* regime. In normal or contracting regimes the same pattern loses.

Rules (longs; shorts are the exact mirror):
 1. Regime gate   ATR14 / ATR100 of prior daily ranges >= 1.10, else no trade today.
 2. Liquidity map At 09:30 NY: overnight high, previous-day high, pre-market high
                  (07:00-09:30), Asia high (20:00-24:00), London high (02:00-05:00),
                  previous cash-session high; keep those above the open and within
                  1.5 ATR of it.
 3. Run           09:30-11:30: price trades through one or more of those levels.
 4. Breakaway     A 15-minute candle (aligned to 09:30) closes above the highest run
                  level, and the breakout leg contains a bullish 15m FVG.
 5. Entry         Limit at the FVG's consequent encroachment (50%), live until 12:00;
                  cancelled if a 15m candle closes back below the run level.
 6. Stop          At the run level (the liquidity line). Stop distance must be
                  >= max(0.05 ATR, floor) and <= 0.6 ATR; floor 2.0 pt NQ / 1.0 pt ES.
 7. Exit          15:55 NY (hold the expansion leg into the close), or the stop.
 8. One trade per day.
"""
from __future__ import annotations

from .engine import Params

BUY_SIDE = ("onh", "pdh", "pre_high", "asia_high", "london_high", "prev_rth_high")
SELL_SIDE = ("onl", "pdl", "pre_low", "asia_low", "london_low", "prev_rth_low")

# Round-trip cost per contract in index points: conservative (stress) and realistic futures.
COSTS = {"NAS100_USD": {"conservative": 1.0, "realistic": 0.5},
         "SPX500_USD": {"conservative": 0.5, "realistic": 0.25}}
RISK_FLOOR = {"NAS100_USD": 2.0, "SPX500_USD": 1.0}


def ebm(inst: str = "NAS100_USD", cost: str = "conservative", exit: str = "eod") -> Params:
    """The Expansion Breakaway Model. ``exit``: 'eod' (primary), 'rr3' or 'eod_be' (pre-registered alternates)."""
    p = Params(
        mode="continuation", tf=15, entry_at="ce", stop_mode="level",
        sweep_levels=SELL_SIDE, target_levels=BUY_SIDE, max_level_dist_atr=1.5,
        sweep_start=570, sweep_end=690, entry_end=720, exit_mod=955,
        min_risk_atr=0.05, min_risk_pts=RISK_FLOOR[inst], max_risk_atr=0.6,
        regime_min=1.10, max_trades=1, target="eod",
        cost_pts=COSTS[inst][cost], tick=0.25,
    )
    if exit == "rr3":
        p = p.replace(target="rr", rr=3.0)
    elif exit == "eod_be":
        p = p.replace(be_at_r=1.0)
    return p


def reference_models(inst: str = "NAS100_USD", cost: str = "conservative") -> dict[str, Params]:
    """Textbook ICT setups, mechanized, pre-registered for the holdout comparison."""
    c = COSTS[inst][cost]
    return {
        # Liquidity sweep -> 1m market structure shift -> FVG at CE -> 2R ("2022 model" mechanics)
        "ICT 2022 model (1m, FVG CE, 2R)": Params(cost_pts=c),
        # 10:00-11:00 window, first displacement FVG after a sweep, target nearest opposing liquidity
        "Silver Bullet (10-11, FVG edge, liquidity target)": Params(
            sweep_start=600, sweep_end=660, entry_end=660, entry_at="edge", target="liq", cost_pts=c),
        # The EBM pattern with the regime gate switched off
        "Breakaway continuation, no regime gate": ebm(inst, cost).replace(regime_min=0.0),
    }

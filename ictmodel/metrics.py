"""Performance statistics for a trade list produced by ``engine.run``."""
from __future__ import annotations

import numpy as np
import pandas as pd


def equity_curve(trades: pd.DataFrame, risk_frac: float = 0.01, start: float = 1.0) -> pd.Series:
    """Compounded equity after each trade, risking ``risk_frac`` of equity per trade."""
    if trades.empty:
        return pd.Series(dtype=float)
    eq = start * np.cumprod(1.0 + risk_frac * trades["r_net"].to_numpy())
    return pd.Series(eq, index=pd.to_datetime(trades["tday"]).to_numpy())


def max_drawdown(eq: np.ndarray) -> float:
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.r_[1.0, eq])
    return float(((np.r_[1.0, eq] - peak) / peak).min())


def max_losing_streak(r: np.ndarray) -> int:
    best = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        best = max(best, cur)
    return best


def summarize(trades: pd.DataFrame, days: pd.DatetimeIndex | None = None,
              risk_frac: float = 0.01, col: str = "r_net") -> dict:
    """Headline statistics. ``days`` = all tradable days in the period (for Sharpe)."""
    if trades is None or trades.empty:
        return {"trades": 0}
    r = trades[col].to_numpy(float)
    wins, losses = r[r > 0], r[r <= 0]
    tdays = pd.to_datetime(trades["tday"])
    if days is None:
        days = pd.DatetimeIndex(sorted(tdays.unique()))
    years = max((days[-1] - days[0]).days / 365.25, 1e-9)
    daily = pd.Series(risk_frac * r, index=tdays).groupby(level=0).sum().reindex(days, fill_value=0.0)
    eq = np.cumprod(1.0 + risk_frac * r)
    sd = daily.std()
    return {
        "trades": int(len(r)),
        "trades_per_year": len(r) / years,
        "win_rate": float((r > 0).mean()),
        "avg_win_R": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_R": float(losses.mean()) if len(losses) else 0.0,
        "expectancy_R": float(r.mean()),
        "t_stat": float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if len(r) > 1 and r.std() > 0 else 0.0,
        "profit_factor": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.inf,
        "total_R": float(r.sum()),
        "cagr": float(eq[-1] ** (1 / years) - 1) if eq[-1] > 0 else -1.0,
        "max_dd": max_drawdown(eq),
        "sharpe": float(daily.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "max_losing_streak": max_losing_streak(r),
        "long_R": float(r[trades["side"].to_numpy() == 1].sum()),
        "short_R": float(r[trades["side"].to_numpy() == -1].sum()),
    }


def by_year(trades: pd.DataFrame, col: str = "r_net") -> pd.DataFrame:
    t = trades.copy()
    t["year"] = pd.to_datetime(t["tday"]).dt.year
    g = t.groupby("year")[col]
    return pd.DataFrame({"trades": g.size(), "win%": g.apply(lambda x: 100 * (x > 0).mean()),
                         "sum_R": g.sum(), "avg_R": g.mean()})


def fmt(s: dict) -> str:
    if s.get("trades", 0) == 0:
        return "no trades"
    return (f"n={s['trades']:5d} ({s['trades_per_year']:.0f}/yr) win={100*s['win_rate']:4.1f}% "
            f"avgW={s['avg_win_R']:+.2f} avgL={s['avg_loss_R']:+.2f} E={s['expectancy_R']:+.3f}R "
            f"t={s['t_stat']:+.2f} PF={s['profit_factor']:.2f} totR={s['total_R']:+7.1f} "
            f"CAGR@1%={100*s['cagr']:+5.1f}% DD={100*s['max_dd']:5.1f}% Sh={s['sharpe']:+.2f} "
            f"L/S R={s['long_R']:+.0f}/{s['short_R']:+.0f}")

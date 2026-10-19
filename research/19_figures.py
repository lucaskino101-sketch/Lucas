"""Figures + chart data for the write-up. Re-runs only the pre-registered models (no selection)."""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import ROOT, evaluate  # noqa: E402
from ictmodel.model import ebm, reference_models  # noqa: E402

FIG = os.path.join(ROOT, "results", "figures")
SURF, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
COL = {"EBM · Nasdaq-100": "#2a78d6", "EBM · S&P 500": "#eb6834",
       "ICT 2022 model · Nasdaq-100": "#1baf7a", "Silver Bullet · Nasdaq-100": "#eda100"}


def trades(inst, p):
    out = []
    for period in ("IS", "OOS"):
        t = evaluate([p], inst=inst, period=period, procs=1, keep_trades=True)[0]["trades"]
        out.append(t.assign(period=period))
    return pd.concat(out, ignore_index=True)


refs = reference_models("NAS100_USD")
series = {
    "EBM · Nasdaq-100": trades("NAS100_USD", ebm("NAS100_USD")),
    "EBM · S&P 500": trades("SPX500_USD", ebm("SPX500_USD")),
    "ICT 2022 model · Nasdaq-100": trades("NAS100_USD", refs["ICT 2022 model (1m, FVG CE, 2R)"]),
    "Silver Bullet · Nasdaq-100": trades("NAS100_USD", refs["Silver Bullet (10-11, FVG edge, liquidity target)"]),
}
data = {}
for name, t in series.items():
    t = t.sort_values(["tday"])
    d = pd.to_datetime(t.tday)
    daily = t.groupby(d).r_net.sum().cumsum()
    data[name] = {"dates": [x.strftime("%Y-%m-%d") for x in daily.index], "cumR": [round(v, 2) for v in daily.values],
                  "n": int(len(t)), "is_E": round(float(t[t.period == "IS"].r_net.mean()), 3),
                  "oos_E": round(float(t[t.period == "OOS"].r_net.mean()), 3)}
    t.to_csv(os.path.join(ROOT, "results", "holdout", f"trades_{name.split(' · ')[0].replace(' ', '_')}_{name.split(' · ')[1].replace(' ', '').replace('&', '')}.csv"), index=False)

# EBM yearly R (Nasdaq)
t = series["EBM · Nasdaq-100"]
yr = t.groupby(pd.to_datetime(t.tday).dt.year).r_net.agg(["size", "sum"])
data["ebm_nq_years"] = [{"year": int(y), "trades": int(r["size"]), "R": round(float(r["sum"]), 1)} for y, r in yr.iterrows()]
# regime-gate curve from the frozen in-sample selection grid (16_final_selection, conservative costs)
data["gate_curve"] = {"gates": [0.0, 1.0, 1.1, 1.2], "Nasdaq-100": [-0.04, 0.23, 0.58, 0.60], "S&P 500": [0.14, 0.27, 0.42, 0.62]}
json.dump(data, open(os.path.join(FIG, "chart_data.json"), "w"))


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def cum_chart(names, title, fname):
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150, facecolor=SURF)
    style(ax)
    for nm in names:
        x = pd.to_datetime(data[nm]["dates"])
        y = np.array(data[nm]["cumR"])
        ax.plot(x, y, color=COL[nm], lw=2, solid_capstyle="round")
        ax.plot(x[-1], y[-1], "o", ms=6, color=COL[nm], mec=SURF, mew=2)
        ax.annotate(f"{nm.split(' · ')[0]} ({nm.split(' · ')[1]})  {y[-1]:+.0f}R", (x[-1], y[-1]),
                    xytext=(8, 0), textcoords="offset points", va="center", fontsize=9, color=INK2)
    ax.axvline(pd.Timestamp("2015-01-01"), color=AXIS, lw=1)
    ax.axhline(0, color=AXIS, lw=1)
    ylim = ax.get_ylim()
    ax.text(pd.Timestamp("2015-02-01"), ylim[1] - (ylim[1] - ylim[0]) * 0.04, "holdout →", fontsize=9, color=MUTED, va="top")
    ax.text(pd.Timestamp("2014-12-01"), ylim[1] - (ylim[1] - ylim[0]) * 0.04, "← in-sample (development)", fontsize=9,
            color=MUTED, va="top", ha="right")
    ax.set_ylabel("cumulative R (net of costs)", color=MUTED, fontsize=9)
    ax.set_title(title, loc="left", fontsize=12, color="#0b0b0b", pad=12)
    ax.set_xlim(pd.Timestamp("2005-01-01"), pd.Timestamp("2023-06-01"))
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, fname), facecolor=SURF)
    plt.close(fig)


cum_chart(["ICT 2022 model · Nasdaq-100", "Silver Bullet · Nasdaq-100"],
          "Textbook ICT setups, mechanized: cumulative R, 1-pt costs", "textbook_ict_cumR.png")
cum_chart(["EBM · Nasdaq-100", "EBM · S&P 500"],
          "Expansion Breakaway Model: cumulative R, conservative costs", "ebm_cumR.png")

fig, ax = plt.subplots(figsize=(7.5, 4), dpi=150, facecolor=SURF)
style(ax)
g = data["gate_curve"]
xs = np.arange(len(g["gates"]))
for k, (nm, col) in enumerate((("Nasdaq-100", COL["EBM · Nasdaq-100"]), ("S&P 500", COL["EBM · S&P 500"]))):
    vals = g[nm]
    ax.bar(xs + (k - 0.5) * 0.3, vals, width=0.24, color=col, label=nm)
    for xi, v in zip(xs, vals):
        ax.text(xi + (k - 0.5) * 0.3, v + (0.02 if v >= 0 else -0.02), f"{v:+.2f}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=8, color=INK2)
ax.axhline(0, color=AXIS, lw=1)
ax.set_ylim(-0.16, 0.72)
ax.set_xticks(xs, ["no gate", "≥ 1.0", "≥ 1.1 (frozen)", "≥ 1.2"])
ax.set_ylabel("expectancy, R per trade (2005–2014)", color=MUTED, fontsize=9)
ax.set_title("Breakaway continuation only pays in volatility expansion (ATR14/ATR100)", loc="left", fontsize=11, pad=12)
ax.legend(frameon=False, fontsize=9, labelcolor=INK2)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "regime_gate.png"), facecolor=SURF)
plt.close(fig)
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("n", "is_E", "oos_E")} for k, v in data.items() if isinstance(v, dict) and "n" in v}, indent=1))
print(data["ebm_nq_years"])

"""Figures and chart data for the DodgysDD benchmark (reads results/dodgysdd/)."""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "results", "dodgysdd")
FIG = os.path.join(ROOT, "results", "figures")
SURF, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

s = pd.read_csv(os.path.join(D, "summary.csv"))
cons = s[s.cost == "conservative"]

# canonical cumulative R across both periods, per instrument (conservative costs)
out = {"canonical": {}, "variants": []}
for inst, key in (("NAS100_USD", "nq"), ("SPX500_USD", "es")):
    parts = [pd.read_csv(os.path.join(D, f"canonical_trades_{inst}_conservative_{p}.csv")) for p in ("IS", "OOS")]
    t = pd.concat(parts, ignore_index=True)
    daily = t.groupby(pd.to_datetime(t.tday)).r_net.sum().cumsum()
    w = daily.resample("W-FRI").last().dropna()
    out["canonical"][key] = {"d": [x.strftime("%Y-%m-%d") for x in w.index], "v": [round(v, 1) for v in w.values]}
for _, r in cons.iterrows():
    out["variants"].append({"inst": r.inst, "period": r.period, "E": round(r.expectancy_R, 3), "n": int(r.trades),
                            "canon": bool(r.canonical),
                            "label": f"{r.tf}m · {r.grade} · {r.session} · {r.stop} stop · {r.exit}"})
json.dump(out, open(os.path.join(FIG, "dodgysdd_chart_data.json"), "w"))

# strip plot: expectancy of every variant, per instrument x period
fig, ax = plt.subplots(figsize=(8.5, 4.2), dpi=150, facecolor=SURF)
ax.set_facecolor(SURF)
for sp in ("top", "right", "left"):
    ax.spines[sp].set_visible(False)
ax.spines["bottom"].set_color(AXIS)
ax.tick_params(colors=MUTED, labelsize=9, length=0)
ax.grid(axis="y", color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
groups = [("NAS100_USD", "IS", "Nasdaq-100\n2005–2014"), ("NAS100_USD", "OOS", "Nasdaq-100\n2015–2020"),
          ("SPX500_USD", "IS", "S&P 500\n2005–2014"), ("SPX500_USD", "OOS", "S&P 500\n2015–2020")]
rng = np.random.default_rng(0)
for gi, (inst, per, lab) in enumerate(groups):
    g = cons[(cons.inst == inst) & (cons.period == per)]
    x = gi + rng.uniform(-0.18, 0.18, len(g))
    ax.scatter(x[~g.canonical.values], g.expectancy_R.values[~g.canonical.values], s=18, color="#86b6ef", edgecolors=SURF, linewidths=0.8, zorder=2)
    cv = g[g.canonical]
    ax.scatter([gi], cv.expectancy_R.values, s=60, color="#2a78d6", edgecolors=SURF, linewidths=1.5, zorder=3)
    if len(cv):
        ax.annotate(f"canonical {cv.expectancy_R.values[0]:+.2f}R", (gi, cv.expectancy_R.values[0]), xytext=(10, 0),
                    textcoords="offset points", fontsize=8, color=INK2, va="center")
ax.axhline(0, color=AXIS, lw=1)
ax.set_xticks(range(len(groups)), [g[2] for g in groups])
ax.set_ylabel("expectancy, R per trade (after costs)", color=MUTED, fontsize=9)
ax.set_title("DodgysDD iFVG: all 72 variants, conservative costs", loc="left", fontsize=12, pad=12)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "dodgysdd_variants.png"), facecolor=SURF)
plt.close(fig)
print("written", os.path.join(FIG, "dodgysdd_variants.png"))

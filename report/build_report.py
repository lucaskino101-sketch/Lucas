"""Assemble report/ebm_report.html from results/ (chart data, holdout summary) and the template."""
import json
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
cd = json.load(open(os.path.join(ROOT, "results", "figures", "chart_data.json")))


def weekly(name):
    s = pd.Series(cd[name]["cumR"], index=pd.to_datetime(cd[name]["dates"]))
    w = s.resample("W-FRI").last().dropna()
    return {"d": [x.strftime("%Y-%m-%d") for x in w.index], "v": [round(v, 1) for v in w.values]}


data = {
    "ebm": {"nq": {"d": cd["EBM · Nasdaq-100"]["dates"], "v": cd["EBM · Nasdaq-100"]["cumR"]},
            "es": {"d": cd["EBM · S&P 500"]["dates"], "v": cd["EBM · S&P 500"]["cumR"]}},
    "textbook": {"ict": weekly("ICT 2022 model · Nasdaq-100"), "sb": weekly("Silver Bullet · Nasdaq-100")},
    "gate": cd["gate_curve"],
    "dodgy": json.load(open(os.path.join(ROOT, "results", "figures", "dodgysdd_chart_data.json"))),
}
ds = pd.read_csv(os.path.join(ROOT, "results", "dodgysdd", "summary.csv"))
canon = ds[ds.canonical & (ds.cost == "conservative")]


def _row(r):
    name = {"NAS100_USD": "Nasdaq-100", "SPX500_USD": "S&P 500"}[r.inst]
    per = "2005–14" if r.period == "IS" else "2015–20 holdout"
    sign = lambda v, d=2: ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.{d}f}"
    return (f'<tr{" class=\"hl\"" if r.period == "OOS" else ""}><td>{name}</td><td>{per}</td><td class="num">{int(r.trades):,}</td>'
            f'<td class="num">{100 * r.win_rate:.0f}</td><td class="num">{sign(r.expectancy_R)}R</td>'
            f'<td class="num">{sign(r.gross_E, 3)}R</td><td class="num">{sign(r.t_stat, 1)}</td>'
            f'<td class="num">{r.profit_factor:.2f}</td><td class="num">−{abs(100 * r.max_dd):.1f}%</td></tr>')


dodgy_rows = "".join(_row(r) for _, r in canon.sort_values(["inst", "period"]).iterrows())
DODGY_LEAD = open(os.path.join(HERE, "dodgy_lead.html")).read() if os.path.exists(os.path.join(HERE, "dodgy_lead.html")) else ""

# ---------- setup schematic (illustrative 15m candles) ----------
def y(p):
    return 270 - (p - 20) * 4


candles = [(33, 36, 30, 35), (35, 38.5, 34, 37.5), (37.5, 41.5, 36.5, 39), (39, 51, 38.5, 50), (50, 55, 46, 54),
           (54, 56, 50, 51), (51, 52, 43.5, 47), (47, 53, 46.5, 52), (52, 58, 51, 57), (57, 60, 55.5, 59),
           (59, 61, 57, 60.5), (60.5, 63, 59.5, 62), (70, 72.5, 68.5, 71.5), (71.5, 74, 70.5, 73)]
xs = [100 + 40 * i for i in range(12)] + [630, 670]
parts = []
level, fvg_lo, fvg_hi = 40, 41.5, 46
ce = (fvg_lo + fvg_hi) / 2
parts.append(f'<rect class="d-fvg" x="172" y="{y(fvg_hi):.1f}" width="428" height="{y(fvg_lo) - y(fvg_hi):.1f}"/>')
parts.append(f'<line class="d-level" x1="70" y1="{y(level):.1f}" x2="600" y2="{y(level):.1f}"/>')
parts.append(f'<line class="d-ce" x1="172" y1="{y(ce):.1f}" x2="600" y2="{y(ce):.1f}"/>')
for (o, h, l, c), x in zip(candles, xs):
    up = c >= o
    top, bot = y(max(o, c)), y(min(o, c))
    parts.append(f'<line class="d-wick" x1="{x}" y1="{y(h):.1f}" x2="{x}" y2="{y(l):.1f}"/>')
    parts.append(f'<rect class="{"d-up" if up else "d-down"}" x="{x - 8}" y="{top:.1f}" width="16" height="{max(bot - top, 1.5):.1f}"/>')
# fill marker + leader
parts.append(f'<line class="d-leader" x1="340" y1="{y(ce) + 6:.1f}" x2="340" y2="{y(level) + 10:.1f}"/>')
parts.append(f'<circle class="d-dot" cx="340" cy="{y(ce):.1f}" r="5"/>')
parts.append(f'<text class="d-label" x="340" y="{y(level) + 24:.1f}" text-anchor="middle">filled at CE</text>')
# exit marker
parts.append(f'<circle class="d-dot" cx="700" cy="{y(73):.1f}" r="5"/>')
parts.append(f'<text class="d-label" x="700" y="{y(73) - 14:.1f}" text-anchor="middle">exit 15:55</text>')
# right-margin labels
parts.append(f'<text class="d-label d-strong" x="610" y="{y(fvg_hi) - 4:.1f}">breakaway FVG</text>')
parts.append(f'<text class="d-label" x="610" y="{y(ce) + 4:.1f}">limit buy at CE</text>')
parts.append(f'<text class="d-label" x="610" y="{y(level) + 4:.1f}">stop at run level</text>')
parts.append(f'<text class="d-label d-muted" x="74" y="{y(level) - 6:.1f}">buy-side level</text>')
# window brackets
def bracket(x1, x2, yy, label):
    return (f'<path class="d-bracket" d="M{x1} {yy + 5} V{yy} H{x2} V{yy + 5}"/>'
            f'<text class="d-label d-muted" x="{(x1 + x2) / 2}" y="{yy - 5}" text-anchor="middle">{label}</text>')
parts.append(bracket(80, 400, 22, "run window 09:30–11:30"))
parts.append(bracket(280, 480, 52, "limit live until 12:00"))
# time axis
parts.append('<line class="d-axis" x1="70" y1="272" x2="565" y2="272"/><line class="d-axis" x1="600" y1="272" x2="720" y2="272"/>')
parts.append('<text class="d-label d-muted" x="583" y="276" text-anchor="middle">⋯</text>')
for x, lab in ((80, "09:30"), (160, "10:00"), (240, "10:30"), (320, "11:00"), (400, "11:30"), (480, "12:00"), (610, "15:30"), (690, "16:00")):
    parts.append(f'<line class="d-axis" x1="{x}" y1="272" x2="{x}" y2="277"/><text class="d-tick" x="{x}" y="292" text-anchor="middle">{lab}</text>')
setup_svg = ('<svg viewBox="0 0 760 304" role="img" aria-label="Illustrated long setup: price runs a buy-side level, '
             'a 15-minute candle closes above it leaving a bullish fair value gap, a limit buy fills at the gap midpoint '
             'with the stop at the level, and the position is held to 15:55.">' + "".join(p for p in parts if p) + "</svg>")

# ---------- session timeline ----------
def tx(t):
    return 180 + t * 560 / 22


rows = [("Overnight range", 0, 15.5, "map"), ("Asia range", 2, 6, "map"), ("London range", 8, 11, "map"),
        ("Pre-market range", 13, 15.5, "map"), ("Run window", 15.5, 17.5, "act"), ("Limit order live", 15.5, 18, "wash"),
        ("Hold to exit", 15.5, 21.917, "line")]
tl = []
for i, (lab, a, b, kind) in enumerate(rows):
    yy = 44 + i * 26
    tl.append(f'<text class="d-label" x="168" y="{yy + 4}" text-anchor="end">{lab}</text>')
    if kind == "line":
        tl.append(f'<line class="d-ce" x1="{tx(a):.1f}" y1="{yy}" x2="{tx(b):.1f}" y2="{yy}"/><circle class="d-dot" cx="{tx(b):.1f}" cy="{yy}" r="4"/>')
    else:
        cls = {"map": "d-map", "act": "d-act", "wash": "d-wash"}[kind]
        tl.append(f'<rect class="{cls}" x="{tx(a):.1f}" y="{yy - 6}" width="{tx(b) - tx(a):.1f}" height="12" rx="3"/>')
end_y = 44 + 6 * 26 + 14
tl.append(f'<line class="d-snap" x1="{tx(15.5):.1f}" y1="28" x2="{tx(15.5):.1f}" y2="{end_y}"/>')
tl.append(f'<text class="d-label d-strong" x="{tx(15.5):.1f}" y="20" text-anchor="middle">09:30 liquidity map</text>')
tl.append(f'<line class="d-axis" x1="{tx(0):.1f}" y1="{end_y + 4}" x2="{tx(22):.1f}" y2="{end_y + 4}"/>')
for t, lab in ((0, "18:00"), (3, "21:00"), (6, "00:00"), (9, "03:00"), (12, "06:00"), (15, "09:00"), (18, "12:00"), (21, "15:00")):
    tl.append(f'<line class="d-axis" x1="{tx(t):.1f}" y1="{end_y + 4}" x2="{tx(t):.1f}" y2="{end_y + 9}"/>'
              f'<text class="d-tick" x="{tx(t):.1f}" y="{end_y + 24}" text-anchor="middle">{lab}</text>')
TL_ARIA = ('One Globex day in New York time: the overnight, Asia, London and pre-market ranges set the liquidity levels; '
           'at 09:30 the map is fixed; runs count from 09:30 to 11:30; the limit order lives until 12:00; positions are held to 15:55.')
timeline_svg = (f'<svg class="tl-wide" viewBox="0 0 760 {end_y + 32}" role="img" aria-label="{TL_ARIA}">' + "".join(tl) + "</svg>")


# narrow variant for phones: labels sit above each bar instead of in a left column
def nx(t):
    return 14 + t * 332 / 22


nl = []
for i, (lab, a, b2, kind) in enumerate(rows):
    base = 50 + i * 34
    yb = base + 9
    lx = nx(a) + (6 if a >= 15.5 else 0)
    nl.append(f'<text class="d-label" x="{lx:.1f}" y="{base}">{lab}</text>')
    if kind == "line":
        nl.append(f'<line class="d-ce" x1="{nx(a):.1f}" y1="{yb}" x2="{nx(b2):.1f}" y2="{yb}"/><circle class="d-dot" cx="{nx(b2):.1f}" cy="{yb}" r="4"/>')
    else:
        cls = {"map": "d-map", "act": "d-act", "wash": "d-wash"}[kind]
        nl.append(f'<rect class="{cls}" x="{nx(a):.1f}" y="{yb - 5}" width="{nx(b2) - nx(a):.1f}" height="10" rx="3"/>')
n_end = 50 + 6 * 34 + 18
nl.append(f'<line class="d-snap" x1="{nx(15.5):.1f}" y1="30" x2="{nx(15.5):.1f}" y2="{n_end}"/>')
nl.append(f'<text class="d-label d-strong" x="{nx(15.5):.1f}" y="22" text-anchor="middle">09:30 liquidity map</text>')
nl.append(f'<line class="d-axis" x1="{nx(0):.1f}" y1="{n_end + 4}" x2="{nx(22):.1f}" y2="{n_end + 4}"/>')
for t, lab in ((0, "18:00"), (6, "00:00"), (12, "06:00"), (18, "12:00")):
    anchor = "start" if t == 0 else "middle"
    nl.append(f'<line class="d-axis" x1="{nx(t):.1f}" y1="{n_end + 4}" x2="{nx(t):.1f}" y2="{n_end + 9}"/>'
              f'<text class="d-tick" x="{nx(t):.1f}" y="{n_end + 24}" text-anchor="{anchor}">{lab}</text>')
timeline_svg += (f'<svg class="tl-narrow" viewBox="0 0 360 {n_end + 32}" role="img" aria-label="{TL_ARIA}">' + "".join(nl) + "</svg>")

html = open(os.path.join(HERE, "template.html")).read()
html = html.replace("__DATA__", json.dumps(data, separators=(",", ":")))
html = html.replace("__SETUP_SVG__", setup_svg).replace("__TIMELINE_SVG__", timeline_svg)
html = html.replace("__DODGY_ROWS__", dodgy_rows).replace("__DODGY_LEAD__", DODGY_LEAD)
open(os.path.join(HERE, "ebm_report.html"), "w").write(html)
print("wrote", os.path.join(HERE, "ebm_report.html"), len(html) // 1024, "KB")

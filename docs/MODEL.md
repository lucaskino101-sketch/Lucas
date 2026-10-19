# The Expansion Breakaway Model (EBM)

An ICT-style intraday model for Nasdaq-100 futures (NQ/MNQ) that trades the
**breakaway Fair Value Gap left when price runs a liquidity pool**, but only on
days when the market is in a **volatility-expansion regime**.

> **Status: research candidate, not a proven edge.** Out of sample (2015–2020) it
> made +0.31R per trade on Nasdaq-100 after conservative costs, but it lost on the
> S&P 500, EUR/USD, GBP/USD and gold, and its Nasdaq profit came from about three
> large trend days. Forward-test it before risking money. Details are in
> [Results](#results) and [Caveats](#caveats).

## Why this combination

Two findings from the research ([RESEARCH.md](RESEARCH.md)) drive the design:

1. Mechanized textbook ICT setups (liquidity sweep → market-structure shift →
   FVG entry, Silver Bullet, power of three, SMT filters) have **zero edge before
   costs and a large negative edge after costs** on 2005–2014 data. The same holds
   on the 2015–2020 holdout.
2. The one ICT pattern that responds to context is the **breakaway** reading:
   displacement *through* liquidity, leaving an FVG that price returns to and then
   continues. It loses on ordinary days but pays on days when daily volatility is
   expanding (ATR14 ≥ 1.1 × ATR100). Expected payoff rises steadily as the gate
   tightens, on both indices and in both halves of the development data. That
   matches ICT's own consolidation → expansion cycle and published evidence that
   intraday trends persist more in high-volatility regimes.

So EBM keeps the ICT vocabulary (liquidity, displacement, FVG, CE, killzone)
and adds one quantitative gate that decides *when* to use it.

## Rules

All times are New York. Rules are for longs; shorts are the exact mirror (swap
highs and lows).

| # | Step | Rule |
|---|------|------|
| 1 | **Regime gate** | Average daily (Globex) range of the last 14 days ÷ that of the last 100 days ≥ **1.10**. Otherwise no trade today. |
| 2 | **Liquidity map** (at 09:30) | Buy-side levels: overnight high (18:00–09:30), previous-day high, pre-market high (07:00–09:30), Asia high (20:00–24:00), London high (02:00–05:00), previous cash-session high. Keep those **above the 09:30 open** and **within 1.5 × ATR14** of it. |
| 3 | **Run** | Between **09:30 and 11:30**, price trades through one or more of those levels. |
| 4 | **Breakaway** | A **15-minute candle** (aligned to 09:30) **closes above the highest level that was run**, and the breakout leg (from the first run to now) contains a **bullish 15m FVG** (`low[k] > high[k-2]`). Use the most recent one. |
| 5 | **Entry** | Limit buy at the FVG's **consequent encroachment** (50%). Live until **12:00**. Cancel if a 15m candle closes back below the run level (failed breakout). |
| 6 | **Stop** | **At the run level** (the liquidity line). The stop distance must be at least max(0.05 × ATR14, 2.0 NQ points) and at most 0.6 × ATR14, otherwise skip. |
| 7 | **Exit** | **15:55** (hold the expansion leg into the close), or the stop. No target. |
| 8 | **Frequency** | One trade per day. The first side to fill wins and cancels the other. |

Pre-registered alternates, tested on the holdout alongside the primary rules:
a fixed **3R target**, or **move the stop to breakeven at +1R** and still exit at
15:55.

### Parameters (frozen before the holdout)

| Parameter | Value | Why |
|---|---|---|
| Regime gate | ATR14/ATR100 ≥ 1.10 | Middle of the region where every exit variant was positive on both indices in both halves of 2005–2014 |
| Structure timeframe | 15 min | 1–5 min structure was cost-dominated noise |
| Entry | FVG CE (50%) | CE beat the FVG edge on both indices |
| Stop | run level | Beat a stop below FVG candle 1 |
| Run window / entry deadline | 09:30–11:30 / 12:00 | NY AM killzone |
| Stop distance | ≥ max(0.05 ATR, 2 pt) and ≤ 0.6 ATR | Cost hygiene: costs stay ≤ ~0.5R |
| Costs assumed | NQ 1.0 pt (conservative) / 0.5 pt (realistic) per round trip; ES 0.5 / 0.25 | Commission plus slippage on stops |

## Results

Backtests use Oanda 1-minute mid-price CFD data as a futures proxy, with
conservative fills: limit orders need a one-tick trade-through, and a bar that
touches both stop and target counts as a stop. **Development** data is
2005–2014. The **holdout** (2015-01 to 2020-05) was run once, after the rules
above were frozen.

| Market · costs | Period | Trades | Win % | Expectancy | t | Profit factor | Max DD @1% risk |
|---|---|---:|---:|---:|---:|---:|---:|
| Nasdaq-100 · 1.0 pt | development | 78 | 33 | +0.58R | 1.6 | 1.75 | −12.2% |
| **Nasdaq-100 · 1.0 pt** | **holdout** | **58** | **36** | **+0.31R** | 1.0 | 1.45 | −7.3% |
| Nasdaq-100 · 0.5 pt | holdout | 58 | 36 | +0.35R | 1.2 | 1.54 | −7.0% |
| S&P 500 · 0.5 pt | development | 74 | 39 | +0.42R | 1.4 | 1.58 | −15.6% |
| **S&P 500 · 0.5 pt** | **holdout** | **47** | **19** | **−0.35R** | −1.1 | 0.60 | −18.3% |
| EUR/USD, GBP/USD, gold | 2005–2020 | 12–48 per period | — | all negative | — | — | — |

Holdout alternates on Nasdaq-100 at 1.0 pt: 3R target +0.19R; breakeven at +1R
+0.26R.

At 1% risk per trade, the Nasdaq holdout works out to roughly **+3% a year with a
7% max drawdown** from about 11 trades a year. That's a modest, positively skewed
profile, nowhere near "the most profitable model ever".

![EBM cumulative R](../results/figures/ebm_cumR.png)

## Caveats

- **Not statistically proven.** The holdout t-stat is about 1. At this trade count,
  +0.31R a trade is consistent with luck.
- **Outlier-driven.** Without its three best holdout trades, Nasdaq EBM was −3R.
  The model is a trend-day catcher: about 64% of trades lose and a few days carry
  the year.
- **Did not generalize.** The same rules lost on the S&P 500 holdout and on FX and
  gold, so treat any Nasdaq edge as possibly specific or accidental.
- **Data era and source.** CFD mid prices from 2005–2020, not exchange futures
  data, and nothing after May 2020. The 2021–2026 NQ market (0DTE options, a much
  higher price level, different participants) is untested. Use
  [`pine/expansion_breakaway_model.pine`](../pine/expansion_breakaway_model.pine)
  to forward-test it on real NQ futures data.
- **Execution.** The 15m CE limit can be missed on fast days, and slippage on
  stops through a liquidity level can exceed one tick.

## How to trade-test it

1. Load the Pine script on a **1-, 3- or 5-minute NQ1!/MNQ1! chart**. Leave the
   gate at 1.10, the floor at 2.0 pt and exit = hold to 15:55.
2. Check the regime panel each morning. A CLOSED gate means no EBM trade today,
   which is most days: the gate was open on 29% of days in 2005–2014 and 37% in
   2015–2020, and a setup forms on only some of those.
3. Paper-trade at least 30–50 signals. The positive skew needs a big sample before
   it can mean anything.
4. If you go live, size by risk (the script's "Risk % of equity" input) at ≤ 0.5–1%
   per trade. The losing streaks are long by design.

*Educational research, not financial advice.*

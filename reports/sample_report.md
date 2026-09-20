# Backtest report: EMA Cross Demo EA (reference implementation)

- Data: SYNTHETIC random-walk data (no real market, no edge by construction)
- Bars: 30,000 (2020-01-01 00:00:00 to 2023-06-03 23:00:00)
- Parameters: Params(fast=12, slow=26, atr_period=14, sl_atr_mult=2.0, reward_risk=1.5, lots=0.1, max_spread_points=30.0)
- Costs: half-spread on every fill (per-bar spread), 2.0 points slippage on market fills, 3.5 per lot per side commission

## Cost sensitivity

| Run | Trades | Net profit | Win rate | Profit factor | Expectancy/trade | Max drawdown |
|---|---|---|---|---|---|---|
| No costs (gross) | 992 | 357.78 | 38.9% | 1.04 | 0.36 | 417.90 |
| With costs (net) | 992 | -770.00 | 38.1% | 0.92 | -0.78 | 1,065.39 |

## In-sample vs out-of-sample (70% / 30% chronological split, costs on)

| Segment | Trades | Net profit | Win rate | Profit factor | Expectancy/trade | Max drawdown |
|---|---|---|---|---|---|---|
| In-sample | 679 | -567.89 | 38.7% | 0.91 | -0.84 | 891.56 |
| Out-of-sample | 313 | -202.12 | 36.7% | 0.93 | -0.65 | 605.10 |

## How to read this

The data is a random walk, so there is no edge to find. Any profit here is luck, and the gap between the gross and net rows is what costs alone do to a strategy. This report demonstrates the tooling (cost-aware simulation, out-of-sample check, reproducible output), not a profitable system.

Limits: balance is marked at trade close only (drawdown is closed-trade drawdown), bars have no intrabar ordering (stop assumed first when both levels are inside one bar), and results depend on the cost assumptions above.

# MT5 Demo EA: EMA Cross with ATR Stops (+ Python reference backtester)

An example of how I deliver an MT5 Expert Advisor: clean MQL5 source, a Python reference implementation of the same logic, unit tests, and a cost-aware backtest report.

> **This is a deliverable example, not a trading system.** The strategy is a textbook EMA cross. It has no demonstrated edge, and the sample report below is run on synthetic random-walk data on purpose. Nothing here is financial advice.

## What's in the repo

| Path | What it is |
|---|---|
| `mql5/EMA_Cross_Demo_EA.mq5` | The Expert Advisor (MQL5). Compiles with 0 errors, 0 warnings (see `reports/compile.log`). |
| `python/backtest.py` | Reference backtester that mirrors the EA's logic, with spread, slippage and commission. |
| `python/synthetic_data.py` | Synthetic OHLC generator, so the demo runs without any broker data. |
| `python/run_demo.py` | Runs the backtest and writes the report. Accepts your own OHLC CSV. |
| `tests/test_backtest.py` | 8 unit tests (signal timing, no lookahead, costs, spread filter, stop-first rule). |
| `reports/` | Sample report, trade list and compile log. |

## The strategy (evaluated once per new bar, on closed bars only)

- **Entry:** BUY when the fast EMA (12) crosses above the slow EMA (26); SELL on the opposite cross.
- **Exit:** ATR-based stop (2.0 x ATR(14)) and target (1.5 x the stop distance), or an opposite signal.
- **Filters:** skip entries when the spread is wider than a limit.
- **Sizing:** fixed lots, normalised to the symbol's volume step, min and max.

## Engineering details that matter in real deliveries

- Signals use only closed bars, and the Python tests check there is no lookahead in the indicators.
- Position lookup filters by magic number and symbol, so it works on both hedging and netting accounts.
- Stop and target levels are pushed out to the broker's minimum stop distance when needed.
- The reference backtester exists so the EA's logic can be checked independently of the MT5 Strategy Tester.
- Costs are modelled explicitly: half-spread on every fill, slippage on market fills, commission per lot.

## Run it

```bash
python -m unittest discover -s tests -v      # tests
python python/run_demo.py                     # synthetic-data report
python python/run_demo.py --csv my_data.csv   # your own data (time,open,high,low,close[,spread])
```

Requires Python 3.10+ with `pandas` and `numpy`. To compile the EA, open `mql5/EMA_Cross_Demo_EA.mq5` in MetaEditor and press F7.

## Sample result (synthetic data, so read it as a demonstration of the tooling)

| Run | Trades | Net profit | Win rate | Profit factor |
|---|---|---|---|---|
| No costs (gross) | 992 | 357.78 | 38.9% | 1.04 |
| With costs (net) | 992 | -770.00 | 38.1% | 0.92 |
| Out-of-sample (last 30%, costs on) | 313 | -202.12 | 36.7% | 0.93 |

On a random walk there is nothing to find, and costs turn a tiny gross gain into a loss. That is the point of the cost-aware setup: if a real strategy's edge disappears once costs are applied, it was never there. Full report: [`reports/sample_report.md`](reports/sample_report.md).

## Known limits

- Balance is marked at trade close only, so drawdown is closed-trade drawdown.
- OHLC bars have no intrabar ordering; when SL and TP are both inside one bar the stop is assumed to hit first.
- The MQL5 EA and the Python reference implement the same rules, but I have not run them tick-for-tick against each other on identical broker data. Verify on your own history before relying on any result.

## Need something like this?

I build MT5 EAs, backtesting pipelines and Python trading automation. Message me on Upwork with your rules and I'll reply with a short spec.

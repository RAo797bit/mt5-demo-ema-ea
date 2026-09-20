"""Unit tests for the reference backtester. Run: python -m unittest discover -s tests -v"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from backtest import CostModel, Instrument, Params, compute_indicators, run_backtest, signal_at, summarize  # noqa: E402
from synthetic_data import generate_ohlc  # noqa: E402


def bars_from_closes(closes, spread=10.0, wick=0.0005):
    closes = np.asarray(closes, dtype=float)
    open_ = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=len(closes), freq="1h"),
            "open": open_,
            "high": np.maximum(open_, closes) + wick,
            "low": np.minimum(open_, closes) - wick,
            "close": closes,
            "spread": spread,
        }
    )


class SignalTests(unittest.TestCase):
    def test_buy_cross_uses_closed_bars_only(self):
        fast = np.array([0.9, 0.9, 0.9, 1.1, 1.2])
        slow = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        # cross happened on bar 3 (fast 1.1 > slow, previous fast 0.9 <= slow) -> act at bar 4
        self.assertEqual(signal_at(fast, slow, 4), 1)
        # at bar 3 the cross bar itself is not yet closed, so no signal
        self.assertEqual(signal_at(fast, slow, 3), 0)

    def test_sell_cross(self):
        fast = np.array([1.0, 1.0, 1.1, 0.9, 0.8])
        slow = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        self.assertEqual(signal_at(fast, slow, 4), -1)

    def test_no_lookahead_in_indicators(self):
        df = generate_ohlc(n_bars=400, seed=3)
        full = compute_indicators(df, Params())
        cut = compute_indicators(df.iloc[:300], Params())
        np.testing.assert_allclose(full["fast"].iloc[:300].to_numpy(), cut["fast"].to_numpy())
        np.testing.assert_allclose(full["atr"].iloc[:300].to_numpy(), cut["atr"].to_numpy(), equal_nan=True)


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.df = generate_ohlc(n_bars=6000, seed=11)

    def test_deterministic(self):
        a = run_backtest(self.df)
        b = run_backtest(self.df)
        pd.testing.assert_frame_equal(a, b)

    def test_costs_reduce_profit(self):
        gross = run_backtest(self.df, costs=CostModel.none())
        net = run_backtest(self.df, costs=CostModel())
        self.assertGreater(len(net), 10)
        self.assertLess(net["NetProfit"].sum(), gross["NetProfit"].sum())

    def test_wide_spread_blocks_entries(self):
        wide = self.df.copy()
        wide["spread"] = 500.0
        self.assertEqual(len(run_backtest(wide, Params(max_spread_points=30.0))), 0)

    def test_stop_first_when_both_levels_in_one_bar(self):
        closes = [1.00] * 40 + list(np.linspace(1.00, 1.05, 30))    # flat, then an uptrend -> BUY cross
        df = bars_from_closes(closes)
        p = Params(fast=3, slow=8, atr_period=5, sl_atr_mult=1.0, reward_risk=1.0)

        baseline = run_backtest(df, p, CostModel.none())
        self.assertGreater(len(baseline), 0, "test setup should produce at least one trade")
        entry_time = baseline["OpenTime"].iloc[0]
        entry_idx = int(df.index[df["time"] == entry_time][0])

        # blow-out entry bar that touches both the stop and the target
        df.loc[entry_idx, "high"] = df.loc[entry_idx, "close"] + 1.0
        df.loc[entry_idx, "low"] = df.loc[entry_idx, "close"] - 1.0
        trades = run_backtest(df, p, CostModel.none())

        first = trades.iloc[0]
        self.assertEqual(first["OpenTime"], entry_time)
        self.assertEqual(first["CloseTime"], entry_time)
        self.assertEqual(first["Reason"], "sl")

    def test_summary_fields(self):
        s = summarize(run_backtest(self.df))
        for key in ("trades", "net_profit", "win_rate_pct", "profit_factor", "max_drawdown"):
            self.assertIn(key, s)
        self.assertGreaterEqual(s["max_drawdown"], 0.0)


if __name__ == "__main__":
    unittest.main()

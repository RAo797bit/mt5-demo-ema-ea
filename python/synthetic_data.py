"""
Synthetic OHLC generator so the demo runs without any broker data.

The series is a random walk with volatility clustering and a spread that widens
with volatility. A random walk has NO exploitable edge, which is the point: on
data like this a trend-following EA should lose money once costs are applied,
and the report should show that honestly. Swap in real history (exported from
MT5) to evaluate an actual strategy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_ohlc(n_bars: int = 30_000, seed: int = 7, start_price: float = 1.10,
                  freq: str = "1h", base_vol: float = 0.0006, steps_per_bar: int = 12) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # volatility clustering: log-vol follows a slow AR(1) process
    log_vol = np.zeros(n_bars)
    for i in range(1, n_bars):
        log_vol[i] = 0.98 * log_vol[i - 1] + 0.12 * rng.standard_normal()
    vol = base_vol * np.exp(log_vol - log_vol.var() / 2.0)

    # sub-bar steps give realistic open/high/low/close relationships
    steps = rng.standard_normal((n_bars, steps_per_bar)) * (vol[:, None] / np.sqrt(steps_per_bar))
    log_price = np.log(start_price) + np.cumsum(steps.reshape(-1)).reshape(n_bars, steps_per_bar)
    price = np.exp(log_price)

    close = price[:, -1]
    open_ = np.concatenate([[start_price], close[:-1]])
    high = np.maximum(price.max(axis=1), open_)
    low = np.minimum(price.min(axis=1), open_)

    # spread in points, wider when volatility is high
    spread = np.clip(8.0 + 900.0 * (vol - base_vol) + rng.normal(0, 1.5, n_bars), 4.0, 60.0)

    time = pd.date_range("2020-01-01", periods=n_bars, freq=freq)
    return pd.DataFrame(
        {"time": time, "open": open_, "high": high, "low": low, "close": close, "spread": spread}
    )

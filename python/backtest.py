"""
Cost-aware reference backtester for the EMA cross demo EA.

It mirrors the logic in mql5/EMA_Cross_Demo_EA.mq5:
  * signals use CLOSED bars only (bar t-1 vs t-2), acted on at the open of bar t
  * BUY  when fast EMA crosses above slow EMA, SELL when it crosses below
  * an opposite signal closes the open position, then opens the new one
  * SL = entry -/+ ATR * sl_atr_mult, TP = entry +/- ATR * sl_atr_mult * reward_risk
  * entries are skipped when the bar's spread exceeds max_spread_points

Costs modelled (all adverse to the trader):
  * half the spread on every fill
  * slippage on market-type fills (entries, stop-loss exits, signal exits)
  * commission per lot per side

Assumptions worth knowing:
  * OHLC bars have no intrabar ordering. If SL and TP are both inside one bar,
    the stop is assumed to hit first (the pessimistic choice).
  * Balance is marked at trade close only, so drawdown is a closed-trade
    drawdown and understates intrabar floating losses.
  * ATR is the simple average of true range, which matches MT5's iATR.
  * EMA is seeded with the first close (pandas ewm adjust=False), matching MT5.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Instrument:
    """Contract specification for a USD-quoted instrument (EURUSD-like by default)."""
    point: float = 0.00001
    contract_size: float = 100_000.0


@dataclass(frozen=True)
class CostModel:
    slippage_points: float = 2.0
    commission_per_lot_per_side: float = 3.5   # account currency

    @staticmethod
    def none() -> "CostModel":
        return CostModel(slippage_points=0.0, commission_per_lot_per_side=0.0)


@dataclass(frozen=True)
class Params:
    fast: int = 12
    slow: int = 26
    atr_period: int = 14
    sl_atr_mult: float = 2.0
    reward_risk: float = 1.5
    lots: float = 0.10
    max_spread_points: float = 30.0


def compute_indicators(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Add fast/slow EMA and ATR columns (no lookahead: value at row i uses rows <= i)."""
    out = df.copy()
    out["fast"] = out["close"].ewm(span=p.fast, adjust=False).mean()
    out["slow"] = out["close"].ewm(span=p.slow, adjust=False).mean()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [out["high"] - out["low"], (out["high"] - prev_close).abs(), (out["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(p.atr_period).mean()
    return out


def signal_at(fast: np.ndarray, slow: np.ndarray, t: int) -> int:
    """Signal to act on at the open of bar t, from closed bars t-1 and t-2."""
    if fast[t - 1] > slow[t - 1] and fast[t - 2] <= slow[t - 2]:
        return 1
    if fast[t - 1] < slow[t - 1] and fast[t - 2] >= slow[t - 2]:
        return -1
    return 0


def run_backtest(
    df: pd.DataFrame,
    params: Params = Params(),
    costs: CostModel = CostModel(),
    instrument: Instrument = Instrument(),
) -> pd.DataFrame:
    """
    Run the strategy over `df` (columns: time, open, high, low, close, optional spread in points).
    Returns one row per closed trade.
    """
    data = compute_indicators(df.reset_index(drop=True), params)
    n = len(data)
    o = data["open"].to_numpy()
    h = data["high"].to_numpy()
    lo = data["low"].to_numpy()
    fast = data["fast"].to_numpy()
    slow = data["slow"].to_numpy()
    atr = data["atr"].to_numpy()
    times = data["time"].to_numpy()
    spread_pts = data["spread"].to_numpy() if "spread" in data.columns else np.full(n, 10.0)

    pt = instrument.point
    slip = costs.slippage_points * pt
    commission_round_trip = costs.commission_per_lot_per_side * params.lots * 2.0
    first = max(params.slow, params.atr_period) + 2   # warm-up

    trades: list[dict] = []
    pos: Optional[dict] = None

    def close_trade(exit_time, exit_price_raw, reason, exit_spread_pts, market_fill):
        """Close `pos` at raw level; apply half-spread (+ slippage if a market-type fill)."""
        nonlocal pos
        adverse = (exit_spread_pts * pt) / 2.0 + (slip if market_fill else 0.0)
        exit_price = exit_price_raw - adverse * pos["side"]    # long sells lower, short buys higher
        gross = (exit_price - pos["entry"]) * pos["side"] * instrument.contract_size * params.lots
        trades.append(
            {
                "OpenTime": pos["time"],
                "CloseTime": exit_time,
                "Side": "BUY" if pos["side"] == 1 else "SELL",
                "Entry": pos["entry"],
                "Exit": exit_price,
                "Reason": reason,
                "Lots": params.lots,
                "Commission": commission_round_trip,
                "NetProfit": gross - commission_round_trip,
            }
        )
        pos = None

    for t in range(first, n):
        sig = signal_at(fast, slow, t)

        # 1) signal handling at the open of bar t
        if sig != 0:
            if pos is not None and pos["side"] != sig:
                close_trade(times[t], o[t], "signal", spread_pts[t], market_fill=True)
            if pos is None and spread_pts[t] <= params.max_spread_points and not np.isnan(atr[t - 1]):
                half = (spread_pts[t] * pt) / 2.0
                entry = o[t] + (half + slip) * sig            # long buys higher, short sells lower
                sl_dist = atr[t - 1] * params.sl_atr_mult
                tp_dist = sl_dist * params.reward_risk
                pos = {
                    "side": sig,
                    "entry": entry,
                    "sl": entry - sl_dist * sig,
                    "tp": entry + tp_dist * sig,
                    "time": times[t],
                }

        # 2) SL / TP inside bar t (stop first if both are touched)
        if pos is not None:
            if pos["side"] == 1:
                hit_sl, hit_tp = lo[t] <= pos["sl"], h[t] >= pos["tp"]
            else:
                hit_sl, hit_tp = h[t] >= pos["sl"], lo[t] <= pos["tp"]
            if hit_sl:
                close_trade(times[t], pos["sl"], "sl", spread_pts[t], market_fill=True)
            elif hit_tp:
                close_trade(times[t], pos["tp"], "tp", spread_pts[t], market_fill=False)

    if pos is not None:                                       # close any open trade at the last close
        last = n - 1
        close_trade(times[last], data["close"].to_numpy()[last], "end", spread_pts[last], market_fill=True)

    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame, initial_balance: float = 10_000.0) -> dict:
    """Headline statistics from a trade list."""
    if trades.empty:
        return {"trades": 0, "net_profit": 0.0}
    pnl = trades["NetProfit"].to_numpy()
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    balance = initial_balance + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[initial_balance], balance]))[1:]
    max_dd = float(np.max(peak - balance))
    gross_loss = abs(losses.sum())
    return {
        "trades": int(len(pnl)),
        "net_profit": float(pnl.sum()),
        "win_rate_pct": float(len(wins) / len(pnl) * 100.0),
        "profit_factor": float(wins.sum() / gross_loss) if gross_loss > 0 else float("inf"),
        "expectancy_per_trade": float(pnl.mean()),
        "max_drawdown": max_dd,
        "max_drawdown_pct_of_peak": float(np.max((peak - balance) / peak) * 100.0),
        "total_commission": float(trades["Commission"].sum()),
    }


def params_dict(p: Params) -> dict:
    return asdict(p)

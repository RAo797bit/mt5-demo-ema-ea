"""
Run the reference backtest on synthetic data and write a report.

    python python/run_demo.py                 # synthetic data
    python python/run_demo.py --csv my.csv    # your own OHLC export

CSV columns: time,open,high,low,close[,spread]   (spread in points, optional)
Outputs:  reports/sample_report.md  and  reports/sample_trades.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest import CostModel, Instrument, Params, run_backtest, summarize
from synthetic_data import generate_ohlc

ROOT = Path(__file__).resolve().parent.parent


def fmt_row(label: str, s: dict) -> str:
    if s["trades"] == 0:
        return f"| {label} | 0 | - | - | - | - | - |"
    pf = "inf" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    return (
        f"| {label} | {s['trades']} | {s['net_profit']:,.2f} | {s['win_rate_pct']:.1f}% | "
        f"{pf} | {s['expectancy_per_trade']:.2f} | {s['max_drawdown']:,.2f} |"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="OHLC csv (time,open,high,low,close[,spread])")
    ap.add_argument("--out", default=str(ROOT / "reports"))
    args = ap.parse_args()

    synthetic = args.csv is None
    df = generate_ohlc() if synthetic else pd.read_csv(args.csv, parse_dates=["time"])
    params, inst = Params(), Instrument()

    gross = run_backtest(df, params, CostModel.none(), inst)
    net = run_backtest(df, params, CostModel(), inst)

    split = int(len(df) * 0.7)
    is_net = run_backtest(df.iloc[:split], params, CostModel(), inst)
    oos_net = run_backtest(df.iloc[split:], params, CostModel(), inst)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    net.to_csv(out / "sample_trades.csv", index=False)

    src = "SYNTHETIC random-walk data (no real market, no edge by construction)" if synthetic else args.csv
    lines = [
        "# Backtest report: EMA Cross Demo EA (reference implementation)",
        "",
        f"- Data: {src}",
        f"- Bars: {len(df):,} ({df['time'].iloc[0]} to {df['time'].iloc[-1]})",
        f"- Parameters: {params}",
        "- Costs: half-spread on every fill (per-bar spread), 2.0 points slippage on market fills, "
        "3.5 per lot per side commission",
        "",
        "## Cost sensitivity",
        "",
        "| Run | Trades | Net profit | Win rate | Profit factor | Expectancy/trade | Max drawdown |",
        "|---|---|---|---|---|---|---|",
        fmt_row("No costs (gross)", summarize(gross)),
        fmt_row("With costs (net)", summarize(net)),
        "",
        "## In-sample vs out-of-sample (70% / 30% chronological split, costs on)",
        "",
        "| Segment | Trades | Net profit | Win rate | Profit factor | Expectancy/trade | Max drawdown |",
        "|---|---|---|---|---|---|---|",
        fmt_row("In-sample", summarize(is_net)),
        fmt_row("Out-of-sample", summarize(oos_net)),
        "",
        "## How to read this",
        "",
    ]
    if synthetic:
        lines += [
            "The data is a random walk, so there is no edge to find. Any profit here is luck, and the gap between "
            "the gross and net rows is what costs alone do to a strategy. This report demonstrates the tooling "
            "(cost-aware simulation, out-of-sample check, reproducible output), not a profitable system.",
        ]
    else:
        lines += ["Compare the gross and net rows first: if the edge disappears with costs, it was never there."]
    lines += [
        "",
        "Limits: balance is marked at trade close only (drawdown is closed-trade drawdown), bars have no intrabar "
        "ordering (stop assumed first when both levels are inside one bar), and results depend on the cost "
        "assumptions above.",
        "",
    ]
    (out / "sample_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

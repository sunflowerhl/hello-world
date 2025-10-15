#!/usr/bin/env python3
"""Fetch Xueqiu K-line data for a Hong Kong stock and plot trades."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Iterable, List, Optional

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import requests
from zoneinfo import ZoneInfo

HK_TZ = ZoneInfo("Asia/Hong_Kong")


class XueqiuClient:
    """Small helper to fetch K-line data from Xueqiu."""

    BASE_URL = "https://stock.xueqiu.com/v5/stock/chart/kline.json"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._prime_session()

    def _prime_session(self) -> None:
        # Fetching the landing page gives us the cookies required for API calls.
        self._session.get("https://xueqiu.com", timeout=10)

    def fetch_kline(
        self,
        symbol: str,
        period: str = "day",
        count: int = -120,
        indicator: str = "kline",
        begin: Optional[int] = None,
    ) -> pd.DataFrame:
        if begin is None:
            begin = int(dt.datetime.now(tz=dt.timezone.utc).timestamp() * 1000)

        params = {
            "symbol": symbol,
            "begin": begin,
            "period": period,
            "type": "before",
            "count": count,
            "indicator": indicator,
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36",
            "Referer": f"https://xueqiu.com/S/{symbol}",
            "Accept": "application/json, text/plain, */*",
        }

        resp = self._session.get(self.BASE_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("error_code"):
            raise RuntimeError(
                f"Xueqiu returned error {payload['error_code']}: {payload.get('error_description')}"
            )

        chart = payload.get("data", {})
        column_names = chart.get("column") or []
        raw_items = chart.get("item") or []

        if not column_names or not raw_items:
            raise RuntimeError("Empty response returned from Xueqiu")

        records = [dict(zip(column_names, row)) for row in raw_items]
        frame = pd.DataFrame.from_records(records)

        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True).dt.tz_convert(HK_TZ)
        frame = frame.rename(
            columns={
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
            }
        )
        frame = frame.set_index("timestamp")
        frame.index.name = "Date"
        return frame[["Open", "High", "Low", "Close", "Volume"]]


def _normalize_trade_times(times: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(times)
    if getattr(parsed.dt, "tz", None) is None:
        parsed = parsed.dt.tz_localize(HK_TZ, nonexistent="shift_forward", ambiguous="NaT")
    else:
        parsed = parsed.dt.tz_convert(HK_TZ)
    return parsed


def load_trades(path: Path) -> pd.DataFrame:
    """Load trade data from a CSV or JSON file."""
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        trades = pd.DataFrame(data)
    else:
        trades = pd.read_csv(path)

    if trades.empty:
        return trades

    if "time" not in trades or "price" not in trades or "side" not in trades:
        raise ValueError("Trade data must include 'time', 'price', and 'side' columns")

    trades["time"] = _normalize_trade_times(trades["time"])
    if "quantity" not in trades:
        trades["quantity"] = 1.0
    trades["quantity"] = trades["quantity"].fillna(1.0).astype(float)
    trades = trades.sort_values("time")
    return trades


def build_trade_plots(trades: pd.DataFrame) -> List[dict]:
    addplots: List[dict] = []
    if trades.empty:
        return addplots

    buys = trades[trades["side"].str.lower() == "buy"].copy()
    sells = trades[trades["side"].str.lower() == "sell"].copy()

    if not buys.empty:
        series = pd.Series(buys["price"].values, index=buys["time"], name="Buys")
        addplots.append(
            mpf.make_addplot(
                series,
                type="scatter",
                markersize=120,
                marker="^",
                color="green",
                panel=0,
            )
        )

    if not sells.empty:
        series = pd.Series(sells["price"].values, index=sells["time"], name="Sells")
        addplots.append(
            mpf.make_addplot(
                series,
                type="scatter",
                markersize=120,
                marker="v",
                color="red",
                panel=0,
            )
        )

    return addplots


def compute_equity_curve(kline: pd.DataFrame, trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)

    trades = trades.copy()
    trades["side"] = trades["side"].str.lower()

    timeline = kline.index.union(trades["time"])
    closes = kline["Close"].reindex(timeline).sort_index().ffill().dropna()

    if closes.empty:
        return pd.Series(dtype=float)

    equity_values: List[float] = []
    position = 0.0
    cash = 0.0
    trade_records = trades.to_dict("records")
    trade_idx = 0

    for ts, price in closes.items():
        while trade_idx < len(trade_records) and trade_records[trade_idx]["time"] <= ts:
            trade = trade_records[trade_idx]
            qty = float(trade.get("quantity", 1.0) or 0.0)
            side = trade.get("side", "").lower()
            trade_price = float(trade.get("price", 0.0))

            if side == "buy":
                position += qty
                cash -= trade_price * qty
            elif side == "sell":
                position -= qty
                cash += trade_price * qty

            trade_idx += 1

        equity_values.append(cash + position * float(price))

    return pd.Series(equity_values, index=closes.index, name="Equity")


def plot(symbol: str, kline: pd.DataFrame, trades: pd.DataFrame, output: Path) -> None:
    addplots = build_trade_plots(trades)
    equity = compute_equity_curve(kline, trades)
    if not equity.empty:
        addplots.append(
            mpf.make_addplot(
                equity,
                panel=0,
                color="blue",
                secondary_y=True,
                width=1,
            )
        )

    title = f"{symbol} K-line with trades"
    style = mpf.make_mpf_style(base_mpf_style="yahoo", rc={"figure.figsize": (12, 8)})
    fig, axes = mpf.plot(
        kline,
        type="candle",
        style=style,
        addplot=addplots or None,
        volume=True,
        returnfig=True,
        title=title,
    )

    if not trades.empty:
        ax = axes[0]
        for _, row in trades.iterrows():
            ax.annotate(
                row.get("note", row["side"].capitalize()),
                xy=(row["time"], row["price"]),
                xytext=(0, 20 if row["side"].lower() == "buy" else -30),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color="black",
                arrowprops=dict(arrowstyle="-", color="gray"),
            )

    if not equity.empty and hasattr(axes[0], "right_ax") and axes[0].right_ax:
        axes[0].right_ax.set_ylabel("Equity", color="blue")
        axes[0].right_ax.tick_params(axis="y", colors="blue")

    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Xueqiu symbol, e.g. HK00700 for Tencent")
    parser.add_argument(
        "--period",
        default="day",
        choices=["day", "week", "month", "60m", "30m", "15m", "5m", "1m"],
        help="K-line period on Xueqiu",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=-120,
        help="How many candles to request. Negative values request historical data.",
    )
    parser.add_argument(
        "--trades",
        type=Path,
        required=False,
        help="CSV or JSON file containing trades with columns time, price, side, [note]",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("kline_with_trades.png"),
        help="Where to save the generated chart.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    client = XueqiuClient()
    kline = client.fetch_kline(args.symbol, period=args.period, count=args.count)

    trades = pd.DataFrame()
    if args.trades:
        trades = load_trades(args.trades)

    plot(args.symbol, kline, trades, args.output)
    print(f"Chart saved to {args.output}")


if __name__ == "__main__":
    main()

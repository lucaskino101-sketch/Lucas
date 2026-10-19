"""Load 1-minute OHLC data and convert it to New York exchange time.

Source: Oanda M1 mid-price candles mirrored in the public GitHub repo
FutureSharks/financial-data (2005-01 .. 2020-05). Timestamps in the CSVs are UTC.
All ICT session logic runs on America/New_York wall-clock time, so we store a
tz-naive NY timestamp next to the UTC epoch.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

RAW_ROOT = os.environ.get(
    "ICT_RAW_ROOT",
    "/home/user/futuresharks/financial-data/pyfinancialdata/data/currencies/oanda",
)
CACHE_DIR = os.environ.get(
    "ICT_CACHE_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")
)

INSTRUMENTS = ("NAS100_USD", "SPX500_USD", "EUR_USD", "GBP_USD", "XAU_USD")


def _read_raw(instrument: str, root: str = RAW_ROOT) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(root, instrument, "*", "*.csv")))
    if not files:
        raise FileNotFoundError(f"no CSVs for {instrument} under {root}")
    parts = [pd.read_csv(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    return df[["time", "open", "high", "low", "close", "volume"]]


def build_cache(instrument: str, root: str = RAW_ROOT, cache_dir: str = CACHE_DIR) -> str:
    df = _read_raw(instrument, root)
    ny = df["time"].dt.tz_convert("America/New_York")
    out = pd.DataFrame(
        {
            "ts_ny": ny.dt.tz_localize(None),
            "open": df["open"].astype("float64"),
            "high": df["high"].astype("float64"),
            "low": df["low"].astype("float64"),
            "close": df["close"].astype("float64"),
            "volume": df["volume"].astype("int64"),
        }
    )
    # Repair the rare candle whose high/low do not bracket open/close.
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{instrument}_m1.parquet")
    out.to_parquet(path, index=False)
    return path


def load_m1(instrument: str, start: str | None = None, end: str | None = None,
            cache_dir: str = CACHE_DIR) -> pd.DataFrame:
    """1-minute bars indexed by tz-naive New York time."""
    path = os.path.join(cache_dir, f"{instrument}_m1.parquet")
    if not os.path.exists(path):
        build_cache(instrument, cache_dir=cache_dir)
    df = pd.read_parquet(path).set_index("ts_ny")
    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.index < pd.Timestamp(end)]
    return df

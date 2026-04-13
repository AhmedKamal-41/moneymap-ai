"""
alpha_vantage_client.py
-----------------------
Alpha Vantage REST client for equity and ETF daily prices.

Loads ``ALPHA_VANTAGE_API_KEY`` from the environment via ``python-dotenv``.

Free tier: about 5 calls per minute; this client sleeps between calls with
``time.sleep`` to reduce throttling.

On failure or missing key, returns synthetic sample OHLCV data and emits warnings.
"""
from __future__ import annotations

import logging
import os
import time
import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"
_RATE_LIMIT_SLEEP = 12  # seconds between calls (free tier)
_LAST_CALL_TS: list[float] = [0.0]

_LOCAL_CACHE: dict = {}
_CACHE_TTL = 3600


def _warn(message: str) -> None:
    warnings.warn(message, UserWarning, stacklevel=2)
    log.warning(message)


def _cache_get(key: str):
    full = f"_av_{key}"
    try:
        import streamlit as st

        entry = st.session_state.get(full)
    except Exception:
        entry = _LOCAL_CACHE.get(full)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data) -> None:
    full = f"_av_{key}"
    entry = {"data": data, "ts": time.time()}
    try:
        import streamlit as st

        st.session_state[full] = entry
    except Exception:
        _LOCAL_CACHE[full] = entry


def _empty_ohlcv_df() -> pd.DataFrame:
    """Daily OHLCV frame (Alpha Vantage TIME_SERIES_DAILY_ADJUSTED shape)."""
    cols = [
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend_amount",
        "split_coefficient",
    ]
    return pd.DataFrame(
        {c: pd.Series(dtype="float64") for c in cols},
        index=pd.DatetimeIndex([], name="date"),
    )


def _sample_ohlcv(symbol: str, lookback_years: int) -> pd.DataFrame:
    """Deterministic synthetic daily prices for offline demos."""
    lookback_years = max(1, int(lookback_years))
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=lookback_years)
    idx = pd.date_range(start=start, end=end, freq="B")
    n = len(idx)
    if n == 0:
        return _empty_ohlcv_df()

    seed = abs(hash(symbol)) % (2**31)
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.00035, 0.011, n)))
    wobble = rng.uniform(0.997, 1.003, n)
    open_ = np.r_[close[0] * 0.999, close[:-1]]
    high = np.maximum.reduce([open_, close]) * wobble
    low = np.minimum.reduce([open_, close]) / wobble
    vol = rng.integers(80_000, 250_000, n)
    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "adjusted_close": close,
            "volume": vol.astype(float),
            "dividend_amount": np.zeros(n),
            "split_coefficient": np.ones(n),
        },
        index=idx,
    )
    df.index.name = "date"
    return df


def _throttled_get(params: dict, api_key: str) -> dict:
    """
    GET Alpha Vantage with spacing between calls.

    Raises ``AlphaVantageError`` / ``AlphaVantageRateLimitError`` on API issues.
    """
    elapsed = time.time() - _LAST_CALL_TS[0]
    if elapsed < _RATE_LIMIT_SLEEP:
        sleep_for = _RATE_LIMIT_SLEEP - elapsed
        log.debug("Alpha Vantage rate-limit sleep %.1fs", sleep_for)
        time.sleep(sleep_for)

    params = {**params, "apikey": api_key}
    try:
        resp = requests.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        raise AlphaVantageError(f"HTTP error: {exc}") from exc
    finally:
        _LAST_CALL_TS[0] = time.time()

    if "Error Message" in data:
        raise AlphaVantageError(f"Alpha Vantage error: {data['Error Message']}")
    if "Note" in data:
        raise AlphaVantageRateLimitError(
            "Alpha Vantage rate limit reached. "
            f"API message: {data['Note']}"
        )
    if "Information" in data:
        raise AlphaVantageRateLimitError(
            f"Alpha Vantage quota message: {data['Information']}"
        )

    return data


def _parse_daily_adjusted(data: dict) -> pd.DataFrame:
    """Parse ``TIME_SERIES_DAILY_ADJUSTED`` JSON into a sorted DataFrame."""
    ts = data.get("Time Series (Daily)", {})
    if not ts:
        raise AlphaVantageError("Empty time series in response.")

    rows = {}
    for date_str, vals in ts.items():
        rows[date_str] = {
            k.split(". ", 1)[-1].replace(" ", "_"): v for k, v in vals.items()
        }

    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.to_datetime(df.index, errors="coerce")
    df.index.name = "date"
    df = df.sort_index()
    df = df.apply(pd.to_numeric, errors="coerce")
    df.attrs["is_fallback"] = False
    return df


class AlphaVantageClient:
    """Fetch daily equity / ETF prices from Alpha Vantage."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key: str = api_key or os.getenv("ALPHA_VANTAGE_API_KEY", "")
        if not self.api_key:
            _warn("ALPHA_VANTAGE_API_KEY is not set — price requests will use synthetic sample data.")

    def _available(self) -> bool:
        return bool(self.api_key)

    def get_daily_prices(self, symbol: str, lookback_years: int = 2) -> pd.DataFrame:
        """
        Daily OHLCV + ``adjusted_close`` for ``symbol`` (last ``lookback_years`` years).

        Returns synthetic sample OHLCV on missing key, rate limit, HTTP/API errors,
        or an empty post-filter window.
        """
        cache_key = f"daily_{symbol}_{lookback_years}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        if not self._available():
            _warn(f"Alpha Vantage: cannot fetch {symbol!r} without API key — using synthetic sample.")
            out = _sample_ohlcv(symbol, lookback_years)
            out.attrs["is_fallback"] = True
            _cache_set(cache_key, out)
            return out

        try:
            output_size = "full" if lookback_years > 0 else "compact"
            data = _throttled_get(
                {
                    "function": "TIME_SERIES_DAILY_ADJUSTED",
                    "symbol": symbol,
                    "outputsize": output_size,
                },
                self.api_key,
            )
            df = _parse_daily_adjusted(data)
            cutoff = pd.Timestamp.today() - pd.DateOffset(years=lookback_years)
            df = df[df.index >= cutoff]
            if df.empty:
                raise AlphaVantageError("No rows in requested lookback window.")
            df.attrs["is_fallback"] = False
        except AlphaVantageRateLimitError as exc:
            _warn(f"Alpha Vantage rate limit for {symbol!r}: {exc} — using synthetic sample.")
            df = _sample_ohlcv(symbol, lookback_years)
            df.attrs["is_fallback"] = True
        except AlphaVantageError as exc:
            _warn(f"Alpha Vantage error for {symbol!r}: {exc} — using synthetic sample.")
            df = _sample_ohlcv(symbol, lookback_years)
            df.attrs["is_fallback"] = True

        _cache_set(cache_key, df)
        return df

    def get_etf_prices(
        self,
        symbols: List[str],
        lookback_years: int = 2,
        column: str = "adjusted_close",
    ) -> pd.DataFrame:
        """
        One column per symbol (default: ``adjusted_close``), index ``date``.

        Empty DataFrame if no symbols succeed. Rate limiting applies between symbols.
        """
        cache_key = f"etf_{'_'.join(sorted(symbols))}_{lookback_years}_{column}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        frames: Dict[str, pd.Series] = {}
        any_fallback = False
        for symbol in symbols:
            df = self.get_daily_prices(symbol, lookback_years=lookback_years)
            any_fallback = any_fallback or bool(df.attrs.get("is_fallback", False))
            if column in df.columns and not df.empty:
                frames[symbol] = df[column].rename(symbol)
            elif not df.empty:
                _warn(f"Alpha Vantage: column {column!r} missing for {symbol!r} — skipping.")

        if not frames:
            combined = pd.DataFrame(index=pd.DatetimeIndex([], name="date"))
            combined.attrs["is_fallback"] = True
        else:
            combined = pd.concat(frames.values(), axis=1).sort_index()
            combined.index.name = "date"
            combined = combined.ffill(limit=5)
            combined.attrs["is_fallback"] = any_fallback

        _cache_set(cache_key, combined)
        return combined

    def get_daily_returns(self, symbol: str, lookback_years: int = 2) -> pd.Series:
        """Daily log-returns from ``adjusted_close``; empty series if no prices."""
        prices = self.get_daily_prices(symbol, lookback_years)
        if "adjusted_close" not in prices.columns or prices.empty:
            return pd.Series(dtype="float64", name=symbol)
        ac = prices["adjusted_close"].dropna()
        return np.log(ac / ac.shift(1)).dropna().rename(symbol)


class AlphaVantageError(RuntimeError):
    """Alpha Vantage API or transport error."""


class AlphaVantageRateLimitError(AlphaVantageError):
    """Free-tier rate limit or quota messaging from the API."""

"""
bls_client.py
-------------
Bureau of Labor Statistics (BLS) Public Data API v2 REST client.

``BLS_API_KEY`` is optional but increases the per-day request limit
(unauthenticated: 25 series/day; registered: 500 series/day).

Caches successful responses in ``st.session_state`` when available (TTL 1 hour).
On failure, returns deterministic synthetic sample frames and emits warnings.
"""
from __future__ import annotations

import logging
import os
import time
import warnings
from typing import List, Optional

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# ── Series catalogue ──────────────────────────────────────────────────────────
CPI_ALL_URBAN = "CUUR0000SA0"  # CPI-U, all items, not seasonally adjusted
CPI_CORE = "CUUR0000SA0L1E"  # CPI-U, ex food & energy
AVG_HOURLY_WAGES = "CES0500000003"  # Avg hourly earnings, all private, SA

# ── Cache helpers ─────────────────────────────────────────────────────────────
_LOCAL_CACHE: dict = {}
_CACHE_TTL = 3600  # seconds

_RETRY_DELAYS = [2, 5, 10]  # seconds between retries


def _warn(message: str) -> None:
    warnings.warn(message, UserWarning, stacklevel=2)
    log.warning(message)


def _cache_get(key: str):
    full = f"_bls_{key}"
    try:
        import streamlit as st

        entry = st.session_state.get(full)
    except Exception:
        entry = _LOCAL_CACHE.get(full)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data) -> None:
    full = f"_bls_{key}"
    entry = {"data": data, "ts": time.time()}
    try:
        import streamlit as st

        st.session_state[full] = entry
    except Exception:
        _LOCAL_CACHE[full] = entry


def _empty_cpi_wage_df() -> pd.DataFrame:
    """Empty frame with same columns as successful CPI/wage pulls."""
    return pd.DataFrame(
        {"value": pd.Series(dtype="float64"), "yoy_pct": pd.Series(dtype="float64")},
        index=pd.DatetimeIndex([], name="date"),
    )


def _sample_cpi_wage_df(lookback_years: int, *, wage: bool) -> pd.DataFrame:
    """Monthly synthetic CPI or wage index for demo charts."""
    lookback_years = max(1, int(lookback_years))
    today = pd.Timestamp.today().normalize()
    start = (today - pd.DateOffset(years=lookback_years + 1)).replace(day=1)
    idx = pd.date_range(start=start, end=today, freq="MS")
    n = len(idx)
    rng = np.random.default_rng(7 if wage else 11)
    base = 28.0 if wage else 280.0
    drift = 0.15 if wage else 0.35
    vals = base + drift * np.arange(n) + rng.normal(0, 0.08, n)
    df = pd.DataFrame({"value": vals}, index=idx)
    df.index.name = "date"
    df["yoy_pct"] = df["value"].pct_change(12) * 100.0
    cutoff = pd.Timestamp.today() - pd.DateOffset(years=lookback_years)
    df = df[df.index >= cutoff]
    return df


# ── BLS JSON → DataFrame ──────────────────────────────────────────────────────
def _parse_bls_series(series_data: list) -> pd.DataFrame:
    """
    Convert the BLS JSON ``data`` array to a DataFrame indexed by ``date``.

    BLS months use ``M01``–``M12`` (``M13`` = annual average, dropped).
    The API returns data newest-first; output is sorted oldest-first.
    """
    records = []
    for item in series_data:
        period = item.get("period", "")
        if not period.startswith("M") or period == "M13":
            continue
        month = int(period[1:])
        year = int(item["year"])
        try:
            value = float(item["value"])
        except (ValueError, KeyError):
            continue
        records.append({"date": pd.Timestamp(year=year, month=month, day=1), "value": value})

    if not records:
        return pd.DataFrame(columns=["value"]).rename_axis("date")

    df = pd.DataFrame(records).set_index("date").sort_index()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def _add_yoy(df: pd.DataFrame) -> pd.DataFrame:
    """Append a ``yoy_pct`` column computed from the ``value`` column."""
    df = df.copy()
    df["yoy_pct"] = df["value"].pct_change(12) * 100
    return df


# ── Client ────────────────────────────────────────────────────────────────────
class BLSClient:
    """
    Fetch CPI and wage series from the BLS Public Data API v2.

    Public methods return DataFrames indexed by ``date`` with columns
    ``value`` and ``yoy_pct`` (synthetic sample on failure).
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key: str = api_key or os.getenv("BLS_API_KEY", "")

    def _post(self, series_ids: List[str], start_year: int, end_year: int) -> Optional[dict]:
        """
        POST to the BLS API with retries.

        Returns parsed JSON on success, or ``None`` after failed attempts
        (after emitting a warning).
        """
        payload: dict = {
            "seriesid": series_ids,
            "startyear": str(start_year),
            "endyear": str(end_year),
            "calculations": True,
        }
        if self.api_key:
            payload["registrationkey"] = self.api_key

        last_exc: Optional[Exception] = None
        for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
            if delay:
                log.debug("BLS retry %d — waiting %ds", attempt, delay)
                time.sleep(delay)
            try:
                resp = requests.post(BLS_API_URL, json=payload, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "REQUEST_FAILED":
                    msgs = data.get("message", ["Unknown BLS error"])
                    _warn(f"BLS API error: {'; '.join(str(m) for m in msgs)}")
                    return None
                return data
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                log.warning("BLS timeout (attempt %d): %s", attempt, exc)
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                log.warning("BLS request failed (attempt %d): %s", attempt, exc)

        _warn(f"BLS API unreachable after retries: {last_exc}")
        return None

    def _fetch_series(self, series_id: str, lookback_years: int = 3) -> pd.DataFrame:
        """
        Fetch a single BLS series for the past ``lookback_years`` years.

        Returns an empty DataFrame on transport/API/parse failure.
        """
        today = pd.Timestamp.today()
        end_year = today.year
        start_year = end_year - lookback_years

        data = self._post([series_id], start_year, end_year)
        if data is None:
            return _parse_bls_series([])

        try:
            series_data = data["Results"]["series"][0]["data"]
        except (KeyError, IndexError) as exc:
            _warn(f"Unexpected BLS response structure for {series_id!r}: {exc}")
            return _parse_bls_series([])

        return _parse_bls_series(series_data)

    def get_cpi_data(self, lookback_years: int = 3) -> pd.DataFrame:
        """
        Return monthly CPI-U (all items, NSA) for the past N years.

        Columns: ``value``, ``yoy_pct`` (year-over-year %). Synthetic sample on failure.
        """
        cache_key = f"cpi_{lookback_years}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        df = self._fetch_series(CPI_ALL_URBAN, lookback_years=lookback_years + 1)
        if df.empty:
            _warn("BLS CPI: no live data — using synthetic sample series.")
            out = _sample_cpi_wage_df(lookback_years, wage=False)
            out.attrs["is_fallback"] = True
            _cache_set(cache_key, out)
            return out

        df = _add_yoy(df)
        cutoff = pd.Timestamp.today() - pd.DateOffset(years=lookback_years)
        df = df[df.index >= cutoff]
        df.attrs["is_fallback"] = False

        _cache_set(cache_key, df)
        return df

    def get_wage_data(self, lookback_years: int = 3) -> pd.DataFrame:
        """
        Return monthly average hourly earnings (all private employees).

        Columns: ``value`` ($/hr), ``yoy_pct``. Synthetic sample on failure.
        """
        cache_key = f"wages_{lookback_years}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        df = self._fetch_series(AVG_HOURLY_WAGES, lookback_years=lookback_years + 1)
        if df.empty:
            _warn("BLS wages: no live data — using synthetic sample series.")
            out = _sample_cpi_wage_df(lookback_years, wage=True)
            out.attrs["is_fallback"] = True
            _cache_set(cache_key, out)
            return out

        df = _add_yoy(df)
        cutoff = pd.Timestamp.today() - pd.DateOffset(years=lookback_years)
        df = df[df.index >= cutoff]
        df.attrs["is_fallback"] = False

        _cache_set(cache_key, df)
        return df

    def get_latest_cpi_yoy(self) -> Optional[float]:
        """Return the most recent CPI YoY % as a scalar."""
        df = self.get_cpi_data()
        clean = df["yoy_pct"].dropna()
        return round(float(clean.iloc[-1]), 2) if len(clean) else None

    def get_latest_wage_growth(self) -> Optional[float]:
        """Return the most recent wage YoY % as a scalar."""
        df = self.get_wage_data()
        clean = df["yoy_pct"].dropna()
        return round(float(clean.iloc[-1]), 2) if len(clean) else None


class BLSClientError(RuntimeError):
    """Optional: raised by strict callers if BLS handling must fail hard."""

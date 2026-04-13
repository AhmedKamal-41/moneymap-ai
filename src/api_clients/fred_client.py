"""
fred_client.py
--------------
FRED (Federal Reserve Economic Data) API client using ``fredapi``.

Loads ``FRED_API_KEY`` from the environment via ``python-dotenv``.
On failure or when the client is unavailable, methods return **deterministic
synthetic sample series** (so charts always render) and emit warnings.
``_is_fallback`` on the macro dashboard is ``True`` whenever sample data is
used. ``FREDClientError`` remains for optional strict handling.
"""
from __future__ import annotations

import logging
import os
import time
import warnings
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

try:
    from fredapi import Fred

    _FREDAPI_AVAILABLE = True
except ImportError:
    Fred = None  # type: ignore[misc, assignment]
    _FREDAPI_AVAILABLE = False

# ── Series catalogue (FRED IDs) ───────────────────────────────────────────────
class _S:
    DFF = "DFF"  # Fed Funds Rate (effective), daily
    CPIAUCSL = "CPIAUCSL"  # CPI All Urban Consumers, SA
    UNRATE = "UNRATE"  # Unemployment rate, monthly
    DGS10 = "DGS10"  # 10-Year Treasury constant maturity, daily
    DGS2 = "DGS2"  # 2-Year Treasury constant maturity, daily
    GDP_GROWTH = "A191RL1Q225SBEA"  # Real GDP growth, % change SAAR, quarterly
    SP500 = "SP500"  # S&P 500 index, daily


# ── Cache (successful responses only) ─────────────────────────────────────────
_LOCAL_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 3600


def _warn(message: str) -> None:
    warnings.warn(message, UserWarning, stacklevel=2)
    log.warning(message)


def _cache_get(key: str) -> Optional[Any]:
    full = f"_fred_{key}"
    try:
        import streamlit as st

        entry = st.session_state.get(full)
    except Exception:
        entry = _LOCAL_CACHE.get(full)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data: Any) -> None:
    full = f"_fred_{key}"
    entry = {"data": data, "ts": time.time()}
    try:
        import streamlit as st

        st.session_state[full] = entry
    except Exception:
        _LOCAL_CACHE[full] = entry


def _empty_series_df() -> pd.DataFrame:
    """Single-column 'value' time series with a DatetimeIndex named ``date``."""
    return pd.DataFrame(
        {"value": pd.Series(dtype="float64")},
        index=pd.DatetimeIndex([], name="date"),
    )


def _series_to_df(s: pd.Series, col: str = "value") -> pd.DataFrame:
    """Convert a FRED pandas Series to a clean DataFrame."""
    if s is None or len(s) == 0:
        return _empty_series_df()
    df = s.dropna().to_frame(name=col)
    df.index = pd.to_datetime(df.index, errors="coerce")
    df.index.name = "date"
    df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_index()


def empty_macro_dashboard() -> Dict[str, Any]:
    """
    Return the same structure as ``get_macro_dashboard`` but with empty frames.

    Used by callers that explicitly need an empty bundle (e.g. tests).
    """
    e = _empty_series_df()
    return {
        "fed_funds": e.copy(),
        "cpiaucsl": e.copy(),
        "cpi_yoy": e.copy(),
        "unemployment": e.copy(),
        "t10yr": e.copy(),
        "t2yr": e.copy(),
        "yield_spread": e.copy(),
        "gdp_growth": e.copy(),
        "sp500": e.copy(),
        "_is_fallback": True,
    }


def sample_macro_dashboard(lookback_years: int = 2) -> Dict[str, Any]:
    """
    Deterministic synthetic macro bundle for offline demos (not real FRED data).

    Same keys as ``get_macro_dashboard`` plus ``_is_fallback`` = True.
    """
    lookback_years = max(1, int(lookback_years))
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=lookback_years)
    idx = pd.date_range(start=start, end=end, freq="B")
    n = len(idx)
    if n == 0:
        return empty_macro_dashboard()

    t = np.linspace(0, 4 * np.pi, n)
    rng = np.random.default_rng(42)

    fed = np.clip(3.0 + 1.5 * np.sin(t) + rng.normal(0, 0.06, n), 0.05, None)
    unrate = np.clip(4.0 + 0.8 * np.sin(t + 1.0) + rng.normal(0, 0.04, n), 2.0, 15.0)
    t10 = np.clip(3.5 + 0.6 * np.sin(t * 0.8) + rng.normal(0, 0.05, n), 0.5, None)
    t2 = np.clip(3.0 + 0.7 * np.sin(t * 0.9 + 0.5) + rng.normal(0, 0.05, n), 0.25, None)
    spread = t10 - t2
    cpi_lvl = 300.0 + np.cumsum(np.clip(rng.normal(0.02, 0.04, n), -0.2, 0.2))
    cpi_series = pd.Series(cpi_lvl, index=idx)
    cpi_yoy_vals = (cpi_series.pct_change(252).fillna(0.0) * 100.0).to_numpy(dtype=float)
    gdp = np.clip(1.5 + 0.8 * np.sin(t * 0.3) + rng.normal(0, 0.12, n), -2.0, 8.0)
    sp = 4500.0 * np.exp(np.cumsum(rng.normal(0.00025, 0.0075, n)))

    def _col(arr: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame({"value": arr.astype(float)}, index=idx.copy()).rename_axis("date")

    spread_df = pd.DataFrame({"value": spread.astype(float)}, index=idx.copy()).rename_axis("date")
    return {
        "fed_funds": _col(fed),
        "cpiaucsl": _col(cpi_lvl.astype(float)),
        "cpi_yoy": _col(cpi_yoy_vals),
        "unemployment": _col(unrate),
        "t10yr": _col(t10),
        "t2yr": _col(t2),
        "yield_spread": spread_df,
        "gdp_growth": _col(gdp),
        "sp500": _col(sp.astype(float)),
        "_is_fallback": True,
    }


def _sample_series_for_id(
    series_id: str,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
) -> pd.DataFrame:
    """Synthetic single-series frame for unknown or failed ``get_series`` pulls."""
    end_d = pd.Timestamp(end) if end is not None else pd.Timestamp.today().normalize()
    start_d = pd.Timestamp(start) if start is not None else end_d - pd.DateOffset(years=2)
    idx = pd.date_range(start=start_d, end=end_d, freq="B")
    n = len(idx)
    if n == 0:
        return _empty_series_df()

    seed = abs(hash(series_id)) % (2**31)
    rng = np.random.default_rng(seed)
    defaults: dict[str, float] = {
        _S.DFF: 4.5,
        _S.CPIAUCSL: 310.0,
        _S.UNRATE: 4.2,
        _S.DGS10: 4.0,
        _S.DGS2: 3.8,
        _S.GDP_GROWTH: 2.0,
        _S.SP500: 4800.0,
    }
    base = float(defaults.get(series_id, 100.0))
    if series_id in (_S.CPIAUCSL, _S.SP500):
        vals = base * np.exp(np.cumsum(rng.normal(0.0001, 0.007, n)))
    else:
        vals = base + np.cumsum(rng.normal(0.0, 0.04, n))
    if series_id == _S.UNRATE:
        vals = np.clip(vals, 2.0, 20.0)
    else:
        vals = np.clip(vals, 0.01, None)
    return pd.DataFrame({"value": vals.astype(float)}, index=idx).rename_axis("date")


class FREDClient:
    """Fetch economic series from FRED; failures yield sample series + warnings."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key: str = api_key or os.getenv("FRED_API_KEY", "")
        self._fred: Optional[Any] = None

        if not _FREDAPI_AVAILABLE:
            _warn("fredapi is not installed — FRED requests will use synthetic sample series.")
            return
        if not self.api_key:
            _warn("FRED_API_KEY is not set — FRED requests will use synthetic sample series.")
            return
        try:
            self._fred = Fred(api_key=self.api_key)
        except Exception as exc:
            _warn(f"FRED client initialisation failed: {exc}")
            self._fred = None

    def get_series(
        self,
        series_id: str,
        start: Optional[Union[str, pd.Timestamp]] = None,
        end: Optional[Union[str, pd.Timestamp]] = None,
    ) -> pd.DataFrame:
        """
        Pull any FRED series into a DataFrame indexed by ``date`` with column ``value``.

        Returns a synthetic sample DataFrame if the client is unavailable or the
        request fails (never raises for transport/API issues).
        """
        cache_key = f"series_{series_id}_{start}_{end}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        if self._fred is None:
            _warn(f"Cannot fetch FRED series {series_id!r}: client not initialised — using sample data.")
            out = _sample_series_for_id(series_id, start, end)
            _cache_set(cache_key, out)
            return out

        obs_start = None if start is None else str(pd.Timestamp(start))[:10]
        obs_end = None if end is None else str(pd.Timestamp(end))[:10]

        try:
            raw = self._fred.get_series(
                series_id,
                observation_start=obs_start,
                observation_end=obs_end,
            )
            df = _series_to_df(raw)
            _cache_set(cache_key, df)
            return df
        except Exception as exc:
            _warn(f"FRED request failed for series {series_id!r}: {exc} — using sample data.")
            out = _sample_series_for_id(series_id, start, end)
            _cache_set(cache_key, out)
            return out

    def get_macro_dashboard(self, lookback_years: int = 2) -> Dict[str, Any]:
        """
        Return a dict of DataFrames for core macro series.

        Keys
        ----
        fed_funds, cpiaucsl, cpi_yoy, unemployment, t10yr, t2yr,
        yield_spread, gdp_growth, sp500, and ``_is_fallback`` (bool).

        ``cpiaucsl`` is the CPI level series; ``cpi_yoy`` is year-over-year %,
        computed from CPI when possible. ``yield_spread`` is DGS10 minus DGS2
        on overlapping dates.

        On total failure (no live rows), returns ``sample_macro_dashboard`` and
        ``_is_fallback`` is True.
        """
        cache_key = f"macro_dashboard_{lookback_years}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        if self._fred is None:
            out = sample_macro_dashboard(lookback_years=lookback_years)
            _warn("FRED macro dashboard: using synthetic sample data (client not initialised).")
            _cache_set(cache_key, out)
            return out

        start = str(pd.Timestamp.today() - pd.DateOffset(years=lookback_years))[:10]
        start_cpi = str(pd.Timestamp.today() - pd.DateOffset(years=lookback_years + 1))[:10]

        def pull(sid: str, observation_start: str) -> pd.Series:
            try:
                return self._fred.get_series(sid, observation_start=observation_start)
            except Exception as exc:
                _warn(f"FRED dashboard: failed to fetch {sid!r}: {exc}")
                return pd.Series(dtype=float)

        raw_ff = pull(_S.DFF, start)
        raw_cpi = pull(_S.CPIAUCSL, start)
        raw_unem = pull(_S.UNRATE, start)
        raw_t10 = pull(_S.DGS10, start)
        raw_t2 = pull(_S.DGS2, start)
        raw_gdp = pull(_S.GDP_GROWTH, start)
        raw_sp = pull(_S.SP500, start)

        cpiaucsl_df = _series_to_df(raw_cpi)

        cpi_yoy_df = _empty_series_df()
        try:
            raw_cpi_full = self._fred.get_series(_S.CPIAUCSL, observation_start=start_cpi)
            if len(raw_cpi_full):
                cpi_yoy_series = raw_cpi_full.pct_change(12) * 100.0
                cpi_yoy_series = cpi_yoy_series[cpi_yoy_series.index >= pd.Timestamp(start)]
                cpi_yoy_df = _series_to_df(cpi_yoy_series)
            elif len(raw_cpi):
                cpi_yoy_series = raw_cpi.pct_change(12) * 100.0
                cpi_yoy_df = _series_to_df(cpi_yoy_series)
        except Exception as exc:
            _warn(f"FRED dashboard: could not compute CPI YoY: {exc}")

        t10_clean = _series_to_df(raw_t10)["value"]
        t2_clean = _series_to_df(raw_t2)["value"]
        spread_series = (t10_clean - t2_clean).dropna()
        spread_df = (
            spread_series.to_frame(name="value").rename_axis("date")
            if len(spread_series)
            else _empty_series_df()
        )

        result: Dict[str, Any] = {
            "fed_funds": _series_to_df(raw_ff),
            "cpiaucsl": cpiaucsl_df,
            "cpi_yoy": cpi_yoy_df,
            "unemployment": _series_to_df(raw_unem),
            "t10yr": _series_to_df(raw_t10),
            "t2yr": _series_to_df(raw_t2),
            "yield_spread": spread_df,
            "gdp_growth": _series_to_df(raw_gdp),
            "sp500": _series_to_df(raw_sp),
        }

        any_data = any(
            isinstance(result[k], pd.DataFrame) and not result[k].empty
            for k in (
                "fed_funds",
                "cpiaucsl",
                "unemployment",
                "t10yr",
                "t2yr",
                "gdp_growth",
                "sp500",
            )
        )
        result["_is_fallback"] = not any_data

        if not any_data:
            _warn(
                "FRED macro dashboard: no live series returned data — using synthetic sample bundle."
            )
            result = sample_macro_dashboard(lookback_years=lookback_years)

        _cache_set(cache_key, result)
        return result

    def get_latest_values(self) -> Dict[str, Optional[float]]:
        """Return the most recent scalar for each dashboard series (skips metadata keys)."""
        dashboard = self.get_macro_dashboard()
        out: Dict[str, Optional[float]] = {}
        for key, df in dashboard.items():
            if key.startswith("_") or not isinstance(df, pd.DataFrame):
                continue
            if df.empty:
                out[key] = None
                continue
            col = df.columns[0]
            clean = df[col].dropna()
            out[key] = float(clean.iloc[-1]) if len(clean) else None
        return out


class FREDClientError(RuntimeError):
    """Raised when callers opt into strict FRED handling (optional)."""

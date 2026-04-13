"""
treasury_client.py
------------------
US Treasury Fiscal Data API REST client (no API key required).

See: https://fiscaldata.treasury.gov/api-documentation/

On failure, methods return synthetic sample DataFrames and emit warnings.
"""
from __future__ import annotations

import logging
import time
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
AVG_RATES_ENDPOINT = "/v1/accounting/od/avg_interest_rates"

_MATURITY_MAP = {
    "Treasury Bills": "Treasury Bills",
    "Treasury Notes": "Treasury Notes",
    "Treasury Bonds": "Treasury Bonds",
    "Treasury Inflation-Protected": "Treasury Inflation-Protected",
    "Federal Financing Bank": "Federal Financing Bank",
}

_LOCAL_CACHE: dict = {}
_CACHE_TTL = 3600


def _warn(message: str) -> None:
    warnings.warn(message, UserWarning, stacklevel=2)
    log.warning(message)


def _cache_get(key: str):
    full = f"_tsy_{key}"
    try:
        import streamlit as st

        entry = st.session_state.get(full)
    except Exception:
        entry = _LOCAL_CACHE.get(full)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data) -> None:
    full = f"_tsy_{key}"
    entry = {"data": data, "ts": time.time()}
    try:
        import streamlit as st

        st.session_state[full] = entry
    except Exception:
        _LOCAL_CACHE[full] = entry


def _empty_rates_df() -> pd.DataFrame:
    """Empty tidy rates: index ``date``, columns ``maturity``, ``rate_pct``."""
    return pd.DataFrame(
        {
            "maturity": pd.Series(dtype="object"),
            "rate_pct": pd.Series(dtype="float64"),
        },
        index=pd.DatetimeIndex([], name="date"),
    )


def _sample_treasury_rates(lookback_months: int) -> pd.DataFrame:
    """Synthetic average-interest-rate panel for demo charts."""
    lookback_months = max(1, int(lookback_months))
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(months=lookback_months)
    idx = pd.date_range(start=start, end=end, freq="MS")
    mats = ["Treasury Bills", "Treasury Notes", "Treasury Bonds"]
    rows: list[dict] = []
    for d in idx:
        for j, m in enumerate(mats):
            rows.append(
                {
                    "date": d,
                    "maturity": m,
                    "rate_pct": float(1.8 + j * 0.35 + 0.15 * np.sin(d.month)),
                }
            )
    df = pd.DataFrame(rows)
    return df.set_index("date")[["maturity", "rate_pct"]]


def _get(endpoint: str, params: Optional[dict] = None, timeout: int = 30) -> dict:
    url = BASE_URL + endpoint
    resp = requests.get(url, params=params or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _classify_maturity(desc: str) -> Optional[str]:
    """Map a raw ``security_desc`` string to a clean maturity label."""
    if not isinstance(desc, str):
        return None
    d = desc.strip()
    for label, substring in _MATURITY_MAP.items():
        if substring.lower() in d.lower():
            return label
    return None


def _fetch_avg_rates(limit: int = 500) -> pd.DataFrame:
    """
    Pull the most recent ``limit`` records from ``avg_interest_rates``.

    Returns columns ``date``, ``security_desc``, ``rate_pct`` (wide raw rows).
    """
    params = {
        "sort": "-record_date",
        "page[size]": min(limit, 10000),
        "fields": "record_date,security_desc,avg_interest_rate_amt",
    }
    data = _get(AVG_RATES_ENDPOINT, params)
    records = data.get("data", [])
    if not records:
        raise TreasuryClientError("Treasury API returned no records.")

    df = pd.DataFrame(records)
    df = df.rename(
        columns={
            "record_date": "date",
            "avg_interest_rate_amt": "rate_pct",
        }
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["rate_pct"] = pd.to_numeric(df["rate_pct"], errors="coerce")
    df = df.dropna(subset=["date", "rate_pct"]).sort_values("date")
    return df


class TreasuryClient:
    """Fetch US Treasury average interest rates as tidy DataFrames."""

    def get_treasury_rates(self, lookback_months: int = 24) -> pd.DataFrame:
        """
        Return average interest rates on Treasury debt.

        Index: ``date``. Columns: ``maturity`` (label), ``rate_pct`` (float).

        Synthetic sample on failure (after warning).
        """
        cache_key = f"rates_{lookback_months}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            df = _fetch_avg_rates(limit=lookback_months * 20)
            cutoff = pd.Timestamp.today() - pd.DateOffset(months=lookback_months)
            df = df[df["date"] >= cutoff].copy()
            df["maturity"] = df["security_desc"].apply(_classify_maturity)
            df = df[df["maturity"].notna()]
            out = df[["date", "maturity", "rate_pct"]].set_index("date")
            out.attrs["is_fallback"] = False
            if out.empty:
                raise TreasuryClientError("Treasury API returned no usable rows after filtering.")
        except Exception as exc:
            _warn(f"Treasury rates fetch failed: {exc} — using synthetic sample data.")
            out = _sample_treasury_rates(lookback_months)
            out.attrs["is_fallback"] = True

        _cache_set(cache_key, out)
        return out

    def get_rates_pivot(self, lookback_months: int = 24) -> pd.DataFrame:
        """
        Wide DataFrame: each column is a ``maturity`` label, index is ``date``.

        Synthetic sample on failure.
        """
        cache_key = f"pivot_{lookback_months}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            tidy = self.get_treasury_rates(lookback_months=lookback_months)
            if tidy.empty:
                tidy = _sample_treasury_rates(lookback_months)
                tidy.attrs["is_fallback"] = True
            t2 = tidy.reset_index()
            pivot = t2.pivot_table(
                index="date",
                columns="maturity",
                values="rate_pct",
                aggfunc="mean",
            )
            pivot.columns.name = None
            pivot.attrs["is_fallback"] = bool(tidy.attrs.get("is_fallback", False))
        except Exception as exc:
            _warn(f"Treasury pivot failed: {exc} — using synthetic sample data.")
            tidy = _sample_treasury_rates(lookback_months)
            t2 = tidy.reset_index()
            pivot = t2.pivot_table(
                index="date",
                columns="maturity",
                values="rate_pct",
                aggfunc="mean",
            )
            pivot.columns.name = None
            pivot.attrs["is_fallback"] = True

        _cache_set(cache_key, pivot)
        return pivot

    def get_latest_rates(self) -> dict:
        """
        Return ``{maturity_label: latest_rate_pct}`` from the most recent dates.

        Empty dict if no data.
        """
        cache_key = "latest"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        pivot = self.get_rates_pivot(lookback_months=3)
        out: dict = {}
        if pivot.empty:
            _cache_set(cache_key, out)
            return out
        for col in pivot.columns:
            s = pivot[col].dropna()
            if len(s):
                out[col] = round(float(s.iloc[-1]), 3)
        _cache_set(cache_key, out)
        return out


class TreasuryClientError(RuntimeError):
    """Internal error before mapping to empty return / warning."""

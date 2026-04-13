"""
risk_metrics.py
---------------
Value at Risk, Conditional VaR, and Monte Carlo confidence bands.

Public API (spec-aligned)
--------------------------
value_at_risk(returns, confidence, horizon_days)      -> float
conditional_var(returns, confidence, horizon_days)    -> float
confidence_bands(current_value, expected_return,
                 volatility, days, simulations)        -> dict

Legacy functions kept for existing callers
-------------------------------------------
historical_var(returns, confidence)       -> float   (single-day, no scaling)
parametric_var(returns, confidence)       -> float
historical_cvar(returns, confidence)      -> float
parametric_cvar(returns, confidence)      -> float
compute_all_risk_metrics(returns, conf)   -> dict
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ─────────────────────────────────────────────────────────────────────────────
# Public API — spec-aligned
# ─────────────────────────────────────────────────────────────────────────────

def value_at_risk(
    returns: pd.Series | np.ndarray,
    confidence: float = 0.95,
    horizon_days: int = 30,
) -> float:
    """
    Historical (non-parametric) Value at Risk, scaled to a multi-day horizon.

    Computes the daily VaR from the empirical return distribution, then scales
    to the requested horizon using the square-root-of-time rule, which is the
    standard Basel / practitioner approximation for i.i.d. returns.

    Parameters
    ----------
    returns      : daily return Series or array (fractional, e.g. -0.02 = -2%).
    confidence   : confidence level, e.g. 0.95 for 95% VaR.
    horizon_days : holding period in days (1 = daily VaR, 30 ≈ monthly).

    Returns
    -------
    float — positive number representing the loss at the confidence level.
    E.g. 0.08 means "lose no more than 8% with 95% confidence over horizon_days."
    """
    arr = np.asarray(returns, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return 0.0
    daily_var = float(-np.percentile(arr, (1.0 - confidence) * 100.0))
    return daily_var * np.sqrt(horizon_days)


def conditional_var(
    returns: pd.Series | np.ndarray,
    confidence: float = 0.95,
    horizon_days: int = 30,
) -> float:
    """
    Historical Conditional VaR (Expected Shortfall), scaled to a multi-day horizon.

    CVaR is the mean loss in the worst (1 - confidence) fraction of outcomes —
    i.e. the average of the tail beyond the VaR threshold.  More conservative
    and theoretically coherent than VaR alone.

    Parameters
    ----------
    returns      : daily return Series or array.
    confidence   : confidence level, e.g. 0.95.
    horizon_days : holding period in days for square-root scaling.

    Returns
    -------
    float — positive number; always >= value_at_risk() at the same confidence.
    """
    arr = np.asarray(returns, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return 0.0

    # Threshold: the return value at the VaR percentile
    cutoff = np.percentile(arr, (1.0 - confidence) * 100.0)   # negative number
    tail = arr[arr <= cutoff]

    if len(tail) == 0:
        # Fallback to VaR if no tail observations
        return value_at_risk(returns, confidence, horizon_days)

    daily_cvar = float(-tail.mean())
    return daily_cvar * np.sqrt(horizon_days)


def confidence_bands(
    current_value: float,
    expected_return: float,
    volatility: float,
    days: int,
    simulations: int = 10_000,
    seed: int = 42,
) -> dict:
    """
    Monte Carlo confidence bands for a price/value projection.

    Runs Geometric Brownian Motion and returns the 5th, 25th, 50th, 75th, and
    95th percentile paths at each future day — ready to be plotted as a fan chart.

    Parameters
    ----------
    current_value   : starting value (e.g. portfolio $ value or stock price).
    expected_return : annualised expected return as a decimal (e.g. 0.08 = 8%).
    volatility      : annualised volatility as a decimal (e.g. 0.18 = 18%).
    days            : number of forward trading days to project.
    simulations     : number of Monte Carlo paths (default 10 000).
    seed            : random seed for reproducibility.

    Returns
    -------
    dict with keys:
        "days"   : list[int]          — [1, 2, ..., days]
        "p5"     : list[float]        — 5th-percentile path
        "p25"    : list[float]        — 25th-percentile path
        "p50"    : list[float]        — median path
        "p75"    : list[float]        — 75th-percentile path
        "p95"    : list[float]        — 95th-percentile path
        "current_value" : float
        "final_p5", "final_p50", "final_p95" : float — endpoint values
    """
    rng = np.random.default_rng(seed)
    dt  = 1.0 / 252.0

    # GBM increments: each column is one path, each row is one day
    # Shape: (days, simulations)
    Z          = rng.standard_normal((days, simulations))
    log_shocks = (expected_return - 0.5 * volatility ** 2) * dt + volatility * np.sqrt(dt) * Z
    log_paths  = np.cumsum(log_shocks, axis=0)
    paths      = current_value * np.exp(log_paths)   # (days, simulations)

    pct_labels = [5, 25, 50, 75, 95]
    # np.percentile across simulations (axis=1) at each day → shape (days,)
    pct_paths  = {f"p{p}": np.percentile(paths, p, axis=1).tolist() for p in pct_labels}

    final = paths[-1]  # (simulations,)
    return {
        "days":          list(range(1, days + 1)),
        "current_value": current_value,
        **pct_paths,
        "final_p5":      float(np.percentile(final, 5)),
        "final_p25":     float(np.percentile(final, 25)),
        "final_p50":     float(np.percentile(final, 50)),
        "final_p75":     float(np.percentile(final, 75)),
        "final_p95":     float(np.percentile(final, 95)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Legacy helpers (kept for backwards compatibility)
# ─────────────────────────────────────────────────────────────────────────────

def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """
    Daily historical VaR (no horizon scaling).  Legacy alias for value_at_risk
    with horizon_days=1.
    """
    return value_at_risk(returns, confidence, horizon_days=1)


def parametric_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Parametric (Gaussian) daily VaR."""
    mu    = float(returns.mean())
    sigma = float(returns.std())
    return float(-(mu + sigma * stats.norm.ppf(1.0 - confidence)))


def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Daily historical CVaR (no horizon scaling)."""
    return conditional_var(returns, confidence, horizon_days=1)


def parametric_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Parametric (Gaussian) daily CVaR."""
    mu    = float(returns.mean())
    sigma = float(returns.std())
    z     = stats.norm.ppf(1.0 - confidence)
    return float(-(mu - sigma * stats.norm.pdf(z) / (1.0 - confidence)))


def compute_all_risk_metrics(
    returns: pd.Series,
    confidence: float = 0.95,
) -> dict:
    """Return a summary dict of all risk metrics.  Kept for backwards compatibility."""
    return {
        "historical_var":    historical_var(returns, confidence),
        "parametric_var":    parametric_var(returns, confidence),
        "historical_cvar":   historical_cvar(returns, confidence),
        "parametric_cvar":   parametric_cvar(returns, confidence),
        "var_30d":           value_at_risk(returns, confidence, 30),
        "cvar_30d":          conditional_var(returns, confidence, 30),
        "confidence_level":  confidence,
        "skewness":          float(returns.skew()),
        "kurtosis":          float(returns.kurtosis()),
    }

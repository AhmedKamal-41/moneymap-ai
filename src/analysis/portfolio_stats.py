"""
portfolio_stats.py
------------------
Single-asset and multi-asset portfolio statistics.

Public API (spec-aligned)
--------------------------
compute_returns(prices_df)                                       -> DataFrame
expected_annual_return(returns)                                  -> float | Series
annual_volatility(returns)                                       -> float | Series
sharpe_ratio(returns, risk_free_rate)                            -> float
beta(asset_returns, market_returns)                              -> float
max_drawdown(prices)                                             -> float
drawdown_series(prices)                                          -> Series
correlation_matrix(returns_df)                                   -> DataFrame
portfolio_return(weights, expected_returns)                      -> float
portfolio_volatility(weights, cov_matrix)                        -> float
portfolio_sharpe(weights, expected_returns, cov_matrix, rfr)     -> float

Legacy helpers kept for existing callers
-----------------------------------------
compute_all(returns, benchmark_returns, risk_free_rate)          -> dict

Implementation note
--------------------
Numerics are NumPy-based; pandas ``Series`` / ``DataFrame`` are used as
containers for alignment with the rest of the app (not a scipy dependency
in this module).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ── Returns ───────────────────────────────────────────────────────────────────

def compute_returns(prices_df: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """
    Compute daily percentage returns from a price series or DataFrame.

    Drops the first row (NaN from pct_change).

    Parameters
    ----------
    prices_df : pd.DataFrame of shape (days, assets) or a single pd.Series.

    Returns
    -------
    DataFrame (or Series) of the same shape minus the first row.
    """
    return prices_df.pct_change().dropna()


# ── Single-asset stats ────────────────────────────────────────────────────────

def expected_annual_return(returns: pd.Series | pd.DataFrame) -> float | pd.Series:
    """
    Annualised expected return using the arithmetic mean scaled by 252.

    Works on a Series (single asset) or DataFrame (returns one value per column).
    """
    return returns.mean() * TRADING_DAYS


def annual_volatility(returns: pd.Series | pd.DataFrame) -> float | pd.Series:
    """
    Annualised volatility (standard deviation scaled by √252).

    Works on a Series or DataFrame.
    """
    return returns.std() * np.sqrt(TRADING_DAYS)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.05) -> float:
    """
    Annualised Sharpe ratio.

    Parameters
    ----------
    returns        : daily return Series.
    risk_free_rate : annualised risk-free rate (e.g. current 3-month T-bill).
                     Fetch live via TreasuryClient.get_latest_rates()["3-Month"].

    Returns
    -------
    float — excess return per unit of annualised volatility.
    """
    er  = float(expected_annual_return(returns))
    vol = float(annual_volatility(returns))
    if vol < 1e-12:
        return 0.0
    return (er - risk_free_rate) / vol


def beta(asset_returns: pd.Series, market_returns: pd.Series) -> float:
    """
    Beta of an asset relative to a market benchmark (e.g. S&P 500).

    Uses the OLS formula: β = Cov(asset, market) / Var(market).
    Aligns both series on their common index before computing.

    Parameters
    ----------
    asset_returns  : daily return Series for the asset.
    market_returns : daily return Series for the market (e.g. SPY).
    """
    # Align on common dates
    combined = pd.concat([asset_returns, market_returns], axis=1).dropna()
    if len(combined) < 2:
        return 1.0
    a = combined.iloc[:, 0].values
    m = combined.iloc[:, 1].values
    cov_matrix = np.cov(a, m, ddof=1)
    market_var = cov_matrix[1, 1]
    if market_var < 1e-12:
        return 1.0
    return float(cov_matrix[0, 1] / market_var)


# ── Drawdown ──────────────────────────────────────────────────────────────────

def max_drawdown(prices: pd.Series) -> float:
    """
    Worst peak-to-trough decline observed in a price series.

    Parameters
    ----------
    prices : pd.Series of price levels (not returns).

    Returns
    -------
    float — negative fraction, e.g. -0.35 means a 35% drawdown.
    """
    rolling_max = prices.cummax()
    dd = prices / rolling_max - 1.0
    return float(dd.min())


def drawdown_series(prices: pd.Series) -> pd.Series:
    """
    Running drawdown from the most recent peak, at each point in time.

    Parameters
    ----------
    prices : pd.Series of price levels (not returns).

    Returns
    -------
    pd.Series of the same index, values in [-1, 0].
    Suitable for plotting as a shaded area chart.
    """
    rolling_max = prices.cummax()
    return prices / rolling_max - 1.0


# ── Multi-asset ───────────────────────────────────────────────────────────────

def correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pearson correlation matrix of asset returns.

    Parameters
    ----------
    returns_df : pd.DataFrame with one column per asset.

    Returns
    -------
    pd.DataFrame of shape (n_assets, n_assets), values in [-1, 1].
    """
    return returns_df.corr()


def portfolio_return(weights: np.ndarray, expected_returns: np.ndarray | pd.Series) -> float:
    """
    Expected portfolio return given asset weights and per-asset expected returns.

    Parameters
    ----------
    weights          : 1-D array summing to 1.0.
    expected_returns : 1-D array of per-asset annualised expected returns.
    """
    w = np.asarray(weights, dtype=float)
    er = np.asarray(expected_returns, dtype=float)
    return float(w @ er)


def portfolio_volatility(weights: np.ndarray, cov_matrix: np.ndarray | pd.DataFrame) -> float:
    """
    Portfolio volatility (annualised standard deviation).

    Parameters
    ----------
    weights    : 1-D array summing to 1.0.
    cov_matrix : annualised covariance matrix (n_assets × n_assets).
    """
    w  = np.asarray(weights, dtype=float)
    cov = np.asarray(cov_matrix, dtype=float)
    variance = w @ cov @ w
    return float(np.sqrt(max(variance, 0.0)))


def portfolio_sharpe(
    weights: np.ndarray,
    expected_returns: np.ndarray | pd.Series,
    cov_matrix: np.ndarray | pd.DataFrame,
    risk_free_rate: float,
) -> float:
    """
    Annualised Sharpe ratio for a portfolio.

    Parameters
    ----------
    weights          : 1-D weight array summing to 1.0.
    expected_returns : 1-D annualised expected return array.
    cov_matrix       : annualised covariance matrix.
    risk_free_rate   : annualised risk-free rate.
    """
    pr  = portfolio_return(weights, expected_returns)
    pv  = portfolio_volatility(weights, cov_matrix)
    if pv < 1e-12:
        return 0.0
    return (pr - risk_free_rate) / pv


# ── Legacy convenience wrapper ────────────────────────────────────────────────

def compute_all(
    returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
    risk_free_rate: float = 0.05,
) -> dict:
    """
    Return all single-asset stats in one dict.

    Kept for backwards compatibility with existing callers.
    `returns` is a daily return Series; `benchmark_returns` is optional market series.
    """
    # Reconstruct a synthetic price series (starting at 100) for drawdown functions
    prices = (1.0 + returns).cumprod() * 100.0
    prices.iloc[0] = 100.0 * (1.0 + returns.iloc[0])  # no off-by-one

    result: dict = {
        "expected_return_ann": float(expected_annual_return(returns)),
        "volatility_ann":      float(annual_volatility(returns)),
        "sharpe":              sharpe_ratio(returns, risk_free_rate),
        "max_drawdown":        max_drawdown(prices),
    }
    if benchmark_returns is not None:
        result["beta"] = beta(returns, benchmark_returns)
    return result

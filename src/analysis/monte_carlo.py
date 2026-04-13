"""
monte_carlo.py
--------------
Monte Carlo simulation for portfolio values and personal/business cash flows.

Public API (spec-aligned)
--------------------------
simulate_portfolio(current_value, expected_return, volatility,
                   days, simulations)                         -> np.ndarray (simulations, days)
simulate_cash_flow(monthly_income, monthly_expenses, months,
                   income_growth, expense_growth,
                   volatility, simulations)                   -> np.ndarray (simulations, months)
summarize_simulations(simulations_array, percentiles)         -> dict

Legacy helpers kept for existing callers
-------------------------------------------
build_fan_chart(paths, title, x_label, y_label)              -> go.Figure
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go


# ─────────────────────────────────────────────────────────────────────────────
# Public API — spec-aligned
# ─────────────────────────────────────────────────────────────────────────────

def simulate_portfolio(
    current_value: float,
    expected_return: float,
    volatility: float,
    days: int = 365,
    simulations: int = 10_000,
    seed: int = 42,
) -> np.ndarray:
    """
    Simulate future portfolio values using Geometric Brownian Motion.

    Each time-step is one trading day.  The drift and diffusion terms follow
    the standard GBM discretisation:

        S(t+dt) = S(t) * exp((μ - σ²/2)*dt + σ*√dt*Z)

    where Z ~ N(0, 1) and dt = 1/252.

    Parameters
    ----------
    current_value   : starting portfolio value in dollars.
    expected_return : annualised expected return (e.g. 0.10 = 10%).
    volatility      : annualised volatility / standard deviation (e.g. 0.18 = 18%).
    days            : number of forward trading days to simulate.
    simulations     : number of independent Monte Carlo paths.
    seed            : random seed for reproducibility.

    Returns
    -------
    np.ndarray of shape (simulations, days).
    Row i is the full price path for simulation i.
    Column j is the cross-sectional distribution on day j+1.
    """
    rng = np.random.default_rng(seed)
    dt  = 1.0 / 252.0

    # Draw all random shocks at once: shape (simulations, days)
    Z          = rng.standard_normal((simulations, days))
    log_shocks = (expected_return - 0.5 * volatility ** 2) * dt + volatility * np.sqrt(dt) * Z

    # Cumulative sum along days axis gives log-price growth from t=0
    log_paths  = np.cumsum(log_shocks, axis=1)          # (simulations, days)
    return current_value * np.exp(log_paths)             # (simulations, days)


def simulate_cash_flow(
    monthly_income: float,
    monthly_expenses: float,
    months: int = 24,
    income_growth: float = 0.0,
    expense_growth: float = 0.0,
    volatility: float = 0.10,
    simulations: int = 5_000,
    seed: int = 42,
) -> np.ndarray:
    """
    Simulate cumulative cash balance paths given monthly income and expenses.

    At each month m (0-indexed from the first future month):

        net_m = income * (1 + income_growth)^m
              - expenses * (1 + expense_growth)^m
              + noise_m

    where noise_m ~ N(0, volatility * |net_0|) captures real-world variance
    around the deterministic budget (e.g. variable income, irregular expenses).

    Cumulative cash at month t = Σ net_m for m in [0, t).

    Parameters
    ----------
    monthly_income   : baseline monthly income in dollars.
    monthly_expenses : baseline monthly expenses in dollars.
    months           : number of months to project.
    income_growth    : monthly income growth rate (e.g. 0.005 = 0.5%/mo).
    expense_growth   : monthly expense growth rate (e.g. 0.003 = 0.3%/mo).
    volatility       : noise scale as a fraction of the base net income.
                       0.10 means ±10% standard deviation around net cash flow.
    simulations      : number of independent Monte Carlo paths.
    seed             : random seed for reproducibility.

    Returns
    -------
    np.ndarray of shape (simulations, months).
    Each row is one cumulative cash-balance path.
    Column j is the cumulative cash after j+1 months.
    """
    rng       = np.random.default_rng(seed)
    base_net  = monthly_income - monthly_expenses   # deterministic net at m=0
    noise_std = abs(base_net) * volatility           # scale noise to net income

    # Deterministic net income at each month: shape (months,)
    m_idx          = np.arange(months, dtype=float)
    income_path    = monthly_income  * (1.0 + income_growth)  ** m_idx
    expense_path   = monthly_expenses * (1.0 + expense_growth) ** m_idx
    det_net        = income_path - expense_path                # (months,)

    # Random noise: shape (simulations, months)
    noise      = rng.normal(0.0, noise_std, (simulations, months))

    # Monthly net cash flows per simulation
    monthly_net = det_net[np.newaxis, :] + noise               # (simulations, months)

    # Cumulative sum along months axis → running cash balance
    return np.cumsum(monthly_net, axis=1)                      # (simulations, months)


def summarize_simulations(
    simulations_array: np.ndarray,
    percentiles: List[int] = None,
) -> dict:
    """
    Summarise a matrix of Monte Carlo simulation paths.

    Parameters
    ----------
    simulations_array : np.ndarray of shape (n_simulations, n_steps).
                        Output of simulate_portfolio() or simulate_cash_flow().
    percentiles       : list of integer percentiles to compute (default [5,25,50,75,95]).

    Returns
    -------
    dict with keys:
        "percentile_paths"  : dict  — {p5: array(n_steps), p25: ..., ...}
                              Cross-sectional percentile at each time step.
        "final_values"      : np.ndarray(n_simulations,) — terminal values.
        "final_mean"        : float
        "final_median"      : float
        "final_std"         : float
        "final_p{p}"        : float — one key per requested percentile.
        "prob_loss"         : float — fraction of paths ending below the t=0 value
                              (estimated as below the first-step cross-section median).
        "n_simulations"     : int
        "n_steps"           : int
    """
    if percentiles is None:
        percentiles = [5, 25, 50, 75, 95]

    n_simulations, n_steps = simulations_array.shape
    final  = simulations_array[:, -1]

    # Cross-sectional percentile at each step → shape (n_steps,) per percentile
    pct_paths: Dict[str, np.ndarray] = {}
    for p in percentiles:
        pct_paths[f"p{p}"] = np.percentile(simulations_array, p, axis=0)

    # Approximate starting value from step 0 distribution median
    start_approx = float(np.median(simulations_array[:, 0]))
    prob_loss     = float(np.mean(final < start_approx))

    result: dict = {
        "percentile_paths": pct_paths,
        "final_values":     final,
        "final_mean":       float(np.mean(final)),
        "final_median":     float(np.median(final)),
        "final_std":        float(np.std(final)),
        "prob_loss":        prob_loss,
        "n_simulations":    n_simulations,
        "n_steps":          n_steps,
    }
    for p in percentiles:
        result[f"final_p{p}"] = float(np.percentile(final, p))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Legacy helper — kept for existing callers (e.g. build_fan_chart used in pages)
# ─────────────────────────────────────────────────────────────────────────────

def build_fan_chart(
    paths: np.ndarray,
    title: str = "Monte Carlo Simulation",
    x_label: str = "Step",
    y_label: str = "Value",
    color: str = "#1f6feb",
) -> go.Figure:
    """
    Build a Plotly fan-chart from a simulation paths matrix.

    Accepts either axis convention:
    - New API: shape (n_simulations, n_steps)  → percentiles across axis=0
    - Legacy:  shape (n_steps, n_simulations)  → percentiles across axis=1
    """
    # Normalise to (n_simulations, n_steps) for consistent axis handling
    if paths.shape[0] < paths.shape[1]:
        # Likely (n_steps, n_simulations) — transpose to standard form
        paths = paths.T

    n_steps = paths.shape[1]
    x = list(range(n_steps))

    def _pct(p: int) -> list:
        return np.percentile(paths, p, axis=0).tolist()

    p10, p25, p50, p75, p90 = _pct(10), _pct(25), _pct(50), _pct(75), _pct(90)

    def _rgba(hex_color: str, alpha: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    fig = go.Figure()

    # P10–P90 band
    fig.add_trace(go.Scatter(
        x=x + x[::-1],
        y=p90 + p10[::-1],
        fill="toself",
        fillcolor=_rgba(color, 0.12),
        line=dict(color="rgba(0,0,0,0)"),
        name="P10–P90",
        hoverinfo="skip",
    ))
    # P25–P75 band
    fig.add_trace(go.Scatter(
        x=x + x[::-1],
        y=p75 + p25[::-1],
        fill="toself",
        fillcolor=_rgba(color, 0.25),
        line=dict(color="rgba(0,0,0,0)"),
        name="P25–P75",
        hoverinfo="skip",
    ))
    # Median
    fig.add_trace(go.Scatter(
        x=x, y=p50,
        line=dict(color=color, width=2),
        name="Median (P50)",
    ))

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#161b22",
        font=dict(color="#e6edf3"),
        legend=dict(orientation="h", x=0, y=1.1, bgcolor="rgba(0,0,0,0)"),
    )
    return fig

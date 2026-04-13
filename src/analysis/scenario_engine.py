"""
scenario_engine.py
------------------
Build base / upside / downside Monte Carlo scenario projections and
one-at-a-time sensitivity analysis.

Public API (spec-aligned)
--------------------------
build_scenarios(base_params, mode)                              -> dict
sensitivity_analysis(base_params, variable_name,
                     range_values, mode)                        -> pd.DataFrame

Legacy compatibility
--------------------
The old DataFrame-based build_scenarios signature is replaced; existing code
that used it should migrate to the new dict-based API.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.analysis.monte_carlo import (
    simulate_cash_flow,
    simulate_portfolio,
    summarize_simulations,
)

log = logging.getLogger(__name__)

# ── Scenario definitions (spec-prescribed multipliers) ────────────────────────
#   income_mult   : factor applied to monthly_income / monthly_revenue
#   expense_mult  : factor applied to monthly_expenses
#   return_delta  : absolute addition to expected_return (portfolio only)

_SCENARIO_DEFS: Dict[str, Dict[str, float]] = {
    "base":     {"income_mult": 1.00, "expense_mult": 1.00, "return_delta":  0.00},
    "upside":   {"income_mult": 1.15, "expense_mult": 1.00, "return_delta":  0.03},
    "downside": {"income_mult": 0.80, "expense_mult": 1.10, "return_delta": -0.15},
}

# Scenario display metadata (used by the page layer)
SCENARIO_META: Dict[str, Dict[str, str]] = {
    "base":     {"label": "Base Case",  "color": "#1f6feb", "band": "rgba(31,111,235,0.13)"},
    "upside":   {"label": "Upside",     "color": "#3fb950", "band": "rgba(63,185,80,0.13)"},
    "downside": {"label": "Downside",   "color": "#f85149", "band": "rgba(248,81,73,0.13)"},
}

# Simulation constants
_SCENARIO_MONTHS:  int   = 12
_CF_SIMULATIONS:   int   = 5_000   # cash-flow scenario runs
_SA_SIMULATIONS:   int   = 2_000   # sensitivity analysis (speed trade-off)
_PORT_SIMULATIONS: int   = 5_000
_CF_VOLATILITY:    float = 0.12    # noise as fraction of base net cash flow
_PORT_VOLATILITY:  float = 0.15    # default portfolio annual volatility

# Variables routed to the portfolio simulation (rather than cash-flow sim)
_PORTFOLIO_VARS = frozenset({"expected_return", "volatility"})


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_cashflow(
    monthly_income: float,
    monthly_expenses: float,
    starting_cash: float,
    months: int = _SCENARIO_MONTHS,
    income_growth: float = 0.0,
    expense_growth: float = 0.0,
    simulations: int = _CF_SIMULATIONS,
    seed: int = 42,
) -> np.ndarray:
    """
    Run a cash-flow Monte Carlo and shift paths by `starting_cash`.

    Returns shape (simulations, months).  Values represent the actual cash
    balance at each month, starting from `starting_cash`.
    """
    paths = simulate_cash_flow(
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        months=months,
        income_growth=income_growth,
        expense_growth=expense_growth,
        volatility=_CF_VOLATILITY,
        simulations=simulations,
        seed=seed,
    )
    return paths + starting_cash          # broadcast scalar over (sims, months)


def _extract_scenario_result(paths: np.ndarray) -> Dict[str, Any]:
    """
    Compute all scenario output metrics from a (simulations, months) array.

    Returns a dict suitable for consumption by the page layer and for
    storage in session_state.
    """
    summary = summarize_simulations(paths, percentiles=[5, 25, 50, 75, 95])

    # Probability of cash going negative at any point during the horizon
    went_negative = np.any(paths < 0, axis=1)    # (simulations,) bool
    prob_negative = float(went_negative.mean())

    # Median first month of going negative (1-based), or None if never
    months_until_negative: Optional[float] = None
    if went_negative.any():
        neg_indices = np.argmax(paths[went_negative] < 0, axis=1)  # 0-based month
        months_until_negative = float(np.median(neg_indices) + 1)  # 1-based

    return {
        # Ending-cash distribution
        "median_outcome":         summary["final_median"],
        "p5_outcome":             summary["final_p5"],
        "p25_outcome":            summary["final_p25"],
        "p75_outcome":            summary["final_p75"],
        "p95_outcome":            summary["final_p95"],
        # Risk
        "probability_of_negative": prob_negative,
        "months_until_negative":   months_until_negative,
        # Full percentile paths for charting — shape {p5: array, ...}
        "percentile_paths":        summary["percentile_paths"],
        # n_months axis
        "months":                  list(range(1, paths.shape[1] + 1)),
    }


def _personal_cashflow_params(
    params: Dict[str, Any],
    income_mult: float,
    expense_mult: float,
) -> tuple[float, float, float]:
    """Return (income, expenses, starting_cash) for a personal scenario."""
    income = params["monthly_income"] * income_mult
    expenses = params["monthly_expenses"] * expense_mult

    # Add monthly debt interest cost on top of base expenses if debt fields provided
    debt_bal  = params.get("debt_balance", 0.0)
    debt_rate = params.get("debt_rate", 0.0)
    if debt_bal > 0 and debt_rate > 0:
        monthly_interest = debt_bal * debt_rate / 12.0
        expenses += monthly_interest

    starting_cash = params.get("savings", 0.0)
    return income, expenses, starting_cash


def _business_cashflow_params(
    params: Dict[str, Any],
    income_mult: float,
    expense_mult: float,
) -> tuple[float, float, float, float]:
    """Return (revenue, expenses, starting_cash, monthly_growth) for a business scenario."""
    revenue = params["monthly_revenue"] * income_mult
    expenses = params["monthly_expenses"] * expense_mult

    # marketing_budget is already included in monthly_expenses, but if the user
    # supplied it explicitly we leave expenses as-is (the budget is part of the total).
    starting_cash = params.get("cash_balance", 0.0)

    # growth_rate is annual; convert to monthly for simulate_cash_flow
    annual_growth = params.get("growth_rate", 0.0)
    monthly_growth = (1.0 + annual_growth) ** (1.0 / 12.0) - 1.0

    return revenue, expenses, starting_cash, monthly_growth


# ── Public: scenario builder ──────────────────────────────────────────────────

def build_scenarios(base_params: Dict[str, Any], mode: str = "personal") -> Dict[str, Any]:
    """
    Build base, upside, and downside Monte Carlo projections over 12 months.

    Scenario multipliers (hard-coded per spec):
        base     — as provided
        upside   — income/revenue +15%, expenses flat, portfolio return +3%
        downside — income/revenue -20%, expenses +10%, portfolio return -15%

    Parameters
    ----------
    base_params : dict
        Personal keys: monthly_income, monthly_expenses, savings, debt_balance,
                       debt_rate, portfolio_value, expected_return, volatility
        Business keys: monthly_revenue, monthly_expenses, cash_balance, debt_balance,
                       growth_rate, marketing_budget

    mode : "personal" | "business"

    Returns
    -------
    dict  — keys: "base", "upside", "downside", each containing:
        median_outcome          float   — median 12-month ending cash
        p5_outcome / p95_outcome float  — confidence interval endpoints
        probability_of_negative float   — fraction of paths that go negative
        months_until_negative   float | None
        percentile_paths        dict    — {p5, p25, p50, p75, p95} → array (12,)
        months                  list[int]
        params_used             dict    — the scenario params that were run
    """
    results: Dict[str, Any] = {}

    for scenario_name, mods in _SCENARIO_DEFS.items():
        im = mods["income_mult"]
        em = mods["expense_mult"]

        if mode == "personal":
            income, expenses, starting_cash = _personal_cashflow_params(
                base_params, im, em
            )
            paths = _run_cashflow(income, expenses, starting_cash)
            result = _extract_scenario_result(paths)
            result["params_used"] = {
                "monthly_income":  income,
                "monthly_expenses": expenses,
                "starting_cash":   starting_cash,
            }

            # Portfolio simulation (optional, when portfolio_value > 0)
            port_val = base_params.get("portfolio_value", 0.0)
            if port_val > 0.0:
                er  = max(base_params.get("expected_return", 0.08) + mods["return_delta"], -0.30)
                vol = base_params.get("volatility", _PORT_VOLATILITY)
                port_paths = simulate_portfolio(
                    current_value=port_val,
                    expected_return=er,
                    volatility=vol,
                    days=252,
                    simulations=_PORT_SIMULATIONS,
                )
                port_summary = summarize_simulations(port_paths)
                result["portfolio_median"]  = port_summary["final_median"]
                result["portfolio_p5"]      = port_summary["final_p5"]
                result["portfolio_p95"]     = port_summary["final_p95"]
                result["portfolio_paths"]   = port_summary["percentile_paths"]

        else:  # business
            revenue, expenses, starting_cash, monthly_growth = _business_cashflow_params(
                base_params, im, em
            )
            paths = _run_cashflow(
                monthly_income=revenue,
                monthly_expenses=expenses,
                starting_cash=starting_cash,
                income_growth=monthly_growth,
            )
            result = _extract_scenario_result(paths)
            result["params_used"] = {
                "monthly_revenue": revenue,
                "monthly_expenses": expenses,
                "starting_cash":   starting_cash,
                "monthly_growth":  monthly_growth,
            }

        results[scenario_name] = result

    return results


# ── Public: sensitivity analysis ──────────────────────────────────────────────

def sensitivity_analysis(
    base_params: Dict[str, Any],
    variable_name: str,
    range_values: List[float],
    mode: str = "personal",
) -> pd.DataFrame:
    """
    One-at-a-time sensitivity: vary `variable_name` across `range_values`,
    hold all other base_params fixed at their base values, run Monte Carlo,
    and record the distribution of the 12-month outcome.

    Parameters
    ----------
    base_params   : same structure as build_scenarios()
    variable_name : key to override in base_params (e.g. "monthly_income")
    range_values  : list of values to test
    mode          : "personal" | "business"

    Returns
    -------
    pd.DataFrame with columns:
        variable_value  — the tested value
        median_outcome  — median 12-month ending cash (or portfolio value)
        p_negative      — probability of going negative at any point
        p5_outcome      — 5th-percentile 12-month outcome
        p95_outcome     — 95th-percentile 12-month outcome
    """
    rows: List[Dict[str, float]] = []

    for val in range_values:
        p = {**base_params, variable_name: val}

        # ── Portfolio simulation (expected_return / volatility) ──────────────
        if variable_name in _PORTFOLIO_VARS and mode == "personal":
            port_val = p.get("portfolio_value", 0.0)
            if port_val <= 0.0:
                rows.append({
                    "variable_value": val,
                    "median_outcome": 0.0,
                    "p_negative":     0.0,
                    "p5_outcome":     0.0,
                    "p95_outcome":    0.0,
                })
                continue
            er  = max(p.get("expected_return", 0.08), -0.50)
            vol = max(p.get("volatility", _PORT_VOLATILITY), 1e-4)
            paths = simulate_portfolio(port_val, er, vol, days=252,
                                       simulations=_SA_SIMULATIONS)
            final = paths[:, -1]
            # No concept of "going negative" for a portfolio without leverage
            prob_neg = float(np.mean(final < port_val))    # prob of loss vs cost basis
            rows.append({
                "variable_value": val,
                "median_outcome": float(np.median(final)),
                "p_negative":     prob_neg,
                "p5_outcome":     float(np.percentile(final, 5)),
                "p95_outcome":    float(np.percentile(final, 95)),
            })
            continue

        # ── Cash-flow simulation (everything else) ────────────────────────────
        if mode == "personal":
            income, expenses, starting_cash = _personal_cashflow_params(
                p,
                income_mult=1.0,
                expense_mult=1.0,
            )
            # Special handling for debt_rate: delta cost vs base
            if variable_name == "debt_rate":
                debt_bal      = p.get("debt_balance", 0.0)
                base_rate     = base_params.get("debt_rate", 0.0)
                delta_monthly = debt_bal * (val - base_rate) / 12.0
                expenses     += delta_monthly
        else:
            revenue, expenses, starting_cash, monthly_growth = _business_cashflow_params(
                p, income_mult=1.0, expense_mult=1.0
            )
            income = revenue
            # marketing_budget sensitivity: override the delta in expenses
            if variable_name == "marketing_budget":
                old_mkt  = base_params.get("marketing_budget", 0.0)
                expenses = expenses - old_mkt + val

        paths = _run_cashflow(
            monthly_income=income,
            monthly_expenses=expenses,
            starting_cash=starting_cash,
            income_growth=monthly_growth if mode == "business" else 0.0,
            simulations=_SA_SIMULATIONS,
        )

        final    = paths[:, -1]
        prob_neg = float(np.mean(np.any(paths < 0, axis=1)))

        rows.append({
            "variable_value": val,
            "median_outcome": float(np.median(final)),
            "p_negative":     prob_neg,
            "p5_outcome":     float(np.percentile(final, 5)),
            "p95_outcome":    float(np.percentile(final, 95)),
        })

    return pd.DataFrame(rows, columns=[
        "variable_value", "median_outcome", "p_negative",
        "p5_outcome", "p95_outcome",
    ])

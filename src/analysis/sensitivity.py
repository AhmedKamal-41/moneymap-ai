"""
sensitivity.py
--------------
One-at-a-time (OAT) sensitivity analysis on key financial variables.
Produces a tornado chart showing which lever has the biggest impact.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def run_sensitivity(
    df: pd.DataFrame,
    horizon: int = 36,
    delta: float = 0.10,
) -> Dict:
    """
    Perturb key variables by +/- delta and measure the effect on cumulative cash.

    Parameters
    ----------
    df: transaction DataFrame
    horizon: projection horizon in months
    delta: fractional perturbation (default 10%)

    Returns a dict with impact table and tornado chart.
    """
    df = df.copy().dropna(subset=["date", "amount"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    base_income = df[df["amount"] > 0]["amount"].sum() / max(
        df["date"].dt.to_period("M").nunique(), 1
    )
    base_expense = df[df["amount"] < 0]["amount"].abs().sum() / max(
        df["date"].dt.to_period("M").nunique(), 1
    )

    def cumulative_cash(income: float, expense: float) -> float:
        return (income - expense) * horizon

    base_cash = cumulative_cash(base_income, base_expense)

    variables = {
        "Income (+10%)": cumulative_cash(base_income * (1 + delta), base_expense),
        "Income (-10%)": cumulative_cash(base_income * (1 - delta), base_expense),
        "Expenses (+10%)": cumulative_cash(base_income, base_expense * (1 + delta)),
        "Expenses (-10%)": cumulative_cash(base_income, base_expense * (1 - delta)),
    }

    impacts = {k: v - base_cash for k, v in variables.items()}
    impact_df = (
        pd.DataFrame.from_dict(impacts, orient="index", columns=["impact"])
        .sort_values("impact")
        .reset_index()
    )
    impact_df.columns = ["variable", "impact"]

    colours = ["#ef4444" if v < 0 else "#22c55e" for v in impact_df["impact"]]

    fig = go.Figure(go.Bar(
        x=impact_df["impact"],
        y=impact_df["variable"],
        orientation="h",
        marker_color=colours,
    ))
    fig.add_vline(x=0, line_color="gray", line_dash="dot")
    fig.update_layout(
        title=f"Sensitivity Tornado (±{delta:.0%} perturbation, {horizon}-month horizon)",
        xaxis_title="Impact on Cumulative Cash ($)",
        template="plotly_dark",
    )

    return {
        "impact_df": impact_df,
        "tornado_chart": fig,
        "base_cash": base_cash,
    }

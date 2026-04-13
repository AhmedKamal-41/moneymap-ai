"""
financial_health.py
-------------------
Personal and business financial health analysis.

Public API
----------
analyze_personal_health(df)  -> dict
analyze_business_health(df)  -> dict
detect_anomalies(df, mode)   -> list[dict]

All functions are pure computation — no Plotly figures, no Streamlit calls.
Charts are built in the page layer so this module stays testable and reusable.

Personal health dict includes ``debt_to_income_ratio`` and the alias
``debt_to_income`` (same value) for documentation compatibility.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
# DTI thresholds (fraction of monthly gross income)
_DTI_WARNING  = 0.36
_DTI_DANGER   = 0.43

# Emergency fund levels (months of expenses)
_EF_DANGER  = 1.0
_EF_WARNING = 3.0

# Subscription creep: >10% of monthly income
_SUB_PCT_WARNING = 0.10

# Monthly spending jump anomaly threshold
_MOM_JUMP_THRESHOLD = 0.30

# Trend significance: slope must exceed this fraction of mean to be "trending"
_TREND_THRESHOLD = 0.025

# Payroll concentration: flag if payroll > 50% of revenue
_PAYROLL_PCT_WARNING = 0.50

# Runway danger levels (months)
_RUNWAY_DANGER  = 3.0
_RUNWAY_WARNING = 6.0


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _ensure_month(df: pd.DataFrame) -> pd.DataFrame:
    if "month" not in df.columns:
        df = df.copy()
        df["month"] = df["date"].dt.to_period("M")
    return df


def _compute_trend(values: np.ndarray) -> Dict[str, Any]:
    """
    Fit a linear trend to a sequence of values.
    Returns trend label, slope ($/mo), and avg month-over-month % change.
    """
    if len(values) < 2:
        return {"trend": "stable", "slope": 0.0, "pct_change_avg": 0.0, "n": len(values)}

    x = np.arange(len(values), dtype=float)
    slope = float(np.polyfit(x, values, 1)[0])
    mean_val = float(np.mean(values))

    pct_changes: List[float] = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            pct_changes.append((values[i] - values[i - 1]) / values[i - 1])
    avg_pct = float(np.mean(pct_changes)) if pct_changes else 0.0

    rel_slope = slope / mean_val if mean_val != 0 else 0.0
    if rel_slope > _TREND_THRESHOLD:
        trend = "increasing"
    elif rel_slope < -_TREND_THRESHOLD:
        trend = "decreasing"
    else:
        trend = "stable"

    return {
        "trend": trend,
        "slope": round(slope, 2),
        "pct_change_avg": round(avg_pct, 4),
        "n": len(values),
    }


def _monthly_series(df: pd.DataFrame, value_col: str = "amount") -> List[Dict]:
    """Return sorted list of {month (str), value} dicts."""
    grouped = df.groupby("month")[value_col].sum().sort_index()
    return [
        {"month": str(p), "value": round(float(v), 2)}
        for p, v in grouped.items()
    ]


def _last_two_month_delta(series: List[Dict]) -> Optional[float]:
    """Return the absolute change between the last two months, or None."""
    if len(series) < 2:
        return None
    return round(series[-1]["value"] - series[-2]["value"], 2)


def _top_growing_categories(expense_df: pd.DataFrame) -> List[Dict]:
    """
    Compare first-half vs second-half average monthly spend per category.
    Returns top-3 categories with the largest absolute spending increase.
    """
    expense_df = _ensure_month(expense_df)
    months = sorted(expense_df["month"].unique())
    if len(months) < 2:
        return []

    mid = max(1, len(months) // 2)
    first_months  = months[:mid]
    second_months = months[mid:]

    monthly_cat = (
        expense_df
        .groupby(["month", "category"])["amount_abs"]
        .sum()
        .reset_index()
    )

    first_avg  = monthly_cat[monthly_cat["month"].isin(first_months)] .groupby("category")["amount_abs"].mean()
    second_avg = monthly_cat[monthly_cat["month"].isin(second_months)].groupby("category")["amount_abs"].mean()

    growth = []
    for cat in set(first_avg.index) & set(second_avg.index):
        f, s = float(first_avg[cat]), float(second_avg[cat])
        if f > 0 and s - f > 5:          # ignore noise < $5
            growth.append({
                "category":        cat,
                "pct_change":      round((s - f) / f, 4),
                "absolute_change": round(s - f, 2),
                "first_half_avg":  round(f, 2),
                "second_half_avg": round(s, 2),
            })

    growth.sort(key=lambda r: r["absolute_change"], reverse=True)
    return growth[:3]


# ── Personal flags ─────────────────────────────────────────────────────────────

def _personal_flags(
    savings_rate: float,
    emergency_fund_months: float,
    dti: float,
    subscription_total: float,
    monthly_income: float,
    mom_trend: Dict,
    spending_by_category: Dict,
) -> List[Dict]:
    flags: List[Dict] = []

    # Savings / deficit
    if savings_rate < 0:
        flags.append({
            "level": "error",
            "msg": "Spending exceeds income — you are running a cash deficit.",
        })
    elif savings_rate < 0.10:
        spend_pct = (1 - savings_rate) * 100
        flags.append({
            "level": "warning",
            "msg": f"Spending is {spend_pct:.0f}% of income. Less than 10% is being saved.",
        })

    # Emergency fund
    if emergency_fund_months < _EF_DANGER:
        flags.append({
            "level": "error",
            "msg": "Emergency fund covers less than 1 month of expenses. "
                   "Build this before investing anywhere else.",
        })
    elif emergency_fund_months < _EF_WARNING:
        flags.append({
            "level": "warning",
            "msg": f"Emergency fund covers {emergency_fund_months:.1f} months of expenses. "
                   f"Target is 3–6 months.",
        })

    # Debt-to-income
    if dti > _DTI_DANGER:
        flags.append({
            "level": "error",
            "msg": f"Debt-to-income ratio is {dti:.0%} — above the 43% lender threshold.",
        })
    elif dti > _DTI_WARNING:
        flags.append({
            "level": "warning",
            "msg": f"Debt-to-income ratio is {dti:.0%} — approaching the 36% healthy limit.",
        })

    # Subscription creep
    sub_pct = subscription_total / monthly_income if monthly_income > 0 else 0
    if sub_pct > _SUB_PCT_WARNING:
        flags.append({
            "level": "warning",
            "msg": f"Subscriptions total ${subscription_total:,.0f}/month "
                   f"({sub_pct:.0%} of income). Review for unused services.",
        })
    elif subscription_total > 150:
        flags.append({
            "level": "info",
            "msg": f"Subscription spend is ${subscription_total:,.0f}/month. "
                   "Consider auditing for unused services.",
        })

    # Spending trend
    if mom_trend["trend"] == "increasing" and mom_trend["pct_change_avg"] > 0.05:
        flags.append({
            "level": "warning",
            "msg": f"Monthly spending is trending up "
                   f"({mom_trend['pct_change_avg'] * 100:.1f}% avg month-over-month).",
        })

    return flags


# ── Business flags ─────────────────────────────────────────────────────────────

def _business_flags(
    gross_margin_pct: float,
    net_margin_pct: float,
    burn_rate: float,
    runway_months: float,
    rev_trend: Dict,
    exp_trend: Dict,
    payroll_pct: float,
    margin_trend: Dict,
) -> List[Dict]:
    flags: List[Dict] = []

    # Runway
    if burn_rate > 0:
        if runway_months < _RUNWAY_DANGER:
            flags.append({
                "level": "error",
                "msg": f"Runway is only {runway_months:.1f} months at current burn rate "
                       f"(${burn_rate:,.0f}/month). Immediate action required.",
            })
        elif runway_months < _RUNWAY_WARNING:
            flags.append({
                "level": "warning",
                "msg": f"Runway is {runway_months:.1f} months. "
                       "Target 12+ months of runway.",
            })

    # Margins
    if gross_margin_pct < 0.30:
        flags.append({
            "level": "error",
            "msg": f"Gross margin is {gross_margin_pct:.1%} — below 30%. "
                   "COGS is consuming most of revenue.",
        })
    elif gross_margin_pct < 0.50:
        flags.append({
            "level": "warning",
            "msg": f"Gross margin is {gross_margin_pct:.1%}. "
                   "Consider reducing COGS or raising prices.",
        })

    if net_margin_pct < 0:
        flags.append({
            "level": "error",
            "msg": f"Net margin is {net_margin_pct:.1%} — the business is losing money.",
        })

    if margin_trend["trend"] == "decreasing" and margin_trend["n"] >= 3:
        flags.append({
            "level": "warning",
            "msg": "Net margins are declining over the past months. "
                   "Revenue growth is not keeping pace with expenses.",
        })

    # Revenue trend
    if rev_trend["trend"] == "decreasing":
        flags.append({
            "level": "warning",
            "msg": f"Revenue is trending downward "
                   f"({rev_trend['pct_change_avg'] * 100:.1f}% avg month-over-month change).",
        })

    # Expense growth outpacing revenue
    if (exp_trend["trend"] == "increasing"
            and rev_trend["trend"] != "increasing"
            and exp_trend["pct_change_avg"] > 0.05):
        flags.append({
            "level": "warning",
            "msg": "Expenses are growing while revenue is flat or declining. "
                   "Burn rate is accelerating.",
        })

    # Payroll concentration
    if payroll_pct > _PAYROLL_PCT_WARNING:
        flags.append({
            "level": "warning",
            "msg": f"Payroll is {payroll_pct:.0%} of revenue. "
                   "Above 50% leaves little room for other growth investments.",
        })

    return flags


# ── Public: personal ──────────────────────────────────────────────────────────

def analyze_personal_health(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute a comprehensive personal financial health profile.

    Expected input: output of parse_personal_csv() — columns
    date, month, amount (signed), category, description.

    Returns a plain dict (no Plotly objects) suitable for caching and testing.
    """
    df = _ensure_month(df.copy())

    income_df  = df[df["amount"] > 0]
    expense_df = df[df["amount"] < 0].copy()
    expense_df["amount_abs"] = expense_df["amount"].abs()

    n_months = max(df["month"].nunique(), 1)

    total_income   = float(income_df["amount"].sum())
    total_expenses = float(expense_df["amount_abs"].sum())
    net_cash       = total_income - total_expenses
    monthly_income   = total_income   / n_months
    monthly_expenses = total_expenses / n_months
    savings_rate     = net_cash / total_income if total_income > 0 else 0.0

    # Debt-to-income (annualised debt / annualised income)
    debt_total = float(
        expense_df[expense_df["category"] == "debt_payment"]["amount_abs"].sum()
    )
    dti = debt_total / total_income if total_income > 0 else 0.0

    # Emergency fund — use max(0, net_cash) as savings proxy
    ef_months = max(net_cash, 0) / monthly_expenses if monthly_expenses > 0 else 0.0

    # Spending breakdown (expenses only, sorted descending)
    cat_totals = (
        expense_df.groupby("category")["amount_abs"]
        .sum()
        .sort_values(ascending=False)
    )
    spending_by_category = {k: round(float(v), 2) for k, v in cat_totals.items()}

    # Subscription detail
    sub_df = expense_df[expense_df["category"] == "subscriptions"]
    sub_monthly_total = float(sub_df["amount_abs"].sum()) / n_months
    sub_list = (
        sub_df.groupby("description")["amount_abs"]
        .agg(total="sum", occurrences="count")
        .reset_index()
        .assign(monthly_avg=lambda x: (x["total"] / n_months).round(2))
        .sort_values("total", ascending=False)
        .rename(columns={"description": "name"})
        .assign(total=lambda x: x["total"].round(2))
        .to_dict("records")
    )

    # Month-over-month spending trend
    monthly_exp_series = _monthly_series(
        expense_df.assign(amount=expense_df["amount_abs"]), "amount"
    )
    monthly_inc_series = _monthly_series(income_df, "amount")
    mom_trend = _compute_trend(
        np.array([r["value"] for r in monthly_exp_series])
    )

    # Top 3 growing expense categories
    top_growing = _top_growing_categories(expense_df)

    # Month-over-month deltas for metric cards
    inc_delta = _last_two_month_delta(monthly_inc_series)
    exp_delta = _last_two_month_delta(monthly_exp_series)

    flags = _personal_flags(
        savings_rate=savings_rate,
        emergency_fund_months=ef_months,
        dti=dti,
        subscription_total=sub_monthly_total,
        monthly_income=monthly_income,
        mom_trend=mom_trend,
        spending_by_category=spending_by_category,
    )

    return {
        # Scalars
        "monthly_income":            round(monthly_income, 2),
        "monthly_expenses":          round(monthly_expenses, 2),
        "total_income":              round(total_income, 2),
        "total_expenses":            round(total_expenses, 2),
        "net_cash":                  round(net_cash, 2),
        "savings_rate":              round(savings_rate, 4),
        "debt_to_income_ratio":      round(dti, 4),
        "debt_to_income":            round(dti, 4),
        "emergency_fund_months":     round(ef_months, 1),
        # Breakdowns
        "spending_by_category":      spending_by_category,
        "subscription_total":        round(sub_monthly_total, 2),
        "subscription_list":         sub_list,
        # Trends
        "month_over_month_spending_trend": mom_trend,
        "top_3_growing_categories":  top_growing,
        # Time series (for charts in the page)
        "monthly_income_series":     monthly_inc_series,
        "monthly_expense_series":    monthly_exp_series,
        # Deltas for metric cards
        "income_delta":              inc_delta,
        "expense_delta":             exp_delta,
        # Meta
        "n_months":                  n_months,
        "flags":                     flags,
    }


# ── Public: business ──────────────────────────────────────────────────────────

def analyze_business_health(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute a comprehensive business financial health profile.

    Expected input: output of parse_business_csv() — columns
    date, month, type (revenue/expense), category, amount (signed), description.
    """
    df = _ensure_month(df.copy())

    revenue_df = df[df["amount"] > 0]
    expense_df = df[df["amount"] < 0].copy()
    expense_df["amount_abs"] = expense_df["amount"].abs()

    n_months = max(df["month"].nunique(), 1)

    total_revenue  = float(revenue_df["amount"].sum())
    total_expenses = float(expense_df["amount_abs"].sum())
    net_income     = total_revenue - total_expenses

    monthly_revenue_avg  = total_revenue  / n_months
    monthly_expenses_avg = total_expenses / n_months

    # Gross margin: (revenue − COGS) / revenue
    cogs_total    = float(expense_df[expense_df["category"] == "cogs"]["amount_abs"].sum())
    gross_profit  = total_revenue - cogs_total
    gross_margin  = gross_profit  / total_revenue if total_revenue > 0 else 0.0
    net_margin    = net_income    / total_revenue if total_revenue > 0 else 0.0

    # Burn rate: average monthly net outflow across months with negative net flow
    monthly_net = (
        df.groupby("month")["amount"].sum().sort_index()
    )
    burning = monthly_net[monthly_net < 0]
    burn_rate = float(burning.abs().mean()) if len(burning) > 0 else 0.0

    # Runway — meaningful only when burning; if profitable use accumulated cash / avg burn
    if burn_rate > 0:
        runway = max(net_income, 0) / burn_rate
    else:
        runway = float("inf")

    # Revenue concentration (CV of monthly revenue — higher = more lumpy)
    monthly_rev_series = revenue_df.groupby("month")["amount"].sum().sort_index()
    rev_cv = (
        float(monthly_rev_series.std() / monthly_rev_series.mean())
        if len(monthly_rev_series) > 1 and monthly_rev_series.mean() > 0
        else 0.0
    )

    # Trends
    monthly_exp_series_raw = expense_df.groupby("month")["amount_abs"].sum().sort_index()
    rev_trend = _compute_trend(monthly_rev_series.values)
    exp_trend = _compute_trend(monthly_exp_series_raw.values)

    # Monthly net-margin trend
    common = sorted(set(monthly_rev_series.index) & set(monthly_exp_series_raw.index))
    if len(common) >= 3:
        margins = np.array([
            (float(monthly_rev_series[m]) - float(monthly_exp_series_raw[m]))
            / float(monthly_rev_series[m])
            for m in common if float(monthly_rev_series[m]) > 0
        ])
        margin_trend = _compute_trend(margins)
    else:
        margin_trend = {"trend": "stable", "slope": 0.0, "pct_change_avg": 0.0, "n": len(common)}

    # Expense breakdown
    cat_totals = (
        expense_df.groupby("category")["amount_abs"]
        .sum()
        .sort_values(ascending=False)
    )
    expense_breakdown = {k: round(float(v), 2) for k, v in cat_totals.items()}

    # Payroll concentration
    payroll_total = float(expense_df[expense_df["category"] == "payroll"]["amount_abs"].sum())
    payroll_pct   = payroll_total / total_revenue if total_revenue > 0 else 0.0

    # Time series for charts
    rev_records = [
        {"month": str(p), "value": round(float(v), 2)}
        for p, v in monthly_rev_series.items()
    ]
    exp_records = [
        {"month": str(p), "value": round(float(v), 2)}
        for p, v in monthly_exp_series_raw.items()
    ]
    net_records = [
        {"month": str(p), "value": round(float(monthly_net[p]), 2)}
        for p in sorted(monthly_net.index)
    ]

    # Deltas for metric cards
    rev_delta = _last_two_month_delta(rev_records)
    exp_delta = _last_two_month_delta(exp_records)

    flags = _business_flags(
        gross_margin_pct=gross_margin,
        net_margin_pct=net_margin,
        burn_rate=burn_rate,
        runway_months=runway,
        rev_trend=rev_trend,
        exp_trend=exp_trend,
        payroll_pct=payroll_pct,
        margin_trend=margin_trend,
    )

    return {
        # Scalars
        "monthly_revenue":           round(monthly_revenue_avg, 2),
        "monthly_expenses":          round(monthly_expenses_avg, 2),
        "total_revenue":             round(total_revenue, 2),
        "total_expenses":            round(total_expenses, 2),
        "net_income":                round(net_income, 2),
        "gross_profit":              round(gross_profit, 2),
        "gross_margin_pct":          round(gross_margin, 4),
        "net_margin_pct":            round(net_margin, 4),
        "burn_rate":                 round(burn_rate, 2),
        "runway_months":             round(runway, 1) if runway != float("inf") else None,
        "revenue_concentration_cv":  round(rev_cv, 3),
        # Breakdowns
        "expense_breakdown":         expense_breakdown,
        "payroll_pct_of_revenue":    round(payroll_pct, 4),
        # Trends
        "revenue_trend":             rev_trend,
        "expense_trend":             exp_trend,
        "margin_trend":              margin_trend,
        # Time series
        "monthly_revenue_series":    rev_records,
        "monthly_expense_series":    exp_records,
        "monthly_net_series":        net_records,
        # Deltas
        "revenue_delta":             rev_delta,
        "expense_delta":             exp_delta,
        # Meta
        "n_months":                  n_months,
        "flags":                     flags,
    }


# ── Public: anomaly detection ─────────────────────────────────────────────────

def detect_anomalies(df: pd.DataFrame, mode: str = "personal") -> List[Dict]:
    """
    Detect three classes of anomalies:

    1. Statistical outliers — expense transactions strictly **above** the
       upper tail ``mean(amount_abs) + 3 * std(amount_abs)`` within each
       category (not two-sided |z| > 3; small "too cheap" expenses are ignored).
    2. Duplicate charges — same date, same amount, same category.
    3. Monthly spend jumps — months where total spending rose > 30% vs prior month.

    Returns a list of dicts with keys:
    date, amount, category, description, reason, anomaly_type.
    """
    df = _ensure_month(df.copy())
    anomalies: List[Dict] = []
    cat_col = "category" if "category" in df.columns else "type"

    expense_df = df[df["amount"] < 0].copy()
    expense_df["amount_abs"] = expense_df["amount"].abs()
    expense_df["date_str"]   = expense_df["date"].dt.strftime("%Y-%m-%d")

    # ── 1. Per-category statistical outliers ──────────────────────────────────
    for cat, group in expense_df.groupby(cat_col):
        if len(group) < 4:          # need ≥4 observations for 3σ to be meaningful
            continue
        mean = float(group["amount_abs"].mean())
        std  = float(group["amount_abs"].std())
        if std < 1e-6:
            continue
        threshold = mean + 3 * std
        for _, row in group[group["amount_abs"] > threshold].iterrows():
            z = (row["amount_abs"] - mean) / std
            anomalies.append({
                "anomaly_type": "statistical_outlier",
                "date":         row["date_str"],
                "amount":       -round(float(row["amount_abs"]), 2),
                "category":     str(cat),
                "description":  str(row.get("description", "")),
                "reason": (
                    f"Unusually large transaction: ${row['amount_abs']:,.0f} "
                    f"({z:.1f}σ above {cat} mean of ${mean:,.0f})"
                ),
            })

    # ── 2. Duplicate charges ─────────────────────────────────────────────────
    expense_df["amount_r"] = expense_df["amount_abs"].round(2)
    dupe_key = ["date_str", "amount_r", cat_col]
    dupes = expense_df[expense_df.duplicated(subset=dupe_key, keep=False)]
    seen: set = set()
    for _, row in dupes.iterrows():
        key = (row["date_str"], row["amount_r"], row[cat_col])
        if key not in seen:
            seen.add(key)
            count = int((expense_df[dupe_key].eq(row[dupe_key]).all(axis=1)).sum())
            anomalies.append({
                "anomaly_type": "duplicate_charge",
                "date":         row["date_str"],
                "amount":       -float(row["amount_r"]),
                "category":     str(row[cat_col]),
                "description":  str(row.get("description", "")),
                "reason": (
                    f"Possible duplicate: ${row['amount_r']:,.2f} charged "
                    f"{count}× on {row['date_str']} in '{row[cat_col]}'"
                ),
            })

    # ── 3. Monthly spend jump > 30% ──────────────────────────────────────────
    monthly_spend = (
        expense_df.groupby("month")["amount_abs"].sum().sort_index()
    )
    months = list(monthly_spend.index)
    for i in range(1, len(months)):
        prev = float(monthly_spend.iloc[i - 1])
        curr = float(monthly_spend.iloc[i])
        if prev > 0 and (curr - prev) / prev > _MOM_JUMP_THRESHOLD:
            pct = (curr - prev) / prev
            anomalies.append({
                "anomaly_type": "spending_spike",
                "date":         str(months[i]),
                "amount":       None,
                "category":     "monthly_total",
                "description":  "",
                "reason": (
                    f"Spending in {months[i]} jumped {pct:.0%} vs prior month "
                    f"(${prev:,.0f} → ${curr:,.0f})"
                ),
            })

    return anomalies

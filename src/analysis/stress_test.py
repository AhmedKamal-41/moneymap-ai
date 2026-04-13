"""
stress_test.py
--------------
Apply historical crash scenarios as financial shocks and measure the impact
on portfolio value, cash runway, monthly burn, and recovery timeline.

Public API
----------
SCENARIOS            : dict[str, dict]
run_stress_test(scenario_name, financial_health, portfolio_value, mode) -> dict
run_all_stress_tests(financial_health, portfolio_value, mode)            -> list[dict]

The third argument to ``run_stress_test`` / ``run_all_stress_tests`` is the
liquid **investment portfolio value in dollars**. Pass a ``float`` or ``int``,
or a small ``dict`` (e.g. ``{"portfolio_value": 50000}`` — also accepts
``value``, ``total``, ``market_value``, ``equity``) which is coerced to a
scalar before shocks are applied.

financial_health dict schema (personal)
---------------------------------------
    monthly_income        float   — avg monthly income
    monthly_expenses      float   — avg monthly expenses
    net_cash              float   — total liquid savings
    debt_rate             float   — primary APR as decimal (0.18 = 18%)
    debt_balance          float

financial_health dict schema (business)
---------------------------------------
    monthly_revenue       float
    monthly_expenses      float
    cash_balance          float
    debt_rate             float
    debt_balance          float
    gross_margin_pct      float   — fraction
    runway_months         float | None
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np


def _coerce_portfolio_value(portfolio: Union[float, int, Dict[str, Any]]) -> float:
    """
    Normalize portfolio input to a single dollar amount.

    Accepts a scalar or a dict from UI/session payloads with common keys.
    """
    if isinstance(portfolio, dict):
        for key in ("portfolio_value", "value", "total", "market_value", "equity"):
            if key in portfolio and portfolio[key] is not None:
                try:
                    return float(portfolio[key])
                except (TypeError, ValueError):
                    continue
        return 0.0
    try:
        return float(portfolio)
    except (TypeError, ValueError):
        return 0.0

# ─────────────────────────────────────────────────────────────────────────────
# Scenario definitions
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "2008_financial_crisis": {
        "label":             "2008 Financial Crisis",
        "equity_shock":      -0.50,
        "duration_months":   18,
        "unemployment_spike": 0.05,    # 5pp rise → used as income reduction for personal
        "revenue_drop":       0.20,    # business revenue drops 20%
        "description":       "Markets fell 50%, unemployment doubled, credit froze for 18 months.",
        "icon":              "🏦",
        "color":             "#f85149",
    },
    "covid_2020": {
        "label":             "COVID-19 Crash (2020)",
        "equity_shock":      -0.34,
        "duration_months":   3,
        "unemployment_spike": 0.10,    # 10pp spike — sharp & severe
        "revenue_drop":       0.30,    # business revenue collapsed short-term
        "description":       "Sharp 34% crash, fastest recovery in history, massive unemployment spike.",
        "icon":              "🦠",
        "color":             "#db6d28",
    },
    "inflation_shock": {
        "label":             "Inflation Shock",
        "equity_shock":      -0.20,
        "inflation_add":      0.04,    # expenses rise 4pp above normal
        "rate_hike":          0.03,    # debt rates rise 3pp
        "duration_months":   12,
        "description":       "Inflation surges, rates spike, equities drop 20%, debt becomes expensive.",
        "icon":              "📈",
        "color":             "#d29922",
    },
    "mild_recession": {
        "label":             "Mild Recession",
        "equity_shock":      -0.15,
        "revenue_drop":       0.15,    # income / revenue falls 15%
        "duration_months":   12,
        "description":       "Moderate downturn, revenue dips 15%, slow 12-month recovery.",
        "icon":              "📉",
        "color":             "#8b949e",
    },
    "rate_spike": {
        "label":             "Rate Spike",
        "equity_shock":      -0.10,
        "rate_hike":          0.05,    # rates jump 5pp — debt service spikes
        "duration_months":   9,
        "description":       "Rates jump 5pp, debt costs spike, equities soften 10%.",
        "icon":              "🔺",
        "color":             "#a371f7",
    },
}

# Historical average equity recovery speeds (months to full recovery)
# Used only when we can't compute from cash paths (portfolio-only scenarios)
_HIST_RECOVERY_MONTHS = {
    "2008_financial_crisis": 54,
    "covid_2020":             22,
    "inflation_shock":        30,
    "mild_recession":         18,
    "rate_spike":             12,
}

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

_SIM_MONTHS = 24   # total simulation horizon


def _apply_shocks(
    scenario: Dict[str, Any],
    base_income: float,
    base_expenses: float,
    debt_balance: float,
    debt_rate: float,
) -> Tuple[float, float, float]:
    """
    Return (shocked_income, shocked_expenses, monthly_debt_delta) after applying
    the scenario's shocks.  All values are in $/month.
    """
    shocked_income = base_income
    shocked_expenses = base_expenses

    # Income / revenue reduction (unemployment_spike or revenue_drop)
    income_shock_frac = scenario.get("revenue_drop", 0.0)
    income_shock_frac += scenario.get("unemployment_spike", 0.0)
    shocked_income = base_income * (1.0 - min(income_shock_frac, 0.90))

    # Expense inflation
    inflation_add = scenario.get("inflation_add", 0.0)
    shocked_expenses = base_expenses * (1.0 + inflation_add)

    # Additional monthly debt service from rate hike
    rate_hike = scenario.get("rate_hike", 0.0)
    monthly_debt_delta = debt_balance * rate_hike / 12.0

    return shocked_income, shocked_expenses, monthly_debt_delta


def _simulate_cash(
    starting_cash: float,
    base_net: float,
    shocked_net: float,
    duration: int,
    total: int = _SIM_MONTHS,
) -> Tuple[List[float], List[float]]:
    """
    Simulate base and stressed cash paths over `total` months.

    Shock is active for months [0, duration); post-shock phase uses base_net
    (full recovery at base rate — conservative but clean).

    Returns (base_path, stressed_path), each length total+1 (including month 0).
    """
    base = [starting_cash]
    for _ in range(total):
        base.append(base[-1] + base_net)

    stressed = [starting_cash]
    for m in range(total):
        net = shocked_net if m < duration else base_net
        stressed.append(stressed[-1] + net)

    return base, stressed


def _worst_month(cash_path: List[float]) -> int:
    """Return the 1-based month index with the lowest cash balance."""
    idx = int(np.argmin(cash_path))
    return max(1, idx)


def _floor_breached(cash_path: List[float]) -> bool:
    return any(v < 0.0 for v in cash_path)


def _depletion_month(cash_path: List[float]) -> Optional[int]:
    """First 1-based month where cash goes negative, or None."""
    for i, v in enumerate(cash_path):
        if v < 0.0:
            return max(1, i)
    return None


def _recovery_from_shock(
    starting_cash: float,
    stressed_path: List[float],
    base_net: float,
    duration: int,
) -> Optional[int]:
    """
    Months after the shock ends until the stressed path returns to starting_cash.
    Returns None if recovery is impossible (base_net <= 0).
    """
    if duration >= len(stressed_path):
        end_cash = stressed_path[-1]
    else:
        end_cash = stressed_path[duration]

    if end_cash >= starting_cash:
        return 0

    if base_net <= 0:
        return None

    gap = starting_cash - end_cash
    return int(math.ceil(gap / base_net))


def _severity_score(
    portfolio_impact_pct: float,
    floor_breached: bool,
    new_monthly_net: float,
    base_monthly_net: float,
) -> float:
    """
    0-100 severity score — higher = more severe.
    Blends portfolio loss, cash floor breach, and net income deterioration.
    """
    port_component = abs(portfolio_impact_pct) * 60.0          # 0-30 for a 50% crash

    # Cash flow deterioration
    if base_monthly_net != 0:
        net_ratio = (base_monthly_net - new_monthly_net) / abs(base_monthly_net)
        cf_component = min(net_ratio * 30.0, 30.0)
    else:
        cf_component = 15.0

    floor_component = 10.0 if floor_breached else 0.0

    return min(100.0, port_component + cf_component + floor_component)


# ─────────────────────────────────────────────────────────────────────────────
# Public: run_stress_test
# ─────────────────────────────────────────────────────────────────────────────

def run_stress_test(
    scenario_name: str,
    financial_health: Dict[str, Any],
    portfolio_value: Union[float, int, Dict[str, Any]],
    mode: str = "personal",
) -> Dict[str, Any]:
    """
    Apply a single historical shock scenario to the user's financial numbers.

    Parameters
    ----------
    scenario_name    : key in SCENARIOS
    financial_health : see module docstring for schema
    portfolio_value  : current investment / equity portfolio value in $ (scalar
                       or dict — see module docstring for accepted dict keys)
    mode             : "personal" | "business"

    Returns
    -------
    dict with keys:
        scenario_name            str
        label                    str
        description              str
        icon                     str
        color                    str   — scenario accent colour

        portfolio_impact_pct     float — fractional change (e.g. -0.50)
        portfolio_impact_dollars float — $ change
        new_portfolio_value      float

        base_monthly_income      float — personal monthly income before shock
        new_monthly_income       float — personal (or revenue for business)
        new_monthly_expenses     float
        new_monthly_net          float — new_income - new_expenses
        base_monthly_net         float — original net

        new_monthly_burn         float — max(0, expenses - income) after shock
        new_runway_months        float | None   — business
        months_until_savings_depleted float | None — personal

        worst_month              int    — 1-based month with lowest cash
        floor_breached           bool
        depletion_month          int | None  — 1-based first month cash < 0

        recovery_months          int | None
        recovery_summary         str

        cash_path_base           list[float]   — length SIM_MONTHS + 1
        cash_path_stressed       list[float]

        severity_score           float   — 0-100, higher = more severe
    """
    scenario = SCENARIOS.get(scenario_name)
    if scenario is None:
        raise ValueError(f"Unknown scenario: {scenario_name!r}. "
                         f"Valid keys: {list(SCENARIOS)}")

    pv = _coerce_portfolio_value(portfolio_value)

    equity_shock   = scenario.get("equity_shock",     0.0)
    duration       = int(scenario.get("duration_months", 12))
    debt_rate      = float(financial_health.get("debt_rate",    0.0) or 0.0)
    debt_balance   = float(financial_health.get("debt_balance", 0.0) or 0.0)

    # ── Derive base income / expenses by mode ─────────────────────────────────
    if mode == "personal":
        base_income   = float(financial_health.get("monthly_income",   5_500.0) or 5_500.0)
        base_expenses = float(financial_health.get("monthly_expenses", 4_500.0) or 4_500.0)
        starting_cash = float(financial_health.get("net_cash", 0.0) or 0.0)
        # Include base monthly debt interest in expenses
        if debt_balance > 0 and debt_rate > 0:
            base_expenses += debt_balance * debt_rate / 12.0
    else:
        base_income   = float(financial_health.get("monthly_revenue",  47_000.0) or 47_000.0)
        base_expenses = float(financial_health.get("monthly_expenses", 40_000.0) or 40_000.0)
        starting_cash = float(financial_health.get("cash_balance",     88_000.0) or 88_000.0)
        if debt_balance > 0 and debt_rate > 0:
            base_expenses += debt_balance * debt_rate / 12.0

    base_net = base_income - base_expenses

    # ── Apply shocks ─────────────────────────────────────────────────────────
    shocked_income, shocked_expenses, monthly_debt_delta = _apply_shocks(
        scenario, base_income, base_expenses, debt_balance, debt_rate,
    )
    shocked_expenses += monthly_debt_delta
    shocked_net = shocked_income - shocked_expenses

    # ── Portfolio impact ──────────────────────────────────────────────────────
    new_portfolio = pv * (1.0 + equity_shock)
    port_impact_dollars = new_portfolio - pv

    # ── Cash flow simulation over 24 months ──────────────────────────────────
    cash_base, cash_stressed = _simulate_cash(
        starting_cash, base_net, shocked_net, duration,
    )

    # ── Derived metrics ───────────────────────────────────────────────────────
    new_burn     = max(0.0, shocked_expenses - shocked_income)
    worst_mo     = _worst_month(cash_stressed)
    is_breached  = _floor_breached(cash_stressed)
    deplete_mo   = _depletion_month(cash_stressed)
    recov_months = _recovery_from_shock(starting_cash, cash_stressed, base_net, duration)

    # Runway / depletion under shock
    if mode == "personal":
        new_runway = None
        if shocked_net < 0:
            months_dep: Optional[float] = starting_cash / abs(shocked_net) if starting_cash > 0 else 0.0
        else:
            months_dep = None
    else:
        months_dep = None
        if shocked_net < 0:
            new_runway: Optional[float] = starting_cash / abs(shocked_net) if starting_cash > 0 else 0.0
        else:
            new_runway = None   # profitable even under shock

    # ── Recovery summary ──────────────────────────────────────────────────────
    hist_recov = _HIST_RECOVERY_MONTHS.get(scenario_name, 24)
    if recov_months == 0:
        recovery_summary = "Cash position is not impaired — no recovery period needed."
    elif recov_months is None:
        recovery_summary = (
            "Recovery requires restoring positive cash flow first. "
            f"Historically, {scenario['label']} conditions resolved within {hist_recov} months."
        )
    else:
        total_recov = duration + recov_months
        recovery_summary = (
            f"At your base monthly savings rate, it would take ~{recov_months} months "
            f"after the shock ends to rebuild to your pre-shock position "
            f"(~{total_recov} months total from today). "
            f"Historical precedent for this scenario: ~{hist_recov} months to equity recovery."
        )

    severity = _severity_score(
        equity_shock,
        is_breached,
        shocked_net,
        base_net,
    )

    return {
        # Identity
        "scenario_name":              scenario_name,
        "label":                      scenario["label"],
        "description":                scenario["description"],
        "icon":                       scenario.get("icon",  "💥"),
        "color":                      scenario.get("color", "#f85149"),
        # Portfolio
        "portfolio_impact_pct":       equity_shock,
        "portfolio_impact_dollars":   port_impact_dollars,
        "new_portfolio_value":        new_portfolio,
        # Cash flow
        "base_monthly_income":        base_income,
        "new_monthly_income":         shocked_income,
        "new_monthly_expenses":       shocked_expenses,
        "base_monthly_net":           base_net,
        "new_monthly_net":            shocked_net,
        "new_monthly_burn":           new_burn,
        # Survival metrics
        "new_runway_months":                  new_runway,
        "months_until_savings_depleted":      months_dep,
        "worst_month":                        worst_mo,
        "floor_breached":                     is_breached,
        "depletion_month":                    deplete_mo,
        # Recovery
        "recovery_months":            recov_months,
        "recovery_summary":           recovery_summary,
        # Simulation paths (month 0 … SIM_MONTHS)
        "cash_path_base":             cash_base,
        "cash_path_stressed":         cash_stressed,
        # Sorting key
        "severity_score":             severity,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: run_all_stress_tests
# ─────────────────────────────────────────────────────────────────────────────

def run_all_stress_tests(
    financial_health: Dict[str, Any],
    portfolio_value: Union[float, int, Dict[str, Any]],
    mode: str = "personal",
) -> List[Dict[str, Any]]:
    """
    Run every scenario and return results sorted by severity (worst first).

    Parameters
    ----------
    financial_health : see module docstring
    portfolio_value  : current portfolio / investment value in $ (scalar or dict)
    mode             : "personal" | "business"

    Returns
    -------
    list[dict] — each dict is the output of run_stress_test(), sorted by
    severity_score descending (most severe scenario first).
    """
    pv = _coerce_portfolio_value(portfolio_value)
    results = []
    for name in SCENARIOS:
        try:
            result = run_stress_test(name, financial_health, pv, mode)
            results.append(result)
        except Exception as exc:
            # Don't let one bad scenario break the whole run
            results.append({
                "scenario_name":    name,
                "label":            SCENARIOS[name].get("label", name),
                "description":      SCENARIOS[name].get("description", ""),
                "icon":             SCENARIOS[name].get("icon", "💥"),
                "color":            SCENARIOS[name].get("color", "#f85149"),
                "portfolio_impact_pct":     0.0,
                "portfolio_impact_dollars": 0.0,
                "new_portfolio_value":      float(pv),
                "base_monthly_income":      0.0,
                "new_monthly_income":       0.0,
                "new_monthly_expenses":     0.0,
                "base_monthly_net":         0.0,
                "new_monthly_net":          0.0,
                "new_monthly_burn":         0.0,
                "new_runway_months":        None,
                "months_until_savings_depleted": None,
                "worst_month":              1,
                "floor_breached":           False,
                "depletion_month":          None,
                "recovery_months":          None,
                "recovery_summary":         f"Error: {exc}",
                "cash_path_base":           [],
                "cash_path_stressed":       [],
                "severity_score":           0.0,
            })

    results.sort(key=lambda r: r["severity_score"], reverse=True)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Resilience score (standalone utility for the page layer)
# ─────────────────────────────────────────────────────────────────────────────

def resilience_score(all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute a 0-100 resilience score from a list of run_all_stress_tests() results.

    A scenario is "survived" if the cash path is still positive at month 12
    (i.e. the user hasn't run out of money within the first year of the shock).

    Returns
    -------
    dict with:
        score        int     — 0-100
        label        str     — "Strong" | "Moderate" | "At Risk" | "Vulnerable"
        color        str     — hex accent colour
        survived     int     — number of scenarios survived
        total        int     — total scenarios tested
        detail       str     — one-sentence interpretation
    """
    total = len(all_results)
    if total == 0:
        return {"score": 0, "label": "N/A", "color": "#8b949e",
                "survived": 0, "total": 0, "detail": "No scenarios run."}

    survived = 0
    for r in all_results:
        path = r.get("cash_path_stressed", [])
        # month 12 is index 12 in the 0-indexed path (month 0 is starting cash)
        month12_cash = path[12] if len(path) > 12 else (path[-1] if path else 0.0)
        if month12_cash > 0:
            survived += 1

    score = int(round(survived / total * 100))

    if score == 100:
        label  = "Strong"
        color  = "#3fb950"
        detail = (f"You survive all {total} scenarios with positive cash through month 12. "
                  "Your financial foundation is resilient.")
    elif score >= 80:
        label  = "Moderate"
        color  = "#d29922"
        detail = (f"You survive {survived} of {total} scenarios. "
                  "A few tail risks could deplete reserves — consider strengthening the buffer.")
    elif score >= 60:
        label  = "At Risk"
        color  = "#db6d28"
        detail = (f"You survive {survived} of {total} scenarios. "
                  "Severe shocks breach your cash floor within a year — build runway urgently.")
    else:
        label  = "Vulnerable"
        color  = "#f85149"
        detail = (f"You survive only {survived} of {total} scenarios by month 12. "
                  "The current financial position has limited shock absorption capacity.")

    return {
        "score":    score,
        "label":    label,
        "color":    color,
        "survived": survived,
        "total":    total,
        "detail":   detail,
    }

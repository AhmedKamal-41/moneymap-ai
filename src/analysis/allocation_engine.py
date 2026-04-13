"""
allocation_engine.py
--------------------
Rule-based, transparent scoring engine that ranks where money should go next.

Every score is computed from an explicit chain of rules so that the page
layer can show *why* a recommendation was made — not just a number.

Public API
----------
PERSONAL_OPTIONS    : list[str]
BUSINESS_OPTIONS    : list[str]
score_allocation(option, context)            -> dict
recommend(context, mode)                     -> dict
explain_recommendation(ranked_list, context) -> str

Context dict schema
-------------------
context = {
    "financial_health": {
        # Personal
        "monthly_income":        float,
        "monthly_expenses":      float,
        "savings_rate":          float,   # fraction  (0.15 = 15%)
        "emergency_fund_months": float,   # months of expenses in liquid savings
        "net_cash":              float,   # total accumulated net savings
        "debt_rate":             float,   # primary APR as decimal (0.18 = 18%)
        "debt_balance":          float,
        "portfolio_value":       float,
        "expected_return":       float,   # decimal

        # Business (overlaps monthly_expenses)
        "monthly_revenue":       float,
        "gross_margin_pct":      float,   # fraction
        "net_margin_pct":        float,
        "burn_rate":             float,   # $/mo outflow when negative
        "runway_months":         float | None,
        "revenue_growth":        float,   # monthly fractional growth rate
        "cash_balance":          float,
        "marketing_budget":      float,
    },
    "macro_summary": {
        "current_fed_rate":      float,   # in PERCENT (e.g. 5.33)
        "current_inflation":     float,   # CPI YoY % (e.g. 3.2)
        "current_unemployment":  float,
        "yield_spread":          float,   # 10Y - 2Y
        "sp500_ytd_return":      float | None,
    },
    "regime":       str,   # "risk_on" | "cautious" | "risk_off" | "recession_warning"
    "risk_profile": str,   # "conservative" | "moderate" | "aggressive"
    "scenarios":    dict,  # output of scenario_engine.build_scenarios()
}
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ── Option identifiers ─────────────────────────────────────────────────────────

PERSONAL_OPTIONS: List[str] = [
    "pay_debt",
    "emergency_fund",
    "treasury_bills",
    "high_yield_savings",
    "index_etfs",
    "individual_stocks",
    "hold_cash",
]

BUSINESS_OPTIONS: List[str] = [
    "pay_debt",
    "cash_reserve",
    "treasury_bills",
    "marketing",
    "hiring",
    "inventory",
    "equipment",
    "hold_cash",
]

# ── Per-option display metadata ────────────────────────────────────────────────
# risk_level: "none" | "low" | "medium" | "high"

_OPTION_META: Dict[str, Dict[str, str]] = {
    "pay_debt": {
        "label":            "Pay Down Debt",
        "description":      "Eliminate high-rate liabilities for a guaranteed, risk-free return equal to the APR.",
        "risk_level":       "none",
        "expected_benefit": "Guaranteed return equal to your debt APR — often the best risk-adjusted move available.",
    },
    "emergency_fund": {
        "label":            "Build Emergency Fund",
        "description":      "Accumulate 3–6 months of liquid, FDIC-insured expenses.",
        "risk_level":       "none",
        "expected_benefit": "Protection against income disruption — prevents forced asset sales or expensive borrowing.",
    },
    "treasury_bills": {
        "label":            "Treasury Bills / Money Market",
        "description":      "Park surplus cash in short-duration government paper for safe, liquid yield.",
        "risk_level":       "low",
        "expected_benefit": "Government-backed yield with full liquidity — outperforms savings in high-rate environments.",
    },
    "high_yield_savings": {
        "label":            "High-Yield Savings Account",
        "description":      "Move idle cash to an FDIC-insured account earning near the Fed Funds rate.",
        "risk_level":       "none",
        "expected_benefit": "Earn near T-bill yield with zero lock-up — ideal for emergency fund and near-term cash.",
    },
    "index_etfs": {
        "label":            "Broad-Market Index ETFs",
        "description":      "Low-cost diversified equity exposure (e.g. total-market or S&P 500 ETFs).",
        "risk_level":       "medium",
        "expected_benefit": "Long-run real returns of 6–8% — best vehicle for compounding after the foundation is secure.",
    },
    "individual_stocks": {
        "label":            "Individual Stocks",
        "description":      "Targeted equity positions with higher return potential and higher idiosyncratic risk.",
        "risk_level":       "high",
        "expected_benefit": "Alpha potential in sectors you know well — only appropriate once the foundation is solid.",
    },
    "hold_cash": {
        "label":            "Hold Cash",
        "description":      "Maintain an elevated cash position and wait for better opportunities or conditions.",
        "risk_level":       "low",
        "expected_benefit": "Optionality — cash lets you act quickly when opportunities or emergencies arise.",
    },
    "cash_reserve": {
        "label":            "Build Cash Reserve",
        "description":      "Extend operational runway to at least 6 months of expenses.",
        "risk_level":       "none",
        "expected_benefit": "Survival buffer — prevents distressed fundraising or fire-sale decisions.",
    },
    "marketing": {
        "label":            "Invest in Marketing",
        "description":      "Acquire customers through paid or organic channels to grow top-line revenue.",
        "risk_level":       "medium",
        "expected_benefit": "Revenue growth — high ROI when unit economics are healthy and runway is secure.",
    },
    "hiring": {
        "label":            "Hire Talent",
        "description":      "Expand headcount to capture growth, fill capability gaps, or reduce founder dependency.",
        "risk_level":       "medium",
        "expected_benefit": "Capacity unlock — scales revenue beyond current team bandwidth.",
    },
    "inventory": {
        "label":            "Invest in Inventory",
        "description":      "Increase stock levels to meet demand and improve margins through bulk purchasing.",
        "risk_level":       "medium",
        "expected_benefit": "Improved fill rates, fewer lost sales, and potential COGS reduction via volume pricing.",
    },
    "equipment": {
        "label":            "Invest in Equipment / Capex",
        "description":      "Capital expenditure on tools, infrastructure, or technology to improve capacity or margin.",
        "risk_level":       "medium",
        "expected_benefit": "Productivity gain — reduces unit cost or increases output without proportional headcount.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tbill_pct(macro: dict) -> float:
    """Fed Funds rate as a percentage — used as T-bill proxy (e.g. 5.33 → 5.33)."""
    return float(macro.get("current_fed_rate") or 5.0)


def _tbill_decimal(macro: dict) -> float:
    """T-bill rate as a decimal for comparison with debt_rate (also decimal)."""
    return _tbill_pct(macro) / 100.0


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _regime_is_defensive(regime: str) -> bool:
    return regime in ("risk_off", "recession_warning")


# ─────────────────────────────────────────────────────────────────────────────
# Per-option scoring functions → (score: float, reasoning: str)
# ─────────────────────────────────────────────────────────────────────────────

def _score_pay_debt(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    debt_balance = float(fh.get("debt_balance", 0.0) or 0.0)
    debt_rate    = float(fh.get("debt_rate",    0.0) or 0.0)   # decimal

    if debt_balance <= 0:
        return 5.0, "No outstanding debt — this option doesn't apply."

    tbill = _tbill_decimal(macro)
    score = 30.0
    parts: List[str] = []

    # Core rule: absolute rate thresholds
    if debt_rate > 0.20:
        score += 55
        parts.append(f"debt APR {debt_rate*100:.1f}% is credit-card territory — "
                      f"paying it down is a guaranteed {debt_rate*100:.1f}% risk-free return")
    elif debt_rate > 0.15:
        score += 45
        parts.append(f"debt APR {debt_rate*100:.1f}% far exceeds expected market returns "
                      f"on a risk-adjusted basis")
    elif debt_rate > 0.10:
        score += 30
        parts.append(f"debt APR {debt_rate*100:.1f}% beats most asset classes after tax")
    elif debt_rate > tbill + 0.02:
        score += 18
        parts.append(f"debt APR {debt_rate*100:.1f}% exceeds T-bill yield "
                      f"({tbill*100:.1f}%) by more than 2 pp — debt paydown wins")
    else:
        parts.append(f"debt APR {debt_rate*100:.1f}% is close to risk-free yield — "
                     f"less urgent than other priorities")

    # Regime modifier (spec: score higher if regime is risk_off)
    if regime == "recession_warning":
        score += 12
        parts.append("recession risk makes guaranteed return of debt paydown more valuable")
    elif regime == "risk_off":
        score += 8
        parts.append("risk-off environment reinforces the value of guaranteed returns")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score), reasoning


def _score_emergency_fund(fh: dict, _macro: dict, _regime: str, _risk: str) -> Tuple[float, str]:
    ef = float(fh.get("emergency_fund_months", 0.0) or 0.0)

    # Spec-prescribed absolute scores
    if ef < 1.0:
        return 100.0, (
            f"Critical: only {ef:.1f} months of expenses in liquid savings. "
            "A single unexpected expense could force costly borrowing or asset sales. "
            "Build to 3 months before anything else."
        )
    if ef < 3.0:
        return 80.0, (
            f"Emergency fund at {ef:.1f} months — below the 3-month minimum. "
            "Topping this up is the highest-leverage, zero-risk move available."
        )
    if ef < 6.0:
        return 40.0, (
            f"Emergency fund at {ef:.1f} months — adequate but not fully buffered. "
            "Consider building toward 6 months, especially if income is variable."
        )
    return 10.0, (
        f"Emergency fund at {ef:.1f} months — healthy and above target. "
        "Other uses of capital will likely produce better returns."
    )


def _score_treasury_bills(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    tbill_pct = _tbill_pct(macro)
    ef        = float(fh.get("emergency_fund_months", 0.0) or 0.0)
    debt_rate = float(fh.get("debt_rate", 0.0) or 0.0)

    score = 20.0
    parts: List[str] = []

    # Spec: score high if T-bill > 4% AND regime is cautious or risk_off
    if tbill_pct > 5.0:
        score += 38
        parts.append(f"T-bill yield at {tbill_pct:.1f}% is exceptional — "
                     f"historically high risk-free return")
    elif tbill_pct > 4.0:
        score += 28
        parts.append(f"T-bill yield at {tbill_pct:.1f}% is above the 4% threshold "
                     f"where cash deployment becomes very attractive")
    elif tbill_pct > 3.0:
        score += 12
        parts.append(f"T-bill yield at {tbill_pct:.1f}% offers positive real return")
    else:
        parts.append(f"T-bill yield at {tbill_pct:.1f}% is low — limited appeal vs other options")

    if regime in ("cautious", "risk_off"):
        score += 20
        parts.append(f"{regime.replace('_', ' ')} regime increases appeal of safe, liquid yield")
    elif regime == "recession_warning":
        score += 12
        parts.append("defensive positioning favours government-backed liquidity")
    elif regime == "risk_on":
        score -= 8
        parts.append("risk-on conditions reduce relative appeal vs equities")

    # Foundation check
    if ef >= 3.0 and debt_rate < 0.10:
        score += 10
        parts.append("foundation (EF + low-rate debt) is solid — surplus cash can work here")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=95.0), reasoning


def _score_high_yield_savings(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    tbill_pct = _tbill_pct(macro)
    ef        = float(fh.get("emergency_fund_months", 0.0) or 0.0)

    score = 28.0
    parts: List[str] = []

    if tbill_pct > 4.0:
        score += 28
        parts.append(f"rates elevated at {tbill_pct:.1f}% — HYSA earns near Fed Funds with zero lock-up")
    elif tbill_pct > 2.5:
        score += 15
        parts.append(f"rates moderate at {tbill_pct:.1f}% — HYSA beats traditional savings")
    else:
        parts.append(f"rates low at {tbill_pct:.1f}% — HYSA advantage over checking is limited")

    if regime in ("cautious", "risk_off"):
        score += 15
        parts.append("safety-oriented environment reinforces liquid, insured cash")
    elif regime == "recession_warning":
        score += 10
        parts.append("defensive regime — FDIC-insured liquidity is valuable")

    if ef < 6.0:
        score += 15
        parts.append("still building emergency fund — HYSA is the ideal vehicle")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=90.0), reasoning


def _score_index_etfs(fh: dict, macro: dict, regime: str, risk: str) -> Tuple[float, str]:
    ef        = float(fh.get("emergency_fund_months", 0.0) or 0.0)
    debt_rate = float(fh.get("debt_rate", 0.0) or 0.0)
    sav_rate  = float(fh.get("savings_rate", 0.0) or 0.0)

    score = 30.0
    parts: List[str] = []

    # Spec: score high if risk_on AND ef >= 3 months AND no high-interest debt
    if regime == "risk_on":
        score += 30
        parts.append("risk-on macro backdrop supports equities — growth assets historically outperform")
    elif regime == "cautious":
        score += 12
        parts.append("mixed signals — index ETFs remain the core long-run allocation with balanced exposure")
    elif regime == "risk_off":
        score -= 8
        parts.append("risk-off conditions compress valuations — reduce urgency but don't exit")
    elif regime == "recession_warning":
        score -= 20
        parts.append("recession signals warrant caution — prioritise foundation before adding equity exposure")

    if ef >= 3.0:
        score += 12
        parts.append(f"emergency fund at {ef:.1f} months covers the downside — "
                     f"free to take long-term market risk")
    elif ef < 3.0:
        score -= 15
        parts.append(f"emergency fund at {ef:.1f} months is insufficient — "
                     f"build it before adding equity exposure")

    if debt_rate < 0.08:
        score += 10
        parts.append("no high-interest debt competing for this capital")
    elif debt_rate > 0.12:
        score -= 12
        parts.append(f"high-rate debt ({debt_rate*100:.1f}% APR) competes directly — paydown first")

    if sav_rate > 0.20:
        score += 8
        parts.append("strong savings rate supports consistent investment")
    elif sav_rate < 0.05:
        score -= 10
        parts.append("low savings rate limits how much can be deployed here")

    if risk == "aggressive":
        score += 5
    elif risk == "conservative":
        score -= 8

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=95.0), reasoning


def _score_individual_stocks(fh: dict, macro: dict, regime: str, risk: str) -> Tuple[float, str]:
    ef        = float(fh.get("emergency_fund_months", 0.0) or 0.0)
    debt_rate = float(fh.get("debt_rate", 0.0) or 0.0)
    sav_rate  = float(fh.get("savings_rate", 0.0) or 0.0)

    score = 12.0
    parts: List[str] = []

    if regime == "risk_on":
        score += 28
        parts.append("growth-oriented regime supports individual stock selection")
    elif regime == "cautious":
        score += 8
        parts.append("mixed environment — selective, quality-focused stock picking can work")
    elif regime == "risk_off":
        score -= 15
        parts.append("risk-off conditions historically punish high-multiple individual names")
    elif regime == "recession_warning":
        score -= 25
        parts.append("recession warning — idiosyncratic risk is hardest to manage in a downturn")

    if risk == "aggressive":
        score += 20
        parts.append("aggressive risk profile aligns with higher-concentration positions")
    elif risk == "conservative":
        score -= 15
        parts.append("conservative risk profile — broad diversification preferred over single names")

    if ef >= 6.0:
        score += 10
        parts.append(f"strong {ef:.1f}-month emergency fund supports taking on more risk")
    elif ef < 3.0:
        score -= 20
        parts.append("insufficient emergency fund — don't risk capital you may need")

    if debt_rate > 0.10:
        score -= 15
        parts.append(f"high-rate debt ({debt_rate*100:.1f}%) must be tackled first")

    if sav_rate > 0.25:
        score += 5

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=85.0), reasoning


def _score_hold_cash_personal(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    ef = float(fh.get("emergency_fund_months", 0.0) or 0.0)

    score = 18.0
    parts: List[str] = []

    # Spec: score moderate if regime is recession_warning
    if regime == "recession_warning":
        score += 42
        parts.append("recession warning — cash provides maximum optionality and "
                     "protects against forced selling")
    elif regime == "risk_off":
        score += 25
        parts.append("risk-off environment — holding cash reduces drawdown risk and "
                     "preserves purchasing power for better entry points")
    elif regime == "cautious":
        score += 15
        parts.append("uncertain conditions — some elevated cash allocation is prudent")
    elif regime == "risk_on":
        score -= 5
        parts.append("risk-on conditions mean idle cash has an opportunity cost")

    if ef < 1.0:
        score += 15
        parts.append("critically low emergency fund makes liquidity essential")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=80.0), reasoning


# ── Business scorers ──────────────────────────────────────────────────────────

def _score_cash_reserve(fh: dict, _macro: dict, _regime: str, _risk: str) -> Tuple[float, str]:
    runway = fh.get("runway_months")  # None means profitable

    if runway is None:
        return 15.0, (
            "Business is cash-flow positive — no immediate runway concern. "
            "Maintaining 3+ months of operating expenses as a buffer is still prudent."
        )
    runway = float(runway)

    # Spec-prescribed scores
    if runway < 3.0:
        return 100.0, (
            f"Critical: only {runway:.1f} months of runway. "
            "Extending cash reserves is the single highest priority — everything else is secondary."
        )
    if runway < 6.0:
        return 70.0, (
            f"Runway at {runway:.1f} months — below the 6-month safety threshold. "
            "Building this to 6 months reduces existential risk and gives room to make "
            "strategic decisions without desperation."
        )
    if runway < 9.0:
        return 40.0, (
            f"Runway at {runway:.1f} months — adequate but limited buffer for long "
            "sales cycles or unexpected downturns."
        )
    return 15.0, (
        f"Runway at {runway:.1f} months — healthy. "
        "Incremental cash beyond this earns more impact deployed in growth or debt paydown."
    )


def _score_marketing(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    margin   = float(fh.get("gross_margin_pct", 0.0) or 0.0)
    runway   = fh.get("runway_months")
    rev_grow = float(fh.get("revenue_growth", 0.0) or 0.0)   # monthly fraction

    score = 30.0
    parts: List[str] = []

    # Spec: high if margin > 20% AND runway > 6 AND regime != recession_warning
    if margin > 0.40:
        score += 30
        parts.append(f"gross margin {margin*100:.0f}% — high-margin business multiplies "
                     f"every marketing dollar into significant profit")
    elif margin > 0.20:
        score += 18
        parts.append(f"gross margin {margin*100:.0f}% supports marketing spend without "
                     f"destroying cash")
    elif margin > 0.10:
        score += 5
        parts.append(f"margin {margin*100:.0f}% is thin — marketing ROI must be tracked tightly")
    else:
        score -= 10
        parts.append(f"margin below 10% — fix unit economics before scaling marketing spend")

    if runway is None or float(runway) > 9.0:
        score += 15
        parts.append("strong runway gives room to invest in customer acquisition")
    elif runway is not None and float(runway) > 6.0:
        score += 8
        parts.append(f"runway {runway:.1f} months provides adequate buffer for marketing investment")
    elif runway is not None and float(runway) < 4.0:
        score -= 20
        parts.append(f"low runway ({runway:.1f} mo) — preserve cash before accelerating spend")

    if rev_grow > 0.10:
        score += 10
        parts.append("strong revenue momentum — marketing can accelerate an already-moving flywheel")
    elif rev_grow > 0.05:
        score += 5
        parts.append("positive revenue growth suggests marketing is working")

    if regime == "recession_warning":
        score -= 28
        parts.append("recession signals — customer acquisition costs rise, conversion falls; "
                     "preserve cash instead")
    elif regime == "risk_off":
        score -= 12
        parts.append("risk-off environment makes demand generation less efficient")
    elif regime == "risk_on":
        score += 8
        parts.append("growth-friendly macro helps demand generation")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score), reasoning


def _score_hiring(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    margin   = float(fh.get("gross_margin_pct", 0.0) or 0.0)
    runway   = fh.get("runway_months")
    rev_grow = float(fh.get("revenue_growth", 0.0) or 0.0)   # monthly

    score = 22.0
    parts: List[str] = []

    # Spec: high if rev growth > 10% (monthly) AND margin > 15% AND runway > 9
    if rev_grow > 0.10:
        score += 25
        parts.append(f"revenue growing {rev_grow*100:.1f}%/month — hiring unlocks capacity "
                     f"to capture this momentum")
    elif rev_grow > 0.05:
        score += 12
        parts.append("solid revenue growth supports incremental headcount")
    elif rev_grow < 0.0:
        score -= 15
        parts.append("revenue declining — add headcount only for critical gaps")

    if margin > 0.30:
        score += 18
        parts.append(f"gross margin {margin*100:.0f}% can absorb incremental payroll")
    elif margin > 0.15:
        score += 10
        parts.append(f"margin {margin*100:.0f}% supports measured headcount growth")
    else:
        score -= 8
        parts.append(f"tight margin ({margin*100:.0f}%) — headcount growth compresses cash quickly")

    if runway is None or float(runway) > 12.0:
        score += 20
        parts.append("long runway provides cushion for ramp-up period")
    elif runway is not None and float(runway) > 9.0:
        score += 12
        parts.append(f"runway {runway:.1f} months is sufficient for a new hire to ramp")
    elif runway is not None and float(runway) < 6.0:
        score -= 22
        parts.append(f"short runway ({runway:.1f} mo) — hiring burns cash you may need")

    if regime == "recession_warning":
        score -= 30
        parts.append("recession signals — hiring risk is highest in downturns; pause non-critical roles")
    elif regime == "risk_off":
        score -= 15
        parts.append("risk-off macro warrants caution on long-term fixed cost commitments")
    elif regime == "risk_on":
        score += 8
        parts.append("constructive macro reduces economic risk of adding headcount")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=95.0), reasoning


def _score_inventory(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    margin   = float(fh.get("gross_margin_pct", 0.0) or 0.0)
    runway   = fh.get("runway_months")
    rev_grow = float(fh.get("revenue_growth", 0.0) or 0.0)
    cash_bal = float(fh.get("cash_balance", 0.0) or 0.0)
    monthly_exp = float(fh.get("monthly_expenses", 1.0) or 1.0)

    score = 22.0
    parts: List[str] = []

    cash_months = cash_bal / monthly_exp if monthly_exp > 0 else 0.0

    if rev_grow > 0.05:
        score += 20
        parts.append("growing revenue justifies building inventory to meet demand")
    elif rev_grow < 0.0:
        score -= 10
        parts.append("declining revenue — avoid building inventory against falling demand")

    if cash_months > 6.0:
        score += 15
        parts.append("cash position strong enough to tie up capital in inventory")
    elif cash_months < 3.0:
        score -= 15
        parts.append("limited cash reserves — inventory is illiquid capital you may need")

    if margin > 0.20:
        score += 12
        parts.append(f"margin {margin*100:.0f}% means inventory investment compounds well")
    elif margin < 0.10:
        score -= 8
        parts.append("thin margins limit the ROI on bulk inventory purchasing")

    if regime == "recession_warning":
        score -= 20
        parts.append("recession risk makes inventory a liability — demand may dry up before it clears")
    elif regime == "risk_off":
        score -= 10
        parts.append("risk-off environment — preserve liquidity over inventory buildup")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=85.0), reasoning


def _score_equipment(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    margin   = float(fh.get("gross_margin_pct", 0.0) or 0.0)
    runway   = fh.get("runway_months")

    score = 18.0
    parts: List[str] = []

    if margin > 0.25:
        score += 22
        parts.append(f"healthy margin {margin*100:.0f}% — equipment ROI likely positive")
    elif margin > 0.15:
        score += 12
        parts.append(f"margin {margin*100:.0f}% can support targeted capital investment")
    else:
        score -= 5
        parts.append("thin margins reduce the return threshold for capex")

    if runway is None or float(runway) > 12.0:
        score += 18
        parts.append("strong runway allows for longer-payback capital investments")
    elif runway is not None and float(runway) > 9.0:
        score += 10
        parts.append(f"runway {runway:.1f} months is adequate for equipment ROI horizon")
    elif runway is not None and float(runway) < 6.0:
        score -= 20
        parts.append(f"short runway ({runway:.1f} mo) — avoid tying up cash in fixed assets")

    if regime == "risk_on":
        score += 10
        parts.append("growth environment supports productive capex")
    elif regime == "recession_warning":
        score -= 22
        parts.append("recession risk — defer non-critical capex; preserve liquidity")
    elif regime == "risk_off":
        score -= 10
        parts.append("risk-off conditions favour preserving cash over capex")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=85.0), reasoning


def _score_hold_cash_business(fh: dict, macro: dict, regime: str, _risk: str) -> Tuple[float, str]:
    runway = fh.get("runway_months")

    score = 18.0
    parts: List[str] = []

    if regime == "recession_warning":
        score += 45
        parts.append("recession warning — holding cash is the highest-value defensive action; "
                     "every month of additional runway buys negotiating power")
    elif regime == "risk_off":
        score += 25
        parts.append("risk-off macro — cash optionality is valuable when conditions are uncertain")
    elif regime == "cautious":
        score += 15
        parts.append("mixed signals — modest cash elevation provides insurance")
    elif regime == "risk_on":
        score -= 5
        parts.append("constructive macro makes idle cash an opportunity cost")

    if runway is not None and float(runway) < 6.0:
        score += 20
        parts.append(f"low runway ({runway:.1f} mo) — every additional month of cash is critical")

    reasoning = "; ".join(parts).capitalize() + "."
    return _clamp(score, hi=85.0), reasoning


# ── Dispatch tables ───────────────────────────────────────────────────────────

_PERSONAL_SCORERS = {
    "pay_debt":          _score_pay_debt,
    "emergency_fund":    _score_emergency_fund,
    "treasury_bills":    _score_treasury_bills,
    "high_yield_savings": _score_high_yield_savings,
    "index_etfs":        _score_index_etfs,
    "individual_stocks": _score_individual_stocks,
    "hold_cash":         _score_hold_cash_personal,
}

_BUSINESS_SCORERS = {
    "pay_debt":      _score_pay_debt,
    "cash_reserve":  _score_cash_reserve,
    "treasury_bills": _score_treasury_bills,
    "marketing":     _score_marketing,
    "hiring":        _score_hiring,
    "inventory":     _score_inventory,
    "equipment":     _score_equipment,
    "hold_cash":     _score_hold_cash_business,
}


# ─────────────────────────────────────────────────────────────────────────────
# Public: score_allocation
# ─────────────────────────────────────────────────────────────────────────────

def score_allocation(option: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score a single allocation option given the full financial + macro context.

    Parameters
    ----------
    option  : one of PERSONAL_OPTIONS or BUSINESS_OPTIONS
    context : see module docstring for schema

    Returns
    -------
    dict with keys:
        option           str
        label            str   — display name
        score            int   — 0-100
        reasoning        str   — transparent explanation of the score
        expected_benefit str   — what the user gains
        risk_level       str   — "none" | "low" | "medium" | "high"
    """
    fh      = context.get("financial_health", {})
    macro   = context.get("macro_summary",    {})
    regime  = str(context.get("regime", "cautious") or "cautious").lower()
    risk    = str(context.get("risk_profile", "moderate") or "moderate").lower()

    # Look up scorer across both tables
    scorer = _PERSONAL_SCORERS.get(option) or _BUSINESS_SCORERS.get(option)
    meta   = _OPTION_META.get(option, {})

    if scorer is None:
        return {
            "option":           option,
            "label":            meta.get("label", option),
            "score":            0,
            "reasoning":        "Unrecognised option.",
            "expected_benefit": "",
            "risk_level":       "unknown",
        }

    raw_score, reasoning = scorer(fh, macro, regime, risk)

    return {
        "option":           option,
        "label":            meta.get("label", option),
        "score":            int(round(_clamp(raw_score))),
        "reasoning":        reasoning,
        "expected_benefit": meta.get("expected_benefit", ""),
        "risk_level":       meta.get("risk_level", "medium"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: recommend
# ─────────────────────────────────────────────────────────────────────────────

def _action_sentence(rec: dict, context: dict) -> str:
    """One punchy imperative sentence for the top-recommendation string."""
    opt   = rec["option"]
    fh    = context.get("financial_health", {})
    macro = context.get("macro_summary", {})

    if opt == "pay_debt":
        rate = float(fh.get("debt_rate", 0.0) or 0.0) * 100
        return (f"Pay down your {rate:.0f}% APR debt first — "
                f"it's the highest guaranteed return available.")

    if opt == "emergency_fund":
        ef = float(fh.get("emergency_fund_months", 0.0) or 0.0)
        return (f"Build your emergency fund from {ef:.1f} months to at least 3–6 months "
                f"of expenses before anything else.")

    if opt == "treasury_bills":
        rate = _tbill_pct(macro)
        return f"Park surplus cash in Treasury bills currently yielding ~{rate:.1f}%."

    if opt == "high_yield_savings":
        rate = _tbill_pct(macro)
        return (f"Move idle cash to a high-yield savings account earning near "
                f"{rate:.1f}% — no lock-up required.")

    if opt == "index_etfs":
        return ("Invest the remainder in low-cost, broad-market index ETFs "
                "for disciplined long-run compounding.")

    if opt == "individual_stocks":
        return ("Allocate a portion to individual stocks in sectors where "
                "you have genuine insight and conviction.")

    if opt == "cash_reserve":
        runway = fh.get("runway_months")
        if runway is not None:
            return (f"Extend cash runway from {runway:.0f} to at least 6 months "
                    f"— survival buffer before any growth spend.")
        return "Build a cash reserve to cover at least 6 months of operating expenses."

    if opt == "marketing":
        return ("Invest in customer acquisition — your margins and runway "
                "support it, and growth momentum is the priority.")

    if opt == "hiring":
        return ("Hire to capture current revenue momentum before the "
                "window narrows.")

    if opt == "inventory":
        return ("Build inventory levels to meet demand and capture "
                "volume-pricing benefits on COGS.")

    if opt == "equipment":
        return ("Invest in equipment that directly reduces unit cost or "
                "expands production capacity.")

    if opt == "hold_cash":
        return ("Hold elevated cash — current conditions reward "
                "optionality over deployment.")

    return rec.get("reasoning", "")


def recommend(context: Dict[str, Any], mode: str = "personal") -> Dict[str, Any]:
    """
    Score all options for the given mode and return a ranked recommendation list.

    Parameters
    ----------
    context : see module docstring
    mode    : "personal" | "business"

    Returns
    -------
    dict with:
        ranked               list[dict]  — all options sorted by score desc
        top_recommendation   str         — 2-3 sentence action plan
    """
    options = PERSONAL_OPTIONS if mode == "personal" else BUSINESS_OPTIONS

    ranked: List[Dict[str, Any]] = []
    for opt in options:
        ranked.append(score_allocation(opt, context))

    ranked.sort(key=lambda r: r["score"], reverse=True)

    # Build the top-recommendation string from the top 3 meaningful options
    top3 = [r for r in ranked[:3] if r["score"] >= 25]
    sentences = [_action_sentence(r, context) for r in top3]
    top_recommendation = " ".join(sentences) if sentences else ranked[0]["reasoning"]

    return {
        "ranked":             ranked,
        "top_recommendation": top_recommendation,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: explain_recommendation
# ─────────────────────────────────────────────────────────────────────────────

def explain_recommendation(ranked_list: List[Dict], context: Dict[str, Any]) -> str:
    """
    Generate a multi-paragraph prose explanation of the recommendation logic.

    Parameters
    ----------
    ranked_list : output of recommend()["ranked"]
    context     : full context dict

    Returns
    -------
    str — markdown-formatted prose (3-4 paragraphs)
    """
    if not ranked_list:
        return "Insufficient data to generate a recommendation."

    fh     = context.get("financial_health", {})
    macro  = context.get("macro_summary",    {})
    regime = str(context.get("regime", "cautious") or "cautious").lower()
    mode   = str(context.get("mode",   "personal") or "personal").lower()

    inflation   = float(macro.get("current_inflation", 3.0)    or 3.0)
    fed_rate    = float(macro.get("current_fed_rate",  5.0)    or 5.0)
    unem        = float(macro.get("current_unemployment", 4.0) or 4.0)
    spread      = float(macro.get("yield_spread", 0.5)         or 0.5)
    regime_name = regime.replace("_", " ").title()

    top    = ranked_list[0]
    second = ranked_list[1] if len(ranked_list) > 1 else {}

    # ── Para 1: macro context ─────────────────────────────────────────────────
    yield_note = ""
    if spread < 0:
        yield_note = (f" The yield curve is inverted by {abs(spread):.2f}pp "
                      f"(10Y–2Y), which has historically preceded recessions.")
    elif spread < 0.5:
        yield_note = f" The yield curve is nearly flat (spread {spread:.2f}pp), signalling slowing growth."

    para1 = (
        f"The current macro regime is **{regime_name}** — inflation is running at "
        f"{inflation:.1f}%, the Federal Funds rate is at {fed_rate:.1f}%, and "
        f"unemployment stands at {unem:.1f}%.{yield_note} "
    )

    if regime == "risk_on":
        para1 += (
            "This is a growth-supportive backdrop: inflation is contained, employment "
            "is healthy, and the yield curve is normal. Risk assets have historically "
            "delivered their best absolute and relative returns in this environment."
        )
    elif regime == "cautious":
        para1 += (
            "The picture is mixed — some indicators are healthy but others signal "
            "uncertainty. A balanced approach that maintains liquidity while keeping "
            "measured growth exposure is appropriate."
        )
    elif regime == "risk_off":
        para1 += (
            "High inflation and a still-tight Fed make this a challenging environment "
            "for bonds (prices fall as yields rise) and for high-multiple equities. "
            "Guaranteed returns — debt paydown, T-bills — become unusually attractive "
            "relative to market risk."
        )
    else:  # recession_warning
        para1 += (
            "Leading indicators are flashing caution: the yield curve inversion and/or "
            "rising unemployment are two of the most reliable recession precursors. "
            "Capital preservation and liquidity take priority until conditions stabilise."
        )

    # ── Para 2: personal or business financial context ────────────────────────
    if mode == "personal":
        debt_rate  = float(fh.get("debt_rate",             0.0) or 0.0) * 100
        ef_months  = float(fh.get("emergency_fund_months", 0.0) or 0.0)
        sav_rate   = float(fh.get("savings_rate",          0.0) or 0.0) * 100
        port_val   = float(fh.get("portfolio_value",       0.0) or 0.0)
        real_return = fed_rate - inflation

        para2 = (
            f"Your personal financial profile shows a savings rate of "
            f"**{sav_rate:.1f}%** and an emergency fund of **{ef_months:.1f} months**"
        )
        if debt_rate > 0:
            para2 += f", with outstanding debt at **{debt_rate:.1f}% APR**"
        if port_val > 0:
            para2 += f", and an investment portfolio worth ${port_val:,.0f}"
        para2 += f". The current real rate of return on cash is **{real_return:+.1f}%** "
        para2 += ("(real returns positive — savers are rewarded)." if real_return > 0
                  else "(negative real return — inflation is eroding cash holdings).")

    else:  # business
        margin      = float(fh.get("gross_margin_pct",  0.0) or 0.0) * 100
        net_margin  = float(fh.get("net_margin_pct",    0.0) or 0.0) * 100
        runway      = fh.get("runway_months")
        rev_grow    = float(fh.get("revenue_growth",    0.0) or 0.0) * 100  # monthly %

        para2 = (
            f"Your business has a gross margin of **{margin:.1f}%** "
            f"and net margin of **{net_margin:.1f}%**"
        )
        if runway is not None:
            para2 += f", with **{runway:.1f} months of runway**"
        else:
            para2 += " and is currently cash-flow positive"
        if rev_grow != 0:
            para2 += f". Revenue is growing at **{rev_grow:.1f}%/month**"
        para2 += "."

    # ── Para 3: top recommendation logic ─────────────────────────────────────
    top_label  = top.get("label",     top.get("option", ""))
    top_score  = top.get("score",     0)
    top_reason = top.get("reasoning", "")
    top_benefit = top.get("expected_benefit", "")

    para3 = (
        f"Given this context, the highest-value use of your next dollar is "
        f"**{top_label}** (priority score: **{top_score}/100**). "
        f"{top_reason}"
    )
    if top_benefit:
        para3 += f" The expected benefit: {top_benefit}"

    # ── Para 4: second priority and T-bill note ───────────────────────────────
    parts4: List[str] = []

    if second:
        s_label  = second.get("label",  second.get("option", ""))
        s_score  = second.get("score",  0)
        s_reason = second.get("reasoning", "")
        if s_score >= 30:
            parts4.append(
                f"Once {top_label} is addressed, **{s_label}** ({s_score}/100) "
                f"becomes the next priority. {s_reason}"
            )

    if fed_rate > 4.0 and top.get("option") not in ("treasury_bills", "high_yield_savings"):
        parts4.append(
            f"As a note: with the Fed Funds rate at {fed_rate:.1f}%, any cash held "
            f"beyond your immediate priorities should be in T-bills or a high-yield "
            f"savings account rather than a standard checking account."
        )

    para4 = " ".join(parts4)

    paragraphs = [para1, para2, para3]
    if para4:
        paragraphs.append(para4)

    return "\n\n".join(paragraphs)

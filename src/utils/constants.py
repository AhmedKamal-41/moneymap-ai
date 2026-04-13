"""
constants.py
------------
Cost assumptions, thresholds, regime definitions, and allocation tier configs.
"""
from __future__ import annotations

# ── Regime detection thresholds ───────────────────────────────────────────────
REGIME_THRESHOLDS = {
    "high_inflation": 4.0,       # CPI YoY % above this = high inflation
    "high_rates": 4.0,           # Fed Funds % above this = restrictive
    "low_unemployment": 4.5,     # U-3 % below this = tight labour market
    "yield_curve_inversion": 0,  # 10Y-2Y spread below this = inverted
}

# ── Historical stress scenarios ───────────────────────────────────────────────
# income_shock and expense_shock are fractional changes (e.g. -0.30 = -30%)
HISTORICAL_SCENARIOS = {
    "2008 Financial Crisis": {
        "income_shock": -0.35,
        "expense_shock": 0.15,
        "duration_months": 18,
        "description": "Severe recession; equity markets fell ~50%, unemployment peaked at 10%.",
    },
    "2020 COVID-19 Shock": {
        "income_shock": -0.25,
        "expense_shock": 0.10,
        "duration_months": 6,
        "description": "Sharp but short shock; rapid V-shaped recovery in many sectors.",
    },
    "2000 Dot-com Bust": {
        "income_shock": -0.20,
        "expense_shock": 0.05,
        "duration_months": 24,
        "description": "Prolonged tech-sector correction; S&P 500 fell ~50% over ~2.5 years.",
    },
    "1970s Stagflation": {
        "income_shock": -0.10,
        "expense_shock": 0.30,
        "duration_months": 36,
        "description": "High inflation eroded purchasing power; wage growth lagged price rises.",
    },
    "2022 Rate Hike Cycle": {
        "income_shock": -0.05,
        "expense_shock": 0.20,
        "duration_months": 12,
        "description": "Aggressive Fed rate hikes crushed bond/equity valuations; CPI peaked ~9%.",
    },
}

# ── Allocation tiers ──────────────────────────────────────────────────────────
# Each tier has: id, label, description, base_score, max_fraction, flags
ALLOCATION_TIERS = [
    {
        "id": "emergency_fund",
        "label": "Emergency Fund",
        "description": (
            "Build 3–6 months of expenses in liquid, FDIC-insured savings. "
            "This is your financial immune system — prioritise it before anything else."
        ),
        "base_score": 85,
        "max_fraction": 0.50,
        "defensive": True,
        "growth": False,
    },
    {
        "id": "high_interest_debt",
        "label": "Pay Off High-Interest Debt",
        "description": (
            "Any debt above ~7% APR (e.g. credit cards, personal loans) is a guaranteed "
            "negative return. Eliminating it beats almost every investment on a risk-adjusted basis."
        ),
        "base_score": 90,
        "max_fraction": 0.40,
        "defensive": True,
        "growth": False,
    },
    {
        "id": "tax_advantaged",
        "label": "Max Tax-Advantaged Accounts",
        "description": (
            "Contribute to 401(k) (especially up to employer match), IRA, or HSA. "
            "Tax-free or tax-deferred compounding is a powerful long-term edge."
        ),
        "base_score": 75,
        "max_fraction": 0.25,
        "defensive": False,
        "growth": True,
    },
    {
        "id": "index_investing",
        "label": "Broad Market Index Funds",
        "description": (
            "Low-cost index funds (e.g. total market ETFs) offer diversified growth exposure "
            "with minimal fees and behavioural drag."
        ),
        "base_score": 65,
        "max_fraction": 0.30,
        "defensive": False,
        "growth": True,
    },
    {
        "id": "real_assets",
        "label": "Real Assets / Real Estate",
        "description": (
            "Real estate or REIT exposure provides inflation hedging and income diversification. "
            "Particularly attractive during high-inflation regimes."
        ),
        "base_score": 55,
        "max_fraction": 0.20,
        "defensive": True,
        "growth": True,
    },
    {
        "id": "liquidity_buffer",
        "label": "Extra Liquidity Buffer",
        "description": (
            "Beyond the emergency fund, holding 1–2 months of additional liquid reserves "
            "gives you optionality for deals, investments, or unexpected costs."
        ),
        "base_score": 50,
        "max_fraction": 0.15,
        "defensive": True,
        "growth": False,
    },
    {
        "id": "skills_education",
        "label": "Skills & Education",
        "description": (
            "Investing in your human capital — courses, certifications, or tools — "
            "often yields the highest personal ROI when income growth is the binding constraint."
        ),
        "base_score": 60,
        "max_fraction": 0.10,
        "defensive": False,
        "growth": True,
    },
]

# ── Common personal spending categories ──────────────────────────────────────
PERSONAL_CATEGORIES = [
    "Housing", "Food & Dining", "Transport", "Healthcare",
    "Utilities", "Entertainment", "Shopping", "Travel",
    "Insurance", "Savings/Investment", "Education", "Other",
]

# ── Business cash flow types ──────────────────────────────────────────────────
BUSINESS_FLOW_TYPES = [
    "Revenue", "COGS", "Payroll", "Rent", "Marketing",
    "Software/SaaS", "Professional Services", "Taxes",
    "Capex", "Loan Repayment", "Other Expense",
]

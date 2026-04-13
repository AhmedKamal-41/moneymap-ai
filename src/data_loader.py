"""
data_loader.py
--------------
CSV parsing, validation, enrichment, and summary computation
for personal and business modes.

Public API
----------
parse_personal_csv(source)  -> pd.DataFrame
parse_business_csv(source)  -> pd.DataFrame
compute_summary(df, mode)   -> dict

Legacy helpers (used by existing pages/tests)
---------------------------------------------
load_csv(source)                    -> pd.DataFrame
validate_dataframe(df, mode)        -> list[str]
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, List

import pandas as pd

log = logging.getLogger(__name__)

# ── Personal category taxonomy ────────────────────────────────────────────────
PERSONAL_CATEGORIES = frozenset({
    "rent", "groceries", "dining", "transport", "subscriptions",
    "shopping", "utilities", "income", "savings", "debt_payment",
    "healthcare", "other",
})

# Ordered rules: (canonical_category, [keywords_to_match_in_description_or_category])
_PERSONAL_RULES: list[tuple[str, list[str]]] = [
    ("income", [
        "salary", "payroll", "direct deposit", "freelance", "consulting",
        "bonus", "side income", "deposit", "payment received", "transfer in",
        "reimbursement", "refund", "cashback", "dividends", "interest earned",
    ]),
    ("savings", [
        "transfer to savings", "savings transfer", "401k", "403b",
        "roth ira", "traditional ira", "investment", "brokerage deposit",
        "fidelity", "vanguard", "schwab", "wealthfront", "betterment", "acorns",
    ]),
    ("debt_payment", [
        "student loan", "navient", "sallie mae", "nelnet", "great lakes",
        "loan payment", "credit card payment", "cc payment", "amex payment",
        "chase payment", "citi payment", "discover payment", "debt payment",
        "mortgage payment", "car loan", "auto loan",
    ]),
    ("rent", [
        "rent", "landlord", "apartment", "hoa fee", "property management",
    ]),
    ("groceries", [
        "trader joe", "whole foods", "safeway", "kroger", "walmart supercenter",
        "costco", "aldi", "publix", "heb", "wegmans", "stop & shop",
        "food lion", "market basket", "sprouts", "grocery", "supermarket",
        "fresh market", "meijer",
    ]),
    ("dining", [
        "restaurant", "starbucks", "dunkin", "panera", "chipotle", "subway",
        "mcdonald", "burger king", "wendy", "taco bell", "pizza", "sushi",
        "ramen", "doordash", "uber eats", "grubhub", "seamless", "postmates",
        "cafe", "coffee shop", "diner", "bistro", "grill", "bar ", "tavern",
        "barbeque", "bbq", "thai", "indian", "chinese food", "italian",
        "brunch", "lunch spot", "food truck", "smoothie",
    ]),
    ("transport", [
        "uber", "lyft", "shell", "exxon", "chevron", "bp ", "citgo",
        "gas station", "gasoline", "fuel", "parking", "metro", "transit",
        "mta ", "bart ", "cta ", "septa", "wmata", "toll", "car wash",
        "jiffy lube", "auto repair", "tire", "zipcar", "bird scooter",
    ]),
    ("subscriptions", [
        "netflix", "hulu", "disney+", "hbo max", "paramount+", "peacock",
        "apple tv", "youtube premium", "spotify", "apple music", "tidal",
        "amazon prime", "audible", "kindle unlimited", "gym", "planet fitness",
        "la fitness", "equinox", "classpass", "icloud", "google one",
        "dropbox", "adobe", "microsoft 365", "nytimes", "wsj subscription",
    ]),
    ("utilities", [
        "electric", "pg&e", "con ed", "consolidated edison", "duke energy",
        "xfinity", "comcast", "spectrum internet", "at&t internet", "fios",
        "frontier", "cox ", "verizon wireless", "t-mobile", "at&t wireless",
        "boost mobile", "cricket wireless", "water bill", "gas bill", "sewage",
        "internet bill", "phone bill", "utility",
    ]),
    ("healthcare", [
        "pharmacy", "cvs", "walgreens", "rite aid", "doctor", "physician",
        "dentist", "orthodontist", "optometrist", "eye doctor", "hospital",
        "urgent care", "medical", "copay", "co-pay", "prescription",
        "health insurance", "dental insurance", "vision insurance",
    ]),
    ("shopping", [
        "amazon", "ebay", "etsy", "nordstrom", "macy", "bloomingdale",
        "best buy", "apple store", "home depot", "lowe", "ikea", "wayfair",
        "target", "bed bath", "tj maxx", "marshalls", "ross ", "gap ",
        "old navy", "h&m", "zara", "nike", "adidas", "clothing", "apparel",
        "shoes", "bookstore", "barnes & noble",
    ]),
]

# Normalise incoming category strings that don't match canonical names
_PERSONAL_CATEGORY_ALIASES: dict[str, str] = {
    "rent": "rent", "mortgage": "rent", "housing": "rent",
    "food & dining": "dining", "food": "dining", "restaurants": "dining",
    "fast food": "dining", "coffee": "dining",
    "groceries": "groceries", "grocery": "groceries",
    "transport": "transport", "transportation": "transport",
    "gas & fuel": "transport", "auto": "transport",
    "ride share": "transport", "rideshare": "transport",
    "subscriptions": "subscriptions", "entertainment": "subscriptions",
    "streaming": "subscriptions",
    "utilities": "utilities", "utility": "utilities",
    "income": "income", "salary": "income", "wages": "income",
    "savings": "savings", "investment": "savings",
    "debt_payment": "debt_payment", "debt": "debt_payment",
    "loan": "debt_payment", "credit card": "debt_payment",
    "shopping": "shopping",
    "healthcare": "healthcare", "health": "healthcare", "medical": "healthcare",
    "travel": "other", "vacation": "other",
}

# ── Business category taxonomy ────────────────────────────────────────────────
BUSINESS_CATEGORIES = frozenset({
    "revenue", "cogs", "payroll", "marketing", "rent",
    "software", "inventory", "debt_payment", "other",
})

_BUSINESS_CATEGORY_ALIASES: dict[str, str] = {
    "revenue": "revenue", "sales": "revenue", "subscription": "revenue",
    "saas revenue": "revenue", "services": "revenue", "consulting": "revenue",
    "product sales": "revenue",
    "cogs": "cogs", "cost of goods": "cogs", "cost of revenue": "cogs",
    "hosting": "cogs",
    "payroll": "payroll", "salary": "payroll", "wages": "payroll",
    "benefits": "payroll", "contractors": "payroll",
    "marketing": "marketing", "advertising": "marketing", "ads": "marketing",
    "pr": "marketing", "content": "marketing",
    "rent": "rent", "office": "rent", "lease": "rent",
    "software": "software", "saas": "software", "tools": "software",
    "licenses": "software", "subscriptions": "software",
    "inventory": "inventory", "supplies": "inventory", "materials": "inventory",
    "debt_payment": "debt_payment", "loan": "debt_payment",
    "professional services": "other", "legal": "other", "accounting": "other",
    "taxes": "other", "insurance": "other", "travel": "other", "capex": "other",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_source(source) -> pd.DataFrame:
    """Read CSV from file path, bytes, BytesIO, StringIO, or Streamlit UploadedFile."""
    if isinstance(source, str):
        return pd.read_csv(source)
    if isinstance(source, pd.DataFrame):
        return source.copy()
    if hasattr(source, "read"):
        content = source.read()
    else:
        content = source
    if isinstance(content, bytes):
        return pd.read_csv(io.BytesIO(content))
    return pd.read_csv(io.StringIO(content))


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [
        re.sub(r"\s+", "_", c.strip().lower()) for c in df.columns
    ]
    return df


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    if "date" not in df.columns:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    bad = df["date"].isna().sum()
    if bad:
        log.warning("%d row(s) have unparseable dates — dropping.", bad)
    return df.dropna(subset=["date"])


def _parse_amount(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce amount to float, stripping currency symbols and commas."""
    if "amount" not in df.columns:
        return df
    if not pd.api.types.is_numeric_dtype(df["amount"]):
        df["amount"] = (
            df["amount"]
            .astype(str)
            .str.replace(r"[$,\s]", "", regex=True)
            .str.replace(r"\((\d+\.?\d*)\)", r"-\1", regex=True)  # (123.45) → -123.45
        )
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df.dropna(subset=["amount"])


def _categorise_personal_row(row: pd.Series) -> str:
    """Return canonical personal category for a single row."""
    amount = row.get("amount", 0)
    desc   = str(row.get("description", "")).lower()
    cat    = str(row.get("category", "")).lower().strip()

    # Positive amounts are income unless they look like transfers/savings
    if amount > 0:
        for kw in ("savings", "transfer", "investment", "brokerage"):
            if kw in desc or kw in cat:
                return "savings"
        return "income"

    # Already a canonical category?
    if cat in PERSONAL_CATEGORIES:
        return cat

    # Alias map
    for key, canonical in _PERSONAL_CATEGORY_ALIASES.items():
        if key in cat:
            return canonical

    # Keyword scan on description (ordered — first match wins)
    for canonical, keywords in _PERSONAL_RULES:
        if any(kw in desc for kw in keywords):
            return canonical

    return "other"


def _categorise_business_row(row: pd.Series) -> str:
    """Return canonical business category for a single row."""
    cat = str(row.get("category", "")).lower().strip()
    typ = str(row.get("type", "")).lower().strip()

    if cat in BUSINESS_CATEGORIES:
        return cat
    for key, canonical in _BUSINESS_CATEGORY_ALIASES.items():
        if key in cat or key in typ:
            return canonical
    return "other"


def _add_personal_time_cols(df: pd.DataFrame) -> pd.DataFrame:
    df["month"]       = df["date"].dt.to_period("M")
    df["week"]        = df["date"].dt.isocalendar().week.astype(int)
    df["day_of_week"] = df["date"].dt.day_name()
    return df


# ── Public: parse functions ───────────────────────────────────────────────────

def parse_personal_csv(source) -> pd.DataFrame:
    """
    Parse a personal-finance CSV and return a clean, enriched DataFrame.

    Required columns: date, amount
    Optional columns: category, description

    Returns columns:
        date (datetime64), amount (float), category (str), description (str),
        month (Period[M]), week (int), day_of_week (str)

    - Amounts are signed: positive = income, negative = expense.
    - If category is absent or unrecognised it is inferred from the description
      using keyword matching (see _PERSONAL_RULES).
    """
    df = _read_source(source)
    df = _normalise_columns(df)

    # Ensure required columns exist
    missing = {"date", "amount"} - set(df.columns)
    if missing:
        raise ValueError(f"Personal CSV is missing required columns: {', '.join(sorted(missing))}")

    df = _parse_dates(df)
    df = _parse_amount(df)

    if len(df) == 0:
        raise ValueError("No valid rows found after parsing dates and amounts.")

    # Ensure optional columns exist so row-level operations are safe
    if "description" not in df.columns:
        df["description"] = ""
    if "category" not in df.columns:
        df["category"] = ""

    df["description"] = df["description"].fillna("").astype(str)
    df["category"]    = df["category"].fillna("").astype(str)

    # Infer / normalise category
    df["category"] = df.apply(_categorise_personal_row, axis=1)

    # Time enrichment
    df = _add_personal_time_cols(df)

    # Canonical column order
    cols = ["date", "month", "week", "day_of_week", "amount", "category", "description"]
    extra = [c for c in df.columns if c not in cols]
    return df[cols + extra].reset_index(drop=True)


def parse_business_csv(source) -> pd.DataFrame:
    """
    Parse a business cash-flow CSV and return a clean DataFrame.

    Required columns: date, amount
    Optional columns: type (revenue/expense), category, description

    Returns columns:
        date (datetime64), month (Period[M]), type (str), category (str),
        amount (float), description (str)

    - Amounts use sign convention: revenue positive, expenses negative.
      If a row has type='expense' and a positive amount, the amount is negated.
    """
    df = _read_source(source)
    df = _normalise_columns(df)

    missing = {"date", "amount"} - set(df.columns)
    if missing:
        raise ValueError(f"Business CSV is missing required columns: {', '.join(sorted(missing))}")

    df = _parse_dates(df)
    df = _parse_amount(df)

    if len(df) == 0:
        raise ValueError("No valid rows found after parsing dates and amounts.")

    if "description" not in df.columns:
        df["description"] = ""
    if "category" not in df.columns:
        df["category"] = ""
    if "type" not in df.columns:
        # Infer from sign
        df["type"] = df["amount"].apply(lambda x: "revenue" if x > 0 else "expense")

    df["description"] = df["description"].fillna("").astype(str)
    df["category"]    = df["category"].fillna("").astype(str)
    df["type"]        = df["type"].str.strip().str.lower().fillna("expense")

    # Normalise category
    df["category"] = df.apply(_categorise_business_row, axis=1)

    # Enforce sign convention: expenses must be negative
    expense_mask = df["type"] == "expense"
    df.loc[expense_mask & (df["amount"] > 0), "amount"] *= -1
    revenue_mask = df["type"] == "revenue"
    df.loc[revenue_mask & (df["amount"] < 0), "amount"] *= -1

    df["month"] = df["date"].dt.to_period("M")

    cols = ["date", "month", "type", "category", "amount", "description"]
    extra = [c for c in df.columns if c not in cols]
    return df[cols + extra].reset_index(drop=True)


# ── Public: summary ───────────────────────────────────────────────────────────

def compute_summary(df: pd.DataFrame, mode: str = "personal") -> Dict[str, Any]:
    """
    Compute high-level financial metrics from a parsed DataFrame.

    Parameters
    ----------
    df   : output of parse_personal_csv or parse_business_csv
    mode : "personal" or "business"

    Returns
    -------
    dict  — keys depend on mode; see below.

    Personal keys
    -------------
    total_income, total_spending, savings_rate, net_savings,
    monthly_income_avg, monthly_burn, top_spending_categories,
    debt_payments_total, subscription_total, n_months

    Business keys
    -------------
    total_revenue, total_expenses, net_income, gross_margin,
    burn_rate, runway_months, top_expense_categories,
    monthly_revenue_avg, monthly_expense_avg, n_months
    """
    if mode == "personal":
        return _summary_personal(df)
    elif mode == "business":
        return _summary_business(df)
    else:
        raise ValueError(f"Unknown mode '{mode}'. Choose 'personal' or 'business'.")


def _summary_personal(df: pd.DataFrame) -> Dict[str, Any]:
    income_df  = df[df["amount"] > 0]
    expense_df = df[df["amount"] < 0]

    total_income   = float(income_df["amount"].sum())
    total_spending = float(expense_df["amount"].abs().sum())
    net_savings    = total_income - total_spending
    savings_rate   = (net_savings / total_income) if total_income > 0 else 0.0

    n_months = max(df["month"].nunique(), 1)
    monthly_income_avg = total_income   / n_months
    monthly_burn       = total_spending / n_months

    # Category breakdown (expenses only, sorted by total spend desc)
    cat_totals = (
        expense_df.groupby("category")["amount"]
        .apply(lambda s: round(s.abs().sum(), 2))
        .sort_values(ascending=False)
    )
    top_spending_categories = cat_totals.head(5).to_dict()

    debt_payments_total = float(
        expense_df[expense_df["category"] == "debt_payment"]["amount"].abs().sum()
    )
    subscription_total = float(
        expense_df[expense_df["category"] == "subscriptions"]["amount"].abs().sum()
    )

    # Monthly cash flow series
    monthly = df.groupby("month")["amount"].sum().reset_index()
    monthly.columns = ["month", "net_flow"]
    monthly["month"] = monthly["month"].astype(str)

    return {
        "total_income":              round(total_income, 2),
        "total_spending":            round(total_spending, 2),
        "net_savings":               round(net_savings, 2),
        "savings_rate":              round(savings_rate, 4),
        "monthly_income_avg":        round(monthly_income_avg, 2),
        "monthly_burn":              round(monthly_burn, 2),
        "top_spending_categories":   top_spending_categories,
        "debt_payments_total":       round(debt_payments_total, 2),
        "subscription_total":        round(subscription_total, 2),
        "n_months":                  n_months,
        "monthly_cashflow":          monthly,
        "category_totals":           cat_totals.to_dict(),
    }


def _summary_business(df: pd.DataFrame) -> Dict[str, Any]:
    revenue_df = df[df["amount"] > 0]
    expense_df = df[df["amount"] < 0]

    total_revenue  = float(revenue_df["amount"].sum())
    total_expenses = float(expense_df["amount"].abs().sum())
    net_income     = total_revenue - total_expenses

    # Gross margin: (revenue - cogs) / revenue
    cogs = float(
        expense_df[expense_df["category"] == "cogs"]["amount"].abs().sum()
    )
    gross_profit = total_revenue - cogs
    gross_margin = (gross_profit / total_revenue) if total_revenue > 0 else 0.0

    n_months = max(df["month"].nunique(), 1)
    monthly_revenue_avg = total_revenue  / n_months
    monthly_expense_avg = total_expenses / n_months
    burn_rate           = monthly_expense_avg

    # Cash estimate: use net income as a proxy for current cash
    # (real usage would pass in a starting balance)
    runway_months = (net_income / burn_rate) if burn_rate > 0 else float("inf")

    cat_totals = (
        expense_df.groupby("category")["amount"]
        .apply(lambda s: round(s.abs().sum(), 2))
        .sort_values(ascending=False)
    )
    top_expense_categories = cat_totals.head(5).to_dict()

    monthly = df.groupby("month")["amount"].sum().reset_index()
    monthly.columns = ["month", "net_flow"]
    monthly["month"] = monthly["month"].astype(str)

    return {
        "total_revenue":          round(total_revenue, 2),
        "total_expenses":         round(total_expenses, 2),
        "net_income":             round(net_income, 2),
        "gross_margin":           round(gross_margin, 4),
        "gross_profit":           round(gross_profit, 2),
        "burn_rate":              round(burn_rate, 2),
        "runway_months":          round(runway_months, 1),
        "monthly_revenue_avg":    round(monthly_revenue_avg, 2),
        "monthly_expense_avg":    round(monthly_expense_avg, 2),
        "top_expense_categories": top_expense_categories,
        "n_months":               n_months,
        "monthly_cashflow":       monthly,
        "category_totals":        cat_totals.to_dict(),
    }


# ── Legacy helpers (used by existing pages and tests) ─────────────────────────

def load_csv(source) -> pd.DataFrame:
    """
    Load a CSV from a file path, bytes, or Streamlit UploadedFile.
    Returns a DataFrame with a parsed 'date' column (datetime64).
    """
    df = _read_source(source)
    df = _normalise_columns(df)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def validate_dataframe(df: pd.DataFrame, mode: str = "personal") -> List[str]:
    """
    Validate a loaded DataFrame against the expected schema.
    Returns a list of human-readable issue strings (empty = all clear).
    """
    issues: List[str] = []

    required = (
        {"date", "amount", "category"} if mode == "personal"
        else {"date", "amount", "type"}
    )
    missing = required - set(df.columns)
    if missing:
        issues.append(f"Missing required columns: {', '.join(sorted(missing))}")

    if "date" in df.columns and df["date"].isna().any():
        n = df["date"].isna().sum()
        issues.append(f"{n} row(s) have unparseable dates and will be excluded.")

    if "amount" in df.columns:
        if not pd.api.types.is_numeric_dtype(df["amount"]):
            issues.append("Column 'amount' is not numeric — check for currency symbols or text.")
        elif (df["amount"] == 0).all():
            issues.append("All 'amount' values are zero — the file may be empty or malformed.")

    if len(df) == 0:
        issues.append("The file contains no data rows.")

    return issues

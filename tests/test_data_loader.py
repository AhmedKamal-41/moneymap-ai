"""
Tests for src/data_loader.py
Covers parse_personal_csv, parse_business_csv, and compute_summary.
"""
import io

import pandas as pd
import pytest

from src.data_loader import (
    BUSINESS_CATEGORIES,
    PERSONAL_CATEGORIES,
    compute_summary,
    load_csv,
    parse_business_csv,
    parse_personal_csv,
    validate_dataframe,
)

# ── Shared CSV fixtures ───────────────────────────────────────────────────────

PERSONAL_FULL_CSV = """\
date,category,amount,description
2024-01-01,income,5500.00,Direct Deposit Payroll
2024-01-01,rent,-1800.00,Monthly Rent
2024-01-02,subscriptions,-15.99,Netflix
2024-01-02,subscriptions,-9.99,Spotify Premium
2024-01-03,utilities,-65.00,Xfinity Internet
2024-01-05,groceries,-87.32,Trader Joes Weekly Run
2024-01-07,dining,-13.50,Starbucks
2024-01-10,dining,-45.80,Chipotle dinner
2024-01-12,transport,-54.20,Shell Gas Station Fill Up
2024-01-15,debt_payment,-385.00,Navient Student Loan
2024-01-18,shopping,-89.99,Amazon Purchase
2024-01-20,healthcare,-35.00,CVS Pharmacy Prescription
2024-01-28,debt_payment,-300.00,Chase CC Payment
2024-02-01,income,5525.00,Direct Deposit Payroll
2024-02-01,rent,-1800.00,Monthly Rent
2024-02-05,groceries,-92.14,Whole Foods
2024-02-10,dining,-55.40,Sushi Nozomi dinner
2024-02-15,debt_payment,-385.00,Navient Student Loan
2024-02-20,transport,-48.60,Chevron Fill Up
2024-02-28,debt_payment,-280.00,Chase CC Payment
"""

BUSINESS_FULL_CSV = """\
date,type,category,amount,description
2024-01-01,revenue,revenue,42000.00,SaaS Subscription Revenue
2024-01-05,revenue,revenue,8500.00,Professional Services Revenue
2024-01-01,expense,payroll,13000.00,Engineering Team Payroll
2024-01-01,expense,payroll,4000.00,Sales Team Payroll
2024-01-01,expense,rent,3200.00,Office Lease
2024-01-03,expense,cogs,5200.00,Cloud Hosting Costs
2024-01-15,expense,software,1800.00,AWS Cloud Infrastructure
2024-01-20,expense,marketing,2800.00,Google Ads Campaign
2024-01-28,expense,other,650.00,CPA Bookkeeping
2024-02-01,revenue,revenue,44000.00,SaaS Subscription Revenue
2024-02-05,revenue,revenue,7500.00,Professional Services Revenue
2024-02-01,expense,payroll,13000.00,Engineering Team Payroll
2024-02-01,expense,payroll,4000.00,Sales Team Payroll
2024-02-01,expense,rent,3200.00,Office Lease
2024-02-03,expense,cogs,5500.00,Cloud Hosting and Infra
2024-02-15,expense,software,2000.00,Tooling Licenses
2024-02-20,expense,marketing,3200.00,LinkedIn Ads
2024-02-28,expense,other,650.00,CPA Bookkeeping
"""

MISSING_COL_CSV = "date,amount\n2024-01-05,100\n"
BAD_DATE_CSV    = "date,amount,category\nnot-a-date,100.0,income\n2024-01-05,200.0,income\n"


def _src(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode())


# ── load_csv / validate_dataframe (legacy helpers) ────────────────────────────

class TestValidateDataframeEmpty:
    def test_empty_frame_reports_issues(self):
        df = pd.DataFrame(columns=["date", "amount", "category"])
        issues = validate_dataframe(df, "personal")
        assert any("no data rows" in msg.lower() for msg in issues)


class TestLoadCSV:
    def test_loads_personal_csv(self):
        df = load_csv(_src(PERSONAL_FULL_CSV))
        assert len(df) > 0
        assert "date" in df.columns
        assert pd.api.types.is_datetime64_any_dtype(df["date"])

    def test_column_names_normalised(self):
        csv = "Date , Amount , Category\n2024-01-01,100.0,Food\n"
        df = load_csv(_src(csv))
        assert "date" in df.columns
        assert "amount" in df.columns
        assert "category" in df.columns

    def test_bad_dates_become_nat(self):
        df = load_csv(_src(BAD_DATE_CSV))
        assert df["date"].isna().sum() == 1


class TestValidateDataframe:
    def test_valid_personal(self):
        df = load_csv(_src(PERSONAL_FULL_CSV))
        issues = validate_dataframe(df, mode="personal")
        assert issues == []

    def test_missing_category_personal(self):
        df = load_csv(_src(MISSING_COL_CSV))
        issues = validate_dataframe(df, mode="personal")
        assert any("category" in i for i in issues)

    def test_bad_dates_flagged(self):
        df = load_csv(_src(BAD_DATE_CSV))
        issues = validate_dataframe(df, mode="personal")
        assert any("date" in i.lower() for i in issues)

    def test_empty_df(self):
        df = pd.DataFrame(columns=["date", "amount", "category"])
        issues = validate_dataframe(df, mode="personal")
        assert any("no data" in i.lower() for i in issues)


# ── parse_personal_csv ────────────────────────────────────────────────────────

class TestParsePersonalCSV:
    def test_returns_dataframe(self):
        df = parse_personal_csv(_src(PERSONAL_FULL_CSV))
        assert isinstance(df, pd.DataFrame)

    def test_required_columns_present(self):
        df = parse_personal_csv(_src(PERSONAL_FULL_CSV))
        for col in ("date", "month", "week", "day_of_week", "amount", "category"):
            assert col in df.columns, f"Missing column: {col}"

    def test_dates_are_datetime(self):
        df = parse_personal_csv(_src(PERSONAL_FULL_CSV))
        assert pd.api.types.is_datetime64_any_dtype(df["date"])

    def test_amounts_are_numeric(self):
        df = parse_personal_csv(_src(PERSONAL_FULL_CSV))
        assert pd.api.types.is_numeric_dtype(df["amount"])

    def test_all_categories_canonical(self):
        df = parse_personal_csv(_src(PERSONAL_FULL_CSV))
        unknown = set(df["category"].unique()) - PERSONAL_CATEGORIES
        assert unknown == set(), f"Non-canonical categories: {unknown}"

    def test_positive_amounts_are_income(self):
        df = parse_personal_csv(_src(PERSONAL_FULL_CSV))
        assert (df[df["amount"] > 0]["category"] == "income").all()

    def test_auto_categorise_by_description(self):
        csv = "date,amount,description\n2024-01-05,-87.32,Trader Joes Weekly Run\n"
        df = parse_personal_csv(_src(csv))
        assert df["category"].iloc[0] == "groceries"

    def test_missing_category_column_ok(self):
        csv = "date,amount,description\n2024-01-01,5500,Employer Payroll\n2024-01-02,-85,Starbucks\n"
        df = parse_personal_csv(_src(csv))
        assert len(df) == 2
        assert "category" in df.columns

    def test_currency_symbols_stripped(self):
        csv = 'date,amount,category\n2024-01-01,"$5500.00",income\n'
        df = parse_personal_csv(_src(csv))
        assert df["amount"].iloc[0] == pytest.approx(5500.0, rel=1e-3)

    def test_bad_date_rows_dropped(self):
        csv = "date,amount,category\nnot-a-date,-50.00,dining\n2024-01-05,-50.00,dining\n"
        df = parse_personal_csv(_src(csv))
        assert len(df) == 1

    def test_raises_on_missing_required_columns(self):
        csv = "category,description\ndining,Lunch\n"
        with pytest.raises(ValueError, match="required columns"):
            parse_personal_csv(_src(csv))

    def test_missing_date_column_raises(self):
        csv = "amount,category\n-50.00,dining\n"
        with pytest.raises(ValueError, match="required columns"):
            parse_personal_csv(_src(csv))

    def test_empty_file_raises(self):
        csv = "date,amount,category\n"
        with pytest.raises(ValueError):
            parse_personal_csv(_src(csv))


# ── parse_business_csv ────────────────────────────────────────────────────────

class TestParseBusinessCSV:
    def test_returns_dataframe(self):
        df = parse_business_csv(_src(BUSINESS_FULL_CSV))
        assert isinstance(df, pd.DataFrame)

    def test_required_columns_present(self):
        df = parse_business_csv(_src(BUSINESS_FULL_CSV))
        for col in ("date", "month", "type", "category", "amount"):
            assert col in df.columns

    def test_expense_amounts_are_negative(self):
        df = parse_business_csv(_src(BUSINESS_FULL_CSV))
        expenses = df[df["type"] == "expense"]
        assert (expenses["amount"] < 0).all()

    def test_revenue_amounts_are_positive(self):
        df = parse_business_csv(_src(BUSINESS_FULL_CSV))
        revenue = df[df["type"] == "revenue"]
        assert (revenue["amount"] > 0).all()

    def test_all_categories_canonical(self):
        df = parse_business_csv(_src(BUSINESS_FULL_CSV))
        unknown = set(df["category"].unique()) - BUSINESS_CATEGORIES
        assert unknown == set(), f"Non-canonical categories: {unknown}"

    def test_positive_expense_coerced_negative(self):
        csv = "date,type,category,amount,description\n2024-01-01,expense,payroll,13000.00,Payroll\n"
        df = parse_business_csv(_src(csv))
        assert df["amount"].iloc[0] == pytest.approx(-13000.0)

    def test_type_inferred_from_sign_when_missing(self):
        csv = "date,amount\n2024-01-01,5000.00\n2024-01-02,-3000.00\n"
        df = parse_business_csv(_src(csv))
        assert df[df["amount"] > 0]["type"].iloc[0] == "revenue"
        assert df[df["amount"] < 0]["type"].iloc[0] == "expense"

    def test_month_column_added(self):
        df = parse_business_csv(_src(BUSINESS_FULL_CSV))
        assert "month" in df.columns

    def test_raises_on_missing_required_columns(self):
        csv = "category,description\nrevenue,Sales\n"
        with pytest.raises(ValueError, match="required columns"):
            parse_business_csv(_src(csv))

    def test_empty_file_raises(self):
        csv = "date,amount\n"
        with pytest.raises(ValueError):
            parse_business_csv(_src(csv))


# ── compute_summary — personal ────────────────────────────────────────────────

class TestComputeSummaryPersonal:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.df      = parse_personal_csv(_src(PERSONAL_FULL_CSV))
        self.summary = compute_summary(self.df, "personal")

    def test_returns_dict(self):
        assert isinstance(self.summary, dict)

    def test_required_keys(self):
        for key in (
            "total_income", "total_spending", "savings_rate", "net_savings",
            "monthly_income_avg", "monthly_burn", "top_spending_categories",
            "debt_payments_total", "subscription_total", "n_months",
        ):
            assert key in self.summary, f"Missing key: {key}"

    def test_n_months_is_two(self):
        # CSV spans Jan and Feb 2024
        assert self.summary["n_months"] == 2

    def test_total_income_correct(self):
        # Jan: 5500, Feb: 5525 = 11025
        assert self.summary["total_income"] == pytest.approx(11025.0, rel=1e-4)

    def test_savings_rate_between_0_and_1(self):
        assert 0.0 <= self.summary["savings_rate"] <= 1.0

    def test_savings_rate_is_positive(self):
        # income > spending in this dataset
        assert self.summary["savings_rate"] > 0.0

    def test_monthly_income_avg_correct(self):
        # 11025 / 2 = 5512.50
        assert self.summary["monthly_income_avg"] == pytest.approx(5512.50, rel=1e-4)

    def test_monthly_burn_is_positive(self):
        assert self.summary["monthly_burn"] > 0.0

    def test_debt_payments_total_is_positive(self):
        # Multiple debt_payment entries exist
        assert self.summary["debt_payments_total"] > 0.0

    def test_subscription_total_is_positive(self):
        # Netflix + Spotify entries
        assert self.summary["subscription_total"] > 0.0

    def test_top_spending_is_dict_max_5(self):
        assert isinstance(self.summary["top_spending_categories"], dict)
        assert len(self.summary["top_spending_categories"]) <= 5

    def test_top_spending_sorted_descending(self):
        cats = list(self.summary["top_spending_categories"].values())
        assert cats == sorted(cats, reverse=True)


# ── compute_summary — business ────────────────────────────────────────────────

class TestComputeSummaryBusiness:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.df      = parse_business_csv(_src(BUSINESS_FULL_CSV))
        self.summary = compute_summary(self.df, "business")

    def test_required_keys(self):
        for key in (
            "total_revenue", "total_expenses", "gross_margin",
            "burn_rate", "runway_months", "top_expense_categories", "n_months",
        ):
            assert key in self.summary, f"Missing key: {key}"

    def test_n_months_is_two(self):
        assert self.summary["n_months"] == 2

    def test_total_revenue_correct(self):
        # Jan: 42000+8500=50500, Feb: 44000+7500=51500 → 102000
        assert self.summary["total_revenue"] == pytest.approx(102000.0, rel=1e-4)

    def test_gross_margin_between_0_and_1(self):
        assert 0.0 <= self.summary["gross_margin"] <= 1.0

    def test_gross_margin_high_saas(self):
        # COGS is only cloud hosting; revenue is SaaS + services → margin > 0.80
        assert self.summary["gross_margin"] > 0.80

    def test_burn_rate_is_positive(self):
        assert self.summary["burn_rate"] > 0.0

    def test_burn_rate_is_monthly_avg(self):
        # total_expenses / n_months
        expected = self.summary["total_expenses"] / self.summary["n_months"]
        assert self.summary["burn_rate"] == pytest.approx(expected, rel=1e-6)

    def test_monthly_revenue_avg_correct(self):
        # 102000 / 2 = 51000
        assert self.summary["monthly_revenue_avg"] == pytest.approx(51000.0, rel=1e-4)

    def test_top_expense_categories_is_dict(self):
        assert isinstance(self.summary["top_expense_categories"], dict)

    def test_top_expense_includes_payroll(self):
        # Payroll is the biggest expense
        assert "payroll" in self.summary["top_expense_categories"]

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            compute_summary(self.df, "unknown")

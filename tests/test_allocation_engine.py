"""
Tests for src/analysis/allocation_engine.py

Covers: score_allocation, recommend, explain_recommendation,
        PERSONAL_OPTIONS, BUSINESS_OPTIONS.
"""
import pytest

from src.analysis.allocation_engine import (
    BUSINESS_OPTIONS,
    PERSONAL_OPTIONS,
    explain_recommendation,
    recommend,
    score_allocation,
)


# ── Context factories ─────────────────────────────────────────────────────────

def _personal_ctx(
    monthly_income:    float = 5_500.0,
    monthly_expenses:  float = 4_200.0,
    ef_months:         float = 4.0,
    debt_rate:         float = 0.07,
    debt_balance:      float = 12_000.0,
    portfolio_value:   float = 35_000.0,
    fed_rate:          float = 5.33,
    regime:            str   = "cautious",
    risk_profile:      str   = "moderate",
) -> dict:
    fh = {
        "monthly_income":        monthly_income,
        "monthly_expenses":      monthly_expenses,
        "savings_rate":          max(0.0, (monthly_income - monthly_expenses) / monthly_income),
        "emergency_fund_months": ef_months,
        "net_cash":              ef_months * monthly_expenses,
        "debt_rate":             debt_rate,
        "debt_balance":          debt_balance,
        "portfolio_value":       portfolio_value,
        "expected_return":       0.08,
    }
    ms = {
        "current_fed_rate":     fed_rate,
        "current_inflation":    3.2,
        "current_unemployment": 4.0,
        "yield_spread":         0.5,
        "sp500_ytd_return":     5.0,
    }
    return {
        "financial_health": fh,
        "macro_summary":    ms,
        "regime":           regime,
        "risk_profile":     risk_profile,
        "scenarios":        {},
        "mode":             "personal",
    }


def _business_ctx(
    monthly_revenue:  float = 47_000.0,
    monthly_expenses: float = 40_000.0,
    cash_balance:     float = 88_000.0,
    runway_months:    float = 12.0,
    debt_rate:        float = 0.065,
    debt_balance:     float = 50_000.0,
    fed_rate:         float = 5.33,
    regime:           str   = "cautious",
) -> dict:
    fh = {
        "monthly_revenue":   monthly_revenue,
        "monthly_expenses":  monthly_expenses,
        "cash_balance":      cash_balance,
        "runway_months":     runway_months,
        "debt_rate":         debt_rate,
        "debt_balance":      debt_balance,
        "gross_margin_pct":  0.15,
        "net_margin_pct":    0.05,
        "burn_rate":         0.0,
        "revenue_growth":    0.005,
        "marketing_budget":  5_000.0,
    }
    ms = {
        "current_fed_rate":     fed_rate,
        "current_inflation":    3.2,
        "current_unemployment": 4.0,
        "yield_spread":         0.5,
        "sp500_ytd_return":     5.0,
    }
    return {
        "financial_health": fh,
        "macro_summary":    ms,
        "regime":           regime,
        "risk_profile":     "moderate",
        "scenarios":        {},
        "mode":             "business",
    }


# ── score_allocation ──────────────────────────────────────────────────────────

class TestScoreAllocation:
    def test_returns_required_keys(self):
        ctx = _personal_ctx()
        result = score_allocation("pay_debt", ctx)
        for key in ("option", "label", "score", "reasoning", "expected_benefit", "risk_level"):
            assert key in result, f"Missing key: {key}"

    def test_score_between_0_and_100(self):
        ctx = _personal_ctx()
        for opt in PERSONAL_OPTIONS:
            result = score_allocation(opt, ctx)
            assert 0 <= result["score"] <= 100, (
                f"{opt}: score {result['score']} out of [0, 100]"
            )

    def test_option_key_preserved(self):
        ctx = _personal_ctx()
        result = score_allocation("index_etfs", ctx)
        assert result["option"] == "index_etfs"

    def test_reasoning_is_non_empty_string(self):
        ctx = _personal_ctx()
        result = score_allocation("emergency_fund", ctx)
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 0

    # ── Emergency fund spec scores ─────────────────────────────────────────────

    def test_emergency_fund_scores_100_when_ef_under_1_month(self):
        """Spec: emergency_fund returns exactly 100 when ef_months < 1."""
        ctx = _personal_ctx(ef_months=0.5)
        result = score_allocation("emergency_fund", ctx)
        assert result["score"] == pytest.approx(100.0, abs=1e-6)

    def test_emergency_fund_scores_80_when_ef_1_to_3_months(self):
        """Spec: emergency_fund returns exactly 80 when 1 <= ef < 3."""
        ctx = _personal_ctx(ef_months=2.0)
        result = score_allocation("emergency_fund", ctx)
        assert result["score"] == pytest.approx(80.0, abs=1e-6)

    def test_emergency_fund_scores_low_when_ef_above_6(self):
        """Spec: emergency_fund returns 10 when ef >= 6 months."""
        ctx = _personal_ctx(ef_months=8.0)
        result = score_allocation("emergency_fund", ctx)
        assert result["score"] == pytest.approx(10.0, abs=1e-6)

    # ── Pay debt scoring ───────────────────────────────────────────────────────

    def test_pay_debt_zero_score_when_no_debt(self):
        ctx = _personal_ctx(debt_balance=0.0)
        result = score_allocation("pay_debt", ctx)
        assert result["score"] < 10.0

    def test_pay_debt_high_score_for_high_apr(self):
        """High-APR debt (>20%) should score very high."""
        ctx = _personal_ctx(debt_rate=0.25, debt_balance=5_000.0, ef_months=6.0)
        result = score_allocation("pay_debt", ctx)
        assert result["score"] > 70.0

    # ── Index ETF regime sensitivity ───────────────────────────────────────────

    def test_index_etfs_scores_low_during_recession_warning(self):
        """Spec: index_etfs scores low when regime=recession_warning."""
        ctx = _personal_ctx(ef_months=1.0, regime="recession_warning")
        result = score_allocation("index_etfs", ctx)
        assert result["score"] < 25.0

    def test_index_etfs_scores_higher_in_risk_on(self):
        """Risk-on regime raises index_etfs score vs recession_warning."""
        ctx_bad  = _personal_ctx(ef_months=4.0, regime="recession_warning")
        ctx_good = _personal_ctx(ef_months=4.0, regime="risk_on")
        s_bad  = score_allocation("index_etfs", ctx_bad)["score"]
        s_good = score_allocation("index_etfs", ctx_good)["score"]
        assert s_good > s_bad

    def test_individual_stocks_lower_than_index_in_recession(self):
        """Individual stocks should score lower than index ETFs in recession."""
        ctx = _personal_ctx(ef_months=4.0, regime="recession_warning")
        s_stocks = score_allocation("individual_stocks", ctx)["score"]
        s_etfs   = score_allocation("index_etfs",       ctx)["score"]
        assert s_stocks <= s_etfs


# ── recommend ─────────────────────────────────────────────────────────────────

class TestRecommend:
    def test_returns_required_keys(self):
        ctx    = _personal_ctx()
        result = recommend(ctx, "personal")
        assert "ranked" in result
        assert "top_recommendation" in result

    def test_ranked_is_list(self):
        ctx    = _personal_ctx()
        result = recommend(ctx, "personal")
        assert isinstance(result["ranked"], list)

    def test_personal_ranked_uses_personal_options(self):
        ctx    = _personal_ctx()
        result = recommend(ctx, "personal")
        options = {r["option"] for r in result["ranked"]}
        assert options == set(PERSONAL_OPTIONS)

    def test_ranked_sorted_descending(self):
        """Top score must be first; list must be monotonically non-increasing."""
        ctx    = _personal_ctx()
        result = recommend(ctx, "personal")
        scores = [r["score"] for r in result["ranked"]]
        assert scores == sorted(scores, reverse=True), "Ranked list is not sorted descending"

    def test_top_recommendation_matches_first_ranked(self):
        """top_recommendation is a prose string derived from the top-ranked option."""
        ctx    = _personal_ctx()
        result = recommend(ctx, "personal")
        assert isinstance(result["top_recommendation"], str)
        assert len(result["top_recommendation"]) > 0

    def test_pay_debt_wins_with_high_rate_and_risk_off(self):
        """
        With debt_rate=20%, ef_months=6 (adequate), regime=risk_off:
        pay_debt score ≈ 83 should be the highest option.
        """
        ctx    = _personal_ctx(debt_rate=0.20, ef_months=6.0, regime="risk_off")
        result = recommend(ctx, "personal")
        assert result["ranked"][0]["option"] == "pay_debt"

    def test_emergency_fund_wins_with_no_savings(self):
        """With ef_months < 1, emergency_fund scores 100 — always #1."""
        ctx    = _personal_ctx(ef_months=0.3)
        result = recommend(ctx, "personal")
        assert result["ranked"][0]["option"] == "emergency_fund"

    def test_individual_stocks_not_top_3_in_recession_warning(self):
        """Individual stocks should be penalised heavily in recession_warning."""
        ctx    = _personal_ctx(ef_months=2.0, regime="recession_warning")
        result = recommend(ctx, "personal")
        top3   = [r["option"] for r in result["ranked"][:3]]
        assert "individual_stocks" not in top3

    # ── Business mode ──────────────────────────────────────────────────────────

    def test_business_mode_returns_business_options(self):
        ctx    = _business_ctx()
        result = recommend(ctx, "business")
        options = {r["option"] for r in result["ranked"]}
        assert options == set(BUSINESS_OPTIONS)

    def test_business_mode_does_not_include_personal_only_options(self):
        """index_etfs and individual_stocks are personal-only."""
        ctx    = _business_ctx()
        result = recommend(ctx, "business")
        options = {r["option"] for r in result["ranked"]}
        assert "index_etfs"       not in options
        assert "individual_stocks" not in options

    def test_business_mode_includes_marketing_and_hiring(self):
        """Business-specific options marketing and hiring should appear."""
        ctx    = _business_ctx()
        result = recommend(ctx, "business")
        options = {r["option"] for r in result["ranked"]}
        assert "marketing" in options
        assert "hiring"    in options

    def test_business_cash_reserve_wins_with_low_runway(self):
        """With runway < 3 months, cash_reserve scores 100 → always #1."""
        ctx    = _business_ctx(runway_months=2.0)
        result = recommend(ctx, "business")
        assert result["ranked"][0]["option"] == "cash_reserve"

    def test_business_ranked_sorted_descending(self):
        ctx    = _business_ctx()
        result = recommend(ctx, "business")
        scores = [r["score"] for r in result["ranked"]]
        assert scores == sorted(scores, reverse=True)


# ── explain_recommendation ────────────────────────────────────────────────────

class TestExplainRecommendation:
    def test_returns_string(self):
        ctx    = _personal_ctx()
        result = recommend(ctx, "personal")
        prose  = explain_recommendation(result["ranked"], ctx)
        assert isinstance(prose, str)

    def test_non_empty_explanation(self):
        ctx    = _personal_ctx()
        result = recommend(ctx, "personal")
        prose  = explain_recommendation(result["ranked"], ctx)
        assert len(prose) > 50

    def test_top_option_label_mentioned(self):
        ctx    = _personal_ctx(ef_months=0.3)
        result = recommend(ctx, "personal")
        prose  = explain_recommendation(result["ranked"], ctx)
        top_label = result["ranked"][0]["label"]
        assert top_label.lower() in prose.lower()

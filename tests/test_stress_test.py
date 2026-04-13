"""
Tests for src/analysis/stress_test.py

Covers: SCENARIOS dict, run_stress_test, run_all_stress_tests,
        resilience_score.
"""
import pytest

from src.analysis.stress_test import (
    SCENARIOS,
    resilience_score,
    run_all_stress_tests,
    run_stress_test,
)


# ── Shared financial health fixtures ─────────────────────────────────────────

def _fh_healthy():
    """Well-capitalised personal finances — survives all shocks easily."""
    return {
        "monthly_income":   20_000.0,
        "monthly_expenses":  3_000.0,
        "net_cash":        500_000.0,
        "debt_rate":            0.04,
        "debt_balance":         0.0,
    }


def _fh_tight():
    """Finances that cannot survive any shock (negative net, zero cash)."""
    return {
        "monthly_income":   2_000.0,
        "monthly_expenses": 6_000.0,   # net = -4 000/mo
        "net_cash":             0.0,
        "debt_rate":            0.05,
        "debt_balance":         0.0,
    }


def _fh_moderate():
    """Typical personal situation — moderate income and savings."""
    return {
        "monthly_income":   5_500.0,
        "monthly_expenses": 4_200.0,
        "net_cash":        18_000.0,
        "debt_rate":            0.07,
        "debt_balance":    12_000.0,
    }


# ── SCENARIOS dict ────────────────────────────────────────────────────────────

class TestScenariosDict:
    def test_five_scenarios_defined(self):
        assert len(SCENARIOS) == 5

    def test_required_keys_per_scenario(self):
        for name, sc in SCENARIOS.items():
            for key in ("label", "equity_shock", "duration_months", "description"):
                assert key in sc, f"Scenario '{name}' missing key '{key}'"

    def test_equity_shocks_are_negative(self):
        for name, sc in SCENARIOS.items():
            assert sc["equity_shock"] <= 0.0, (
                f"Scenario '{name}' has non-negative equity_shock: {sc['equity_shock']}"
            )

    def test_2008_equity_shock_is_minus_50pct(self):
        assert SCENARIOS["2008_financial_crisis"]["equity_shock"] == pytest.approx(-0.50)

    def test_covid_equity_shock_is_minus_34pct(self):
        assert SCENARIOS["covid_2020"]["equity_shock"] == pytest.approx(-0.34)

    def test_inflation_shock_equity_shock(self):
        assert SCENARIOS["inflation_shock"]["equity_shock"] == pytest.approx(-0.20)

    def test_mild_recession_equity_shock(self):
        assert SCENARIOS["mild_recession"]["equity_shock"] == pytest.approx(-0.15)

    def test_rate_spike_equity_shock(self):
        assert SCENARIOS["rate_spike"]["equity_shock"] == pytest.approx(-0.10)

    def test_duration_months_positive(self):
        for name, sc in SCENARIOS.items():
            assert sc["duration_months"] > 0, f"'{name}' duration must be > 0"


# ── run_stress_test ───────────────────────────────────────────────────────────

class TestRunStressTest:
    def test_returns_dict_with_required_keys(self):
        r = run_stress_test("2008_financial_crisis", _fh_moderate(), 35_000, "personal")
        for key in (
            "scenario_name", "label", "portfolio_impact_pct",
            "portfolio_impact_dollars", "new_monthly_net", "severity_score",
            "cash_path_base", "cash_path_stressed", "floor_breached",
        ):
            assert key in r, f"Missing key: {key}"

    def test_2008_reduces_portfolio_by_50pct(self):
        """2008 crisis equity_shock = -0.50 → portfolio_impact_pct == -0.50."""
        r = run_stress_test("2008_financial_crisis", _fh_moderate(), 50_000, "personal")
        assert r["portfolio_impact_pct"] == pytest.approx(-0.50, rel=1e-6)

    def test_2008_portfolio_dollar_impact_correct(self):
        pv = 100_000.0
        r  = run_stress_test("2008_financial_crisis", _fh_moderate(), pv, "personal")
        assert r["portfolio_impact_dollars"] == pytest.approx(-50_000.0, rel=1e-6)
        assert r["new_portfolio_value"]      == pytest.approx( 50_000.0, rel=1e-6)

    def test_portfolio_dict_coerced_like_scalar(self):
        r = run_stress_test(
            "2008_financial_crisis",
            _fh_moderate(),
            {"portfolio_value": 100_000.0},
            "personal",
        )
        assert r["new_portfolio_value"] == pytest.approx(50_000.0, rel=1e-6)

    def test_covid_equity_shock_correct(self):
        """COVID scenario equity_shock = -0.34."""
        r = run_stress_test("covid_2020", _fh_moderate(), 50_000, "personal")
        assert r["portfolio_impact_pct"] == pytest.approx(-0.34, rel=1e-6)

    def test_cash_path_length_25(self):
        """Paths span months 0-24 inclusive = 25 elements."""
        r = run_stress_test("mild_recession", _fh_moderate(), 35_000, "personal")
        assert len(r["cash_path_base"])     == 25
        assert len(r["cash_path_stressed"]) == 25

    def test_cash_path_starts_at_net_cash(self):
        """Month 0 of the cash path is the starting cash balance."""
        fh = _fh_moderate()
        r  = run_stress_test("mild_recession", fh, 0, "personal")
        assert r["cash_path_base"][0]     == pytest.approx(fh["net_cash"], rel=1e-6)
        assert r["cash_path_stressed"][0] == pytest.approx(fh["net_cash"], rel=1e-6)

    def test_severity_score_between_0_and_100(self):
        for name in SCENARIOS:
            r = run_stress_test(name, _fh_moderate(), 35_000, "personal")
            assert 0.0 <= r["severity_score"] <= 100.0, (
                f"'{name}' severity_score out of range: {r['severity_score']}"
            )

    def test_2008_most_severe_of_all(self):
        """2008 crisis should be the most severe scenario for typical finances."""
        scores = {
            name: run_stress_test(name, _fh_moderate(), 35_000, "personal")["severity_score"]
            for name in SCENARIOS
        }
        assert max(scores, key=scores.get) == "2008_financial_crisis"

    def test_unknown_scenario_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown scenario"):
            run_stress_test("nonexistent_scenario_xyz", _fh_moderate(), 0, "personal")

    def test_healthy_finances_positive_net_all_scenarios(self):
        """Even after shock, healthy finances keep a positive monthly net."""
        for name in SCENARIOS:
            r = run_stress_test(name, _fh_healthy(), 0, "personal")
            # With income=20k and expenses=3k, even a 10% unemployment spike
            # yields shocked_income ≥ 16k >> expenses
            assert r["new_monthly_net"] > 0, f"'{name}': expected positive net"

    def test_business_mode_uses_revenue_key(self):
        fh_biz = {
            "monthly_revenue":  47_000.0,
            "monthly_expenses": 40_000.0,
            "cash_balance":     88_000.0,
            "debt_rate":             0.07,
            "debt_balance":     50_000.0,
        }
        r = run_stress_test("mild_recession", fh_biz, 80_000, "business")
        assert r["base_monthly_income"] == pytest.approx(47_000.0, rel=1e-4)

    def test_floor_breached_false_for_healthy_finances(self):
        """Wealthy user with large cash buffer should not breach the floor."""
        r = run_stress_test("mild_recession", _fh_healthy(), 0, "personal")
        assert r["floor_breached"] is False

    def test_floor_breached_true_for_tight_finances_2008(self):
        """User with zero cash and negative monthly net will breach the floor."""
        r = run_stress_test("2008_financial_crisis", _fh_tight(), 0, "personal")
        assert r["floor_breached"] is True


# ── run_all_stress_tests ──────────────────────────────────────────────────────

class TestRunAllStressTests:
    def test_accepts_portfolio_dict(self):
        results = run_all_stress_tests(_fh_moderate(), {"value": 35_000}, "personal")
        assert len(results) == len(SCENARIOS)
        assert all("severity_score" in r for r in results)

    def test_returns_five_results(self):
        results = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        assert len(results) == len(SCENARIOS)

    def test_results_sorted_by_severity_descending(self):
        results = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        scores  = [r["severity_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_2008_is_first(self):
        """2008 financial crisis is always the most severe scenario."""
        results = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        assert results[0]["scenario_name"] == "2008_financial_crisis"

    def test_each_result_has_cash_paths(self):
        results = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        for r in results:
            assert len(r["cash_path_stressed"]) == 25
            assert len(r["cash_path_base"])     == 25

    def test_all_scenario_names_present(self):
        results = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        names   = {r["scenario_name"] for r in results}
        assert names == set(SCENARIOS.keys())


# ── resilience_score ──────────────────────────────────────────────────────────

class TestResilienceScore:
    def test_returns_required_keys(self):
        results = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        resil   = resilience_score(results)
        for key in ("score", "label", "color", "survived", "total", "detail"):
            assert key in resil

    def test_score_100_when_all_scenarios_survived(self):
        """
        Very healthy finances: monthly net >> 0, huge cash buffer.
        All 5 scenarios must have cash_path_stressed[12] > 0.
        """
        results = run_all_stress_tests(_fh_healthy(), 0, "personal")
        resil   = resilience_score(results)
        assert resil["score"]    == 100
        assert resil["survived"] == 5
        assert resil["total"]    == 5
        assert resil["label"]    == "Strong"

    def test_score_0_when_no_scenarios_survived(self):
        """
        Financially distressed: income << expenses, zero cash.
        All 5 scenarios must deplete cash by month 12.
        """
        results = run_all_stress_tests(_fh_tight(), 0, "personal")
        resil   = resilience_score(results)
        assert resil["score"]    == 0
        assert resil["survived"] == 0
        assert resil["total"]    == 5

    def test_empty_results_returns_zero_score(self):
        resil = resilience_score([])
        assert resil["score"] == 0
        assert resil["total"] == 0

    def test_partial_survival_score_between_0_and_100(self):
        """Moderate finances may survive some scenarios but not others."""
        # Use finances tight enough to fail worst case but survive mildest
        fh_mid = {
            "monthly_income":   4_000.0,
            "monthly_expenses": 4_200.0,   # net = -200
            "net_cash":        50_000.0,   # large buffer keeps cash > 0 for mild shocks
            "debt_rate":            0.05,
            "debt_balance":         0.0,
        }
        results = run_all_stress_tests(fh_mid, 0, "personal")
        resil   = resilience_score(results)
        assert 0 <= resil["score"] <= 100

    def test_survived_plus_failed_equals_total(self):
        results = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        resil   = resilience_score(results)
        failed  = resil["total"] - resil["survived"]
        assert resil["survived"] + failed == resil["total"]

    def test_score_equals_survived_over_total_pct(self):
        results  = run_all_stress_tests(_fh_moderate(), 35_000, "personal")
        resil    = resilience_score(results)
        expected = round(resil["survived"] / resil["total"] * 100)
        assert resil["score"] == expected

    def test_label_vulnerable_when_score_0(self):
        results = run_all_stress_tests(_fh_tight(), 0, "personal")
        resil   = resilience_score(results)
        assert resil["label"] == "Vulnerable"

    def test_label_strong_when_score_100(self):
        results = run_all_stress_tests(_fh_healthy(), 0, "personal")
        resil   = resilience_score(results)
        assert resil["label"] == "Strong"

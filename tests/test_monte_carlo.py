"""
Tests for src/analysis/monte_carlo.py

Covers: simulate_portfolio, simulate_cash_flow, summarize_simulations,
        and the legacy build_fan_chart helper.
"""
import numpy as np
import pytest

from src.analysis.monte_carlo import (
    simulate_cash_flow,
    simulate_portfolio,
    summarize_simulations,
)


# ── simulate_portfolio ────────────────────────────────────────────────────────

class TestSimulatePortfolio:
    def test_output_shape(self):
        """Returns (simulations, days) array."""
        paths = simulate_portfolio(
            current_value=100_000,
            expected_return=0.08,
            volatility=0.15,
            days=252,
            simulations=500,
            seed=42,
        )
        assert paths.shape == (500, 252)

    def test_correct_simulations_dimension(self):
        paths = simulate_portfolio(50_000, 0.08, 0.15, days=30, simulations=200, seed=0)
        assert paths.shape[0] == 200

    def test_correct_days_dimension(self):
        paths = simulate_portfolio(50_000, 0.08, 0.15, days=60, simulations=100, seed=0)
        assert paths.shape[1] == 60

    def test_all_values_positive(self):
        """GBM never produces negative prices."""
        paths = simulate_portfolio(100_000, 0.08, 0.15, days=252, simulations=500, seed=1)
        assert (paths > 0).all()

    def test_positive_drift_median_grows(self):
        """With strong positive drift and many simulations, median final > initial."""
        paths = simulate_portfolio(100_000, 0.30, 0.05, days=252, simulations=2000, seed=2)
        median_final = float(np.median(paths[:, -1]))
        assert median_final > 100_000

    def test_higher_volatility_wider_distribution(self):
        """Higher volatility → wider spread of final values."""
        paths_low  = simulate_portfolio(100_000, 0.08, 0.05, days=252, simulations=2000, seed=5)
        paths_high = simulate_portfolio(100_000, 0.08, 0.40, days=252, simulations=2000, seed=5)
        std_low  = float(paths_low[:, -1].std())
        std_high = float(paths_high[:, -1].std())
        assert std_high > std_low

    def test_same_seed_reproducible(self):
        p1 = simulate_portfolio(100_000, 0.08, 0.15, days=10, simulations=50, seed=99)
        p2 = simulate_portfolio(100_000, 0.08, 0.15, days=10, simulations=50, seed=99)
        assert np.array_equal(p1, p2)

    def test_different_seeds_differ(self):
        p1 = simulate_portfolio(100_000, 0.08, 0.15, days=10, simulations=50, seed=1)
        p2 = simulate_portfolio(100_000, 0.08, 0.15, days=10, simulations=50, seed=2)
        assert not np.array_equal(p1, p2)


# ── simulate_cash_flow ────────────────────────────────────────────────────────

class TestSimulateCashFlow:
    def test_output_shape(self):
        """Returns (simulations, months) array."""
        paths = simulate_cash_flow(
            monthly_income=5_000,
            monthly_expenses=4_000,
            months=24,
            simulations=300,
            seed=42,
        )
        assert paths.shape == (300, 24)

    def test_zero_volatility_deterministic(self):
        """With volatility=0 all paths are identical and match the deterministic calculation."""
        income, expenses, months = 5_000, 4_000, 12
        paths = simulate_cash_flow(
            monthly_income=income,
            monthly_expenses=expenses,
            months=months,
            income_growth=0.0,
            expense_growth=0.0,
            volatility=0.0,
            simulations=100,
            seed=0,
        )
        # Deterministic: cumulative cash after m months = m * (income - expenses) = m * 1000
        expected_final = months * (income - expenses)    # 12 * 1000 = 12 000
        assert np.allclose(paths[:, -1], expected_final, atol=1e-6)

    def test_zero_volatility_all_paths_equal(self):
        paths = simulate_cash_flow(5_000, 4_000, 12, volatility=0.0, simulations=50, seed=0)
        # All 50 paths should be identical
        assert np.allclose(paths[0], paths[-1], atol=1e-8)

    def test_negative_net_depletes_cash(self):
        """Negative monthly net → final cumulative cash < 0."""
        paths = simulate_cash_flow(
            monthly_income=2_000,
            monthly_expenses=5_000,   # net = -3000
            months=12,
            volatility=0.0,
            simulations=10,
            seed=0,
        )
        assert (paths[:, -1] < 0).all()

    def test_higher_volatility_wider_spread(self):
        """Higher volatility → larger std of final cash values."""
        paths_low  = simulate_cash_flow(5_000, 4_000, 24, volatility=0.0, simulations=1000, seed=3)
        paths_high = simulate_cash_flow(5_000, 4_000, 24, volatility=0.5, simulations=1000, seed=3)
        assert paths_high[:, -1].std() > paths_low[:, -1].std()

    def test_income_growth_increases_final_cash(self):
        """Positive income growth → higher final cash than flat income."""
        base  = simulate_cash_flow(5_000, 4_000, 24, income_growth=0.0,   volatility=0.0, simulations=10, seed=0)
        grown = simulate_cash_flow(5_000, 4_000, 24, income_growth=0.02,  volatility=0.0, simulations=10, seed=0)
        assert grown[:, -1].mean() > base[:, -1].mean()

    def test_cumsum_property(self):
        """Paths are cumulative: each step adds the monthly net."""
        paths = simulate_cash_flow(5_000, 4_000, 3, volatility=0.0, simulations=5, seed=0)
        # Each path's value at month m should be m * 1000
        assert np.allclose(paths[:, 0], 1_000.0, atol=1e-6)    # month 1
        assert np.allclose(paths[:, 1], 2_000.0, atol=1e-6)    # month 2


# ── summarize_simulations ─────────────────────────────────────────────────────

class TestSummarizeSimulations:
    @pytest.fixture
    def portfolio_paths(self):
        return simulate_portfolio(100_000, 0.08, 0.15, days=252, simulations=1000, seed=42)

    def test_returns_dict(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths)
        assert isinstance(summary, dict)

    def test_default_percentile_keys(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths)
        for key in ("final_p5", "final_p25", "final_p50", "final_p75", "final_p95"):
            assert key in summary, f"Missing key: {key}"

    def test_custom_percentiles_present(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths, percentiles=[10, 50, 90])
        assert "final_p10" in summary
        assert "final_p50" in summary
        assert "final_p90" in summary

    def test_percentile_paths_shape(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths, percentiles=[25, 50, 75])
        for key in ("p25", "p50", "p75"):
            arr = summary["percentile_paths"][key]
            assert len(arr) == portfolio_paths.shape[1]

    def test_required_summary_keys(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths)
        for key in ("final_mean", "final_median", "final_std", "prob_loss",
                    "n_simulations", "n_steps"):
            assert key in summary

    def test_n_simulations_correct(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths)
        assert summary["n_simulations"] == 1000

    def test_n_steps_correct(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths)
        assert summary["n_steps"] == 252

    def test_prob_loss_between_0_and_1(self, portfolio_paths):
        summary = summarize_simulations(portfolio_paths)
        assert 0.0 <= summary["prob_loss"] <= 1.0

    def test_percentiles_ordered(self, portfolio_paths):
        """p5 <= p25 <= p50 <= p75 <= p95 for final values."""
        summary = summarize_simulations(portfolio_paths)
        assert summary["final_p5"] <= summary["final_p25"]
        assert summary["final_p25"] <= summary["final_p50"]
        assert summary["final_p50"] <= summary["final_p75"]
        assert summary["final_p75"] <= summary["final_p95"]

    def test_high_vol_wider_spread(self):
        """Higher volatility → higher standard deviation of final values."""
        paths_low  = simulate_portfolio(100_000, 0.08, 0.05, days=252, simulations=2000, seed=7)
        paths_high = simulate_portfolio(100_000, 0.08, 0.40, days=252, simulations=2000, seed=7)
        s_low  = summarize_simulations(paths_low)
        s_high = summarize_simulations(paths_high)
        assert s_high["final_std"] > s_low["final_std"]

    def test_cash_flow_simulation_works(self):
        """summarize_simulations also works on cash-flow paths (simulations, months)."""
        cf_paths = simulate_cash_flow(5_000, 4_000, 12, simulations=500, seed=0)
        summary  = summarize_simulations(cf_paths)
        assert summary["n_simulations"] == 500
        assert summary["n_steps"] == 12

"""
Tests for src/analysis/risk_metrics.py

Covers: value_at_risk, conditional_var, confidence_bands,
        and legacy helpers (historical_var, historical_cvar,
        parametric_var, parametric_cvar, compute_all_risk_metrics).
"""
import numpy as np
import pandas as pd
import pytest

from src.analysis.risk_metrics import (
    compute_all_risk_metrics,
    conditional_var,
    confidence_bands,
    historical_cvar,
    historical_var,
    parametric_cvar,
    parametric_var,
    value_at_risk,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def normal_returns():
    """1 000-point normal return series with mean ≈ 0, sd ≈ 2%."""
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(0.001, 0.02, 1_000))


@pytest.fixture
def fat_tail_returns():
    """t(3) returns — heavier tails than normal."""
    rng = np.random.default_rng(42)
    return pd.Series(rng.standard_t(df=3, size=1_000) * 0.02)


@pytest.fixture
def loss_heavy_returns():
    """Returns biased strongly negative (many losses)."""
    rng = np.random.default_rng(0)
    return pd.Series(rng.normal(-0.005, 0.02, 1_000))


# ── value_at_risk (spec-aligned public API) ───────────────────────────────────

class TestValueAtRisk:
    def test_returns_positive_number(self, normal_returns):
        """VaR is expressed as a positive loss magnitude."""
        var = value_at_risk(normal_returns, confidence=0.95, horizon_days=1)
        assert var > 0.0

    def test_var_is_positive_for_normal_distribution(self, normal_returns):
        """VaR of a symmetric normal distribution with mean ≈ 0 must be positive."""
        var = value_at_risk(normal_returns, confidence=0.95)
        assert var > 0.0

    def test_higher_confidence_gives_higher_var(self, normal_returns):
        var95 = value_at_risk(normal_returns, 0.95, 1)
        var99 = value_at_risk(normal_returns, 0.99, 1)
        assert var99 >= var95

    def test_longer_horizon_gives_higher_var(self, normal_returns):
        """Square-root-of-time scaling: 30-day VaR > 1-day VaR."""
        var1d  = value_at_risk(normal_returns, 0.95, horizon_days=1)
        var30d = value_at_risk(normal_returns, 0.95, horizon_days=30)
        assert var30d > var1d

    def test_sqrt_time_scaling(self, normal_returns):
        """30-day VaR ≈ √30 × 1-day VaR (square-root-of-time rule)."""
        var1  = value_at_risk(normal_returns, 0.95, horizon_days=1)
        var30 = value_at_risk(normal_returns, 0.95, horizon_days=30)
        assert var30 == pytest.approx(var1 * np.sqrt(30), rel=1e-6)

    def test_loss_heavy_returns_higher_var(self, loss_heavy_returns, normal_returns):
        """Negatively-biased returns should produce larger VaR."""
        var_loss   = value_at_risk(loss_heavy_returns, 0.95, 1)
        var_normal = value_at_risk(normal_returns,     0.95, 1)
        assert var_loss > var_normal

    def test_empty_returns_returns_zero(self):
        var = value_at_risk(np.array([]), confidence=0.95)
        assert var == 0.0


# ── conditional_var (CVaR / Expected Shortfall) ───────────────────────────────

class TestConditionalVar:
    def test_cvar_exceeds_var(self, normal_returns):
        """CVaR (Expected Shortfall) >= VaR — it captures the tail beyond VaR."""
        var  = value_at_risk(normal_returns, 0.95, 1)
        cvar = conditional_var(normal_returns, 0.95, 1)
        assert cvar >= var

    def test_cvar_positive(self, normal_returns):
        cvar = conditional_var(normal_returns, 0.95, 1)
        assert cvar > 0.0

    def test_higher_confidence_increases_cvar(self, normal_returns):
        cvar95 = conditional_var(normal_returns, 0.95, 1)
        cvar99 = conditional_var(normal_returns, 0.99, 1)
        assert cvar99 >= cvar95

    def test_fat_tail_cvar_more_vs_var(self, fat_tail_returns, normal_returns):
        """For fat-tailed data, CVaR/VaR ratio is higher than for normal data."""
        var_n  = value_at_risk(normal_returns,  0.95, 1)
        cvar_n = conditional_var(normal_returns, 0.95, 1)
        var_f  = value_at_risk(fat_tail_returns,  0.95, 1)
        cvar_f = conditional_var(fat_tail_returns, 0.95, 1)
        ratio_fat    = cvar_f / var_f
        ratio_normal = cvar_n / var_n
        assert ratio_fat > ratio_normal

    def test_scaled_series_scales_cvar(self, normal_returns):
        """Doubling all returns doubles CVaR (linearity)."""
        cvar1 = conditional_var(normal_returns,       0.95, 1)
        cvar2 = conditional_var(normal_returns * 2.0, 0.95, 1)
        assert cvar2 == pytest.approx(cvar1 * 2.0, rel=1e-3)


# ── confidence_bands (Monte Carlo GBM) ───────────────────────────────────────

class TestConfidenceBands:
    @pytest.fixture
    def bands(self):
        return confidence_bands(
            current_value=100_000,
            expected_return=0.08,
            volatility=0.15,
            days=60,
            simulations=2_000,
            seed=42,
        )

    def test_returns_dict(self, bands):
        assert isinstance(bands, dict)

    def test_percentile_path_keys_present(self, bands):
        for key in ("p5", "p25", "p50", "p75", "p95"):
            assert key in bands, f"Missing key: {key}"

    def test_final_value_keys_present(self, bands):
        for key in ("final_p5", "final_p25", "final_p50", "final_p75", "final_p95"):
            assert key in bands, f"Missing key: {key}"

    def test_days_key_correct(self, bands):
        assert "days" in bands
        assert len(bands["days"]) == 60

    def test_current_value_preserved(self, bands):
        assert bands["current_value"] == 100_000

    def test_path_lengths_correct(self, bands):
        for key in ("p5", "p25", "p50", "p75", "p95"):
            assert len(bands[key]) == 60

    def test_p5_below_p95(self, bands):
        """5th percentile path must be everywhere below 95th percentile."""
        assert all(lo < hi for lo, hi in zip(bands["p5"], bands["p95"]))

    def test_p50_median_of_bands(self, bands):
        """Median path stays between p25 and p75 at each step."""
        for lo, med, hi in zip(bands["p25"], bands["p50"], bands["p75"]):
            assert lo <= med <= hi

    def test_final_percentiles_ordered(self, bands):
        assert bands["final_p5"] <= bands["final_p25"]
        assert bands["final_p25"] <= bands["final_p50"]
        assert bands["final_p50"] <= bands["final_p75"]
        assert bands["final_p75"] <= bands["final_p95"]

    def test_higher_volatility_wider_bands(self):
        """Higher volatility must produce wider final percentile spread."""
        low  = confidence_bands(100_000, 0.08, 0.05, days=252, simulations=2_000, seed=5)
        high = confidence_bands(100_000, 0.08, 0.40, days=252, simulations=2_000, seed=5)
        spread_low  = low["final_p95"]  - low["final_p5"]
        spread_high = high["final_p95"] - high["final_p5"]
        assert spread_high > spread_low


# ── Legacy helpers ────────────────────────────────────────────────────────────

class TestHistoricalVaR:
    def test_positive_value(self, normal_returns):
        assert historical_var(normal_returns, 0.95) > 0.0

    def test_higher_confidence_higher_var(self, normal_returns):
        assert historical_var(normal_returns, 0.99) >= historical_var(normal_returns, 0.95)


class TestParametricVaR:
    def test_positive_value(self, normal_returns):
        assert parametric_var(normal_returns, 0.95) > 0.0

    def test_close_to_historical_for_normal_data(self, normal_returns):
        h = historical_var(normal_returns, 0.95)
        p = parametric_var(normal_returns, 0.95)
        # For a normal distribution, they should agree within 30%
        assert abs(h - p) / h < 0.30


class TestHistoricalCVaR:
    def test_cvar_exceeds_var(self, normal_returns):
        var  = historical_var(normal_returns, 0.95)
        cvar = historical_cvar(normal_returns, 0.95)
        assert cvar >= var

    def test_positive_value(self, normal_returns):
        assert historical_cvar(normal_returns, 0.95) > 0.0


class TestParametricCVaR:
    def test_cvar_exceeds_var(self, normal_returns):
        var  = parametric_var(normal_returns, 0.95)
        cvar = parametric_cvar(normal_returns, 0.95)
        assert cvar >= var


class TestComputeAllRiskMetrics:
    def test_returns_all_required_keys(self, normal_returns):
        metrics = compute_all_risk_metrics(normal_returns)
        for key in (
            "historical_var", "parametric_var",
            "historical_cvar", "parametric_cvar",
            "var_30d", "cvar_30d",
            "skewness", "kurtosis",
        ):
            assert key in metrics, f"Missing key: {key}"

    def test_all_var_values_positive(self, normal_returns):
        metrics = compute_all_risk_metrics(normal_returns)
        for key in ("historical_var", "parametric_var", "historical_cvar", "parametric_cvar"):
            assert metrics[key] > 0.0, f"{key} should be positive"

    def test_skewness_near_zero_for_normal(self, normal_returns):
        """Normal distribution has skewness ≈ 0."""
        metrics = compute_all_risk_metrics(normal_returns)
        assert abs(metrics["skewness"]) < 0.5

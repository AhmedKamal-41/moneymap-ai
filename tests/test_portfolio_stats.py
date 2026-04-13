"""
Tests for src/analysis/portfolio_stats.py

Covers: expected_annual_return, annual_volatility, sharpe_ratio,
        beta, max_drawdown, portfolio_return, portfolio_volatility,
        portfolio_sharpe, compute_all.
"""
import numpy as np
import pandas as pd
import pytest

from src.analysis.portfolio_stats import (
    TRADING_DAYS,
    annual_volatility,
    beta,
    compute_all,
    compute_returns,
    expected_annual_return,
    max_drawdown,
    portfolio_return,
    portfolio_sharpe,
    portfolio_volatility,
    sharpe_ratio,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def flat_returns():
    """Constant 0.1% daily return — zero volatility."""
    return pd.Series([0.001] * TRADING_DAYS)


@pytest.fixture
def random_returns():
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(0.0005, 0.01, TRADING_DAYS))


@pytest.fixture
def known_returns():
    """Repeating [0.002, 0.001, 0.003] * 84 — analytically tractable."""
    return pd.Series([0.002, 0.001, 0.003] * 84)


# ── max_drawdown — hand-calculated path ───────────────────────────────────────

class TestMaxDrawdownHandCalculated:
    def test_three_point_peak_then_trough(self):
        """Prices 100 → 120 → 90: worst drawdown from peak 120 is -25%."""
        prices = pd.Series([100.0, 120.0, 90.0])
        assert max_drawdown(prices) == pytest.approx(-0.25, rel=1e-9)


# ── compute_returns ───────────────────────────────────────────────────────────

class TestComputeReturns:
    def test_output_length_minus_one(self):
        prices = pd.Series([100.0, 105.0, 110.0, 99.0])
        returns = compute_returns(prices)
        assert len(returns) == len(prices) - 1

    def test_correct_values(self):
        prices = pd.Series([100.0, 110.0])
        returns = compute_returns(prices)
        assert float(returns.iloc[0]) == pytest.approx(0.10, rel=1e-6)

    def test_no_nan_in_output(self):
        prices = pd.Series([100.0, 105.0, 103.0, 108.0])
        returns = compute_returns(prices)
        assert not returns.isna().any()


# ── expected_annual_return ────────────────────────────────────────────────────

class TestExpectedAnnualReturn:
    def test_constant_returns_annualised_correctly(self, flat_returns):
        # 0.001/day * 252 days = 0.252
        er = expected_annual_return(flat_returns)
        assert er == pytest.approx(0.001 * TRADING_DAYS, rel=1e-6)

    def test_zero_mean_returns_zero(self):
        returns = pd.Series([0.01, -0.01] * 126)
        er = expected_annual_return(returns)
        assert er == pytest.approx(0.0, abs=1e-10)

    def test_known_value(self, known_returns):
        # mean = (0.002 + 0.001 + 0.003) / 3 = 0.002
        er = expected_annual_return(known_returns)
        assert er == pytest.approx(0.002 * TRADING_DAYS, rel=1e-6)


# ── annual_volatility ─────────────────────────────────────────────────────────

class TestAnnualVolatility:
    def test_zero_for_constant_returns(self, flat_returns):
        vol = annual_volatility(flat_returns)
        assert vol == pytest.approx(0.0, abs=1e-10)

    def test_positive_for_varying_returns(self, random_returns):
        vol = annual_volatility(random_returns)
        assert vol > 0.0

    def test_scales_with_sqrt_252(self, random_returns):
        daily_std = float(random_returns.std())
        vol = annual_volatility(random_returns)
        assert vol == pytest.approx(daily_std * np.sqrt(TRADING_DAYS), rel=1e-6)


# ── sharpe_ratio ──────────────────────────────────────────────────────────────

class TestSharpeRatio:
    def test_zero_volatility_returns_zero(self, flat_returns):
        # When std ≈ 0, sharpe_ratio returns 0.0 to avoid division by zero
        s = sharpe_ratio(flat_returns, risk_free_rate=0.05)
        assert s == 0.0

    def test_positive_when_excess_return_positive(self, random_returns):
        # mean daily return 0.0005 * 252 = 0.126 annual >> rfr=0.0
        s = sharpe_ratio(random_returns, risk_free_rate=0.0)
        assert s > 0.0

    def test_negative_when_rfr_exceeds_return(self, flat_returns):
        # flat_returns: annual return = 0.252, but zero std → returns 0.0 (edge case)
        # Use random_returns where annual ≈ 0.126 < rfr=0.20
        rng = np.random.default_rng(0)
        low_returns = pd.Series(rng.normal(0.0003, 0.01, TRADING_DAYS))
        s = sharpe_ratio(low_returns, risk_free_rate=0.20)
        assert s < 0.0

    def test_known_formula(self, known_returns):
        """Sharpe must equal (mean*252 - rfr) / (std*sqrt(252))."""
        rfr = 0.05
        result   = sharpe_ratio(known_returns, risk_free_rate=rfr)
        expected = (
            (known_returns.mean() * TRADING_DAYS - rfr)
            / (known_returns.std() * np.sqrt(TRADING_DAYS))
        )
        assert result == pytest.approx(expected, rel=1e-6)

    def test_higher_rfr_lowers_sharpe(self, random_returns):
        s_low  = sharpe_ratio(random_returns, risk_free_rate=0.0)
        s_high = sharpe_ratio(random_returns, risk_free_rate=0.10)
        assert s_low > s_high


# ── beta ──────────────────────────────────────────────────────────────────────

class TestBeta:
    def test_identical_series_returns_one(self, random_returns):
        """Asset perfectly correlated with itself → beta = 1.0."""
        b = beta(random_returns, random_returns)
        assert b == pytest.approx(1.0, rel=1e-6)

    def test_negatively_correlated_returns_negative_one(self, random_returns):
        b = beta(random_returns, -random_returns)
        assert b == pytest.approx(-1.0, rel=1e-6)

    def test_scaled_series_returns_one(self, random_returns):
        """Asset = 2×market returns → beta = 2.0 by OLS formula.

        Cov(2*m, m) / Var(m) = 2*Var(m)/Var(m) = 2.
        """
        b = beta(random_returns * 2.0, random_returns)
        assert b == pytest.approx(2.0, rel=1e-6)

    def test_uncorrelated_series_near_zero(self):
        rng = np.random.default_rng(7)
        asset_r  = pd.Series(rng.normal(0, 0.01, 500))
        market_r = pd.Series(rng.normal(0, 0.01, 500))
        b = beta(asset_r, market_r)
        # With two independent normal series, beta should be close to 0
        assert abs(b) < 0.3


# ── max_drawdown ──────────────────────────────────────────────────────────────

class TestMaxDrawdown:
    def test_known_price_series(self):
        """[100, 80, 90, 70, 100] → max drawdown = -0.30 (peak 100 → trough 70)."""
        prices = pd.Series([100.0, 80.0, 90.0, 70.0, 100.0])
        dd = max_drawdown(prices)
        assert dd == pytest.approx(-0.30, rel=1e-6)

    def test_always_rising_no_drawdown(self):
        prices = pd.Series([100.0, 110.0, 120.0, 130.0])
        dd = max_drawdown(prices)
        assert dd == pytest.approx(0.0, abs=1e-10)

    def test_immediate_50pct_drop(self):
        prices = pd.Series([200.0, 100.0, 100.0])
        dd = max_drawdown(prices)
        assert dd == pytest.approx(-0.50, rel=1e-6)

    def test_return_is_negative_or_zero(self):
        rng = np.random.default_rng(0)
        prices = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
        prices = prices.clip(lower=1.0)  # keep prices positive
        dd = max_drawdown(prices)
        assert dd <= 0.0

    def test_multiple_drawdowns_returns_worst(self):
        # Drop 20%, recover, drop 40% — worst should be -0.40
        prices = pd.Series([100.0, 80.0, 100.0, 60.0, 100.0])
        dd = max_drawdown(prices)
        assert dd == pytest.approx(-0.40, rel=1e-6)


# ── portfolio_return / portfolio_volatility / portfolio_sharpe ────────────────

class TestPortfolioStats:
    def test_portfolio_return_weighted_average(self):
        weights = np.array([0.6, 0.4])
        expected_returns = np.array([0.10, 0.05])
        pr = portfolio_return(weights, expected_returns)
        assert pr == pytest.approx(0.08, rel=1e-6)

    def test_portfolio_return_equal_weights(self):
        weights = np.array([0.5, 0.5])
        expected_returns = np.array([0.12, 0.08])
        pr = portfolio_return(weights, expected_returns)
        assert pr == pytest.approx(0.10, rel=1e-6)

    def test_portfolio_volatility_positive(self):
        weights = np.array([0.5, 0.5])
        cov = np.array([[0.04, 0.01], [0.01, 0.09]])
        pv = portfolio_volatility(weights, cov)
        assert pv > 0.0

    def test_portfolio_volatility_single_asset(self):
        weights = np.array([1.0])
        cov = np.array([[0.09]])     # sigma^2 = 0.09 → sigma = 0.30
        pv = portfolio_volatility(weights, cov)
        assert pv == pytest.approx(0.30, rel=1e-6)

    def test_portfolio_sharpe_positive_for_high_return(self):
        weights = np.array([1.0])
        expected_returns = np.array([0.15])
        cov = np.array([[0.04]])     # vol = 0.20
        ps = portfolio_sharpe(weights, expected_returns, cov, risk_free_rate=0.05)
        assert ps == pytest.approx((0.15 - 0.05) / 0.20, rel=1e-6)


# ── compute_all ───────────────────────────────────────────────────────────────

class TestComputeAll:
    def test_returns_required_keys(self, random_returns):
        stats = compute_all(random_returns)
        for key in ("expected_return_ann", "volatility_ann", "sharpe", "max_drawdown"):
            assert key in stats

    def test_includes_beta_when_benchmark_provided(self, random_returns):
        stats = compute_all(random_returns, benchmark_returns=random_returns)
        assert "beta" in stats
        assert stats["beta"] == pytest.approx(1.0, rel=1e-6)

    def test_max_drawdown_is_negative_or_zero(self, random_returns):
        stats = compute_all(random_returns)
        assert stats["max_drawdown"] <= 0.0

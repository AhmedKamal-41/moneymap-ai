"""
Offline checks: API clients return non-empty synthetic bundles when live data
is unavailable (no network required for these assertions).
"""
import pandas as pd

from src.api_clients.alpha_vantage_client import AlphaVantageClient
from src.api_clients.bls_client import BLSClient
from src.api_clients.fred_client import FREDClient, empty_macro_dashboard, sample_macro_dashboard
from src.api_clients.treasury_client import TreasuryClient


class TestFREDSampleFallback:
    def test_sample_macro_dashboard_nonempty(self):
        dash = sample_macro_dashboard(lookback_years=2)
        assert dash["_is_fallback"] is True
        for key in (
            "fed_funds",
            "cpiaucsl",
            "cpi_yoy",
            "unemployment",
            "t10yr",
            "t2yr",
            "yield_spread",
            "gdp_growth",
            "sp500",
        ):
            assert isinstance(dash[key], pd.DataFrame)
            assert not dash[key].empty, key
            assert "value" in dash[key].columns

    def test_empty_macro_dashboard_still_empty(self):
        dash = empty_macro_dashboard()
        assert all(dash[k].empty for k in dash if isinstance(dash[k], pd.DataFrame))

    def test_client_without_key_returns_sample_dashboard(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        c = FREDClient(api_key="")
        dash = c.get_macro_dashboard(lookback_years=2)
        assert dash["_is_fallback"] is True
        assert not dash["fed_funds"].empty

    def test_get_series_without_client_returns_sample(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        c = FREDClient(api_key="")
        df = c.get_series("DGS10")
        assert not df.empty
        assert df.index.name == "date"


class TestBLSSampleFallback:
    def test_cpi_fallback_nonempty(self, monkeypatch):
        monkeypatch.setenv("BLS_API_KEY", "")
        client = BLSClient(api_key="")
        client._post = lambda *a, **k: None  # type: ignore[method-assign]
        df = client.get_cpi_data(lookback_years=2)
        assert not df.empty
        assert "yoy_pct" in df.columns
        assert df.attrs.get("is_fallback") is True


class TestTreasurySampleFallback:
    def test_rates_fallback_on_fetch_error(self, monkeypatch):
        import src.api_clients.treasury_client as tc

        def boom(*a, **k):
            raise tc.TreasuryClientError("simulated")

        monkeypatch.setattr(tc, "_fetch_avg_rates", boom)
        client = TreasuryClient()
        df = client.get_treasury_rates(lookback_months=12)
        assert not df.empty
        assert df.attrs.get("is_fallback") is True


class TestAlphaVantageSampleFallback:
    def test_daily_prices_without_key(self, monkeypatch):
        monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
        c = AlphaVantageClient(api_key="")
        df = c.get_daily_prices("SPY", lookback_years=1)
        assert not df.empty
        assert "adjusted_close" in df.columns
        assert df.attrs.get("is_fallback") is True

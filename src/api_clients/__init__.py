"""
API clients for external economic and market data (FRED, BLS, Treasury, Alpha Vantage).
"""
from .fred_client import FREDClient, FREDClientError, empty_macro_dashboard
from .bls_client import BLSClient, BLSClientError
from .treasury_client import TreasuryClient, TreasuryClientError
from .alpha_vantage_client import (
    AlphaVantageClient,
    AlphaVantageError,
    AlphaVantageRateLimitError,
)

__all__ = [
    "FREDClient",
    "FREDClientError",
    "empty_macro_dashboard",
    "BLSClient", "BLSClientError",
    "TreasuryClient", "TreasuryClientError",
    "AlphaVantageClient", "AlphaVantageError", "AlphaVantageRateLimitError",
]

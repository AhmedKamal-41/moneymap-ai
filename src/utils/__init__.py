"""
Utilities: formatting helpers and shared constants for the analysis layer.
"""
from .formatting import fmt_currency, fmt_percent, fmt_number
from .constants import HISTORICAL_SCENARIOS, REGIME_THRESHOLDS, ALLOCATION_TIERS

__all__ = [
    "fmt_currency", "fmt_percent", "fmt_number",
    "HISTORICAL_SCENARIOS", "REGIME_THRESHOLDS", "ALLOCATION_TIERS",
]

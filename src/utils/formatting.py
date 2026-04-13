"""
formatting.py
-------------
Currency, percentage, and number formatting helpers.
"""
from __future__ import annotations


def fmt_currency(value: float, symbol: str = "$", decimals: int = 0) -> str:
    """Format a number as currency, e.g. $1,234 or -$1,234."""
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    formatted = f"{abs(value):,.{decimals}f}"
    return f"{sign}{symbol}{formatted}"


def fmt_percent(value: float, decimals: int = 1) -> str:
    """Format a fraction as a percentage string, e.g. 0.153 → '15.3%'."""
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def fmt_number(value: float, decimals: int = 2, suffix: str = "") -> str:
    """Format a plain number with optional suffix, e.g. 1234.5 → '1,234.50x'."""
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}{suffix}"


def fmt_millions(value: float, decimals: int = 1) -> str:
    """Format a large number in millions, e.g. 1_500_000 → '$1.5M'."""
    if value is None:
        return "N/A"
    return f"${value / 1_000_000:.{decimals}f}M"


def fmt_basis_points(value: float) -> str:
    """Convert a decimal rate to basis points string, e.g. 0.0025 → '25 bps'."""
    if value is None:
        return "N/A"
    return f"{value * 10_000:.0f} bps"

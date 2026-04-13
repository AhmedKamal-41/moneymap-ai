"""
market_analyzer.py
------------------
Macro-economic regime classification and investment guidance.

Pure computation — no Streamlit calls, no Plotly figures.
Charts live in the page layer; this module stays testable and importable
outside of a Streamlit session.

Public API
----------
get_macro_summary(fred_data)              -> dict
regime_description(regime)               -> str
rate_environment_advice(fed_rate,
                        inflation,
                        regime)           -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

log = logging.getLogger(__name__)

# ── Regime identifiers ────────────────────────────────────────────────────────
REGIMES = ("risk_on", "cautious", "risk_off", "recession_warning")

# ── Classification thresholds ─────────────────────────────────────────────────
_INF_LOW        = 3.0     # CPI YoY% — "contained" inflation
_INF_HIGH       = 4.0     # CPI YoY% — "high" inflation
_UNEM_LOW       = 4.5     # Unemployment% — "tight" labour market
_SPREAD_INV     = 0.0     # 10Y-2Y spread — below this = inverted yield curve
_UNEM_RISE_FAST = 0.4     # %-point rise over 6 months = "rising fast"
_RATE_RISE_FAST = 0.3     # %-point rise in fed funds over 6 months


# ── DataFrame helpers ─────────────────────────────────────────────────────────

def _latest(df: pd.DataFrame | Any) -> Optional[float]:
    """Return the most recent non-NaN scalar value from a DataFrame."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    col = df.columns[0]
    clean = df[col].dropna()
    return float(clean.iloc[-1]) if len(clean) else None


def _n_months_ago(df: pd.DataFrame | Any, months: int = 6) -> Optional[float]:
    """
    Return the last observed value at least `months` calendar months before
    the most recent observation in `df`.  Falls back to the earliest row if
    the series is shorter than the requested lookback.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    col = df.columns[0]
    clean = df[col].dropna()
    if len(clean) == 0:
        return None
    cutoff = clean.index[-1] - pd.DateOffset(months=months)
    past = clean[clean.index <= cutoff]
    if len(past) == 0:
        return float(clean.iloc[0])       # series shorter than lookback
    return float(past.iloc[-1])


def _direction(
    current: Optional[float],
    past: Optional[float],
    threshold: float = 0.15,
) -> str:
    """
    Classify the direction of change between two scalar readings.

    Returns one of "rising", "falling", or "flat".
    `threshold` is the minimum absolute change to count as directional.
    """
    if current is None or past is None:
        return "flat"
    delta = current - past
    if delta > threshold:
        return "rising"
    if delta < -threshold:
        return "falling"
    return "flat"


def _sp500_ytd(sp500_df: pd.DataFrame | Any) -> Optional[float]:
    """Compute S&P 500 year-to-date return as a percentage."""
    if not isinstance(sp500_df, pd.DataFrame) or sp500_df.empty:
        return None
    col = sp500_df.columns[0]
    s = sp500_df[col].dropna()
    if len(s) == 0:
        return None
    current_year = s.index[-1].year
    ytd_start = s[s.index.year == current_year]
    if len(ytd_start) == 0:
        ytd_start = s
    start_val = float(ytd_start.iloc[0])
    end_val   = float(s.iloc[-1])
    if start_val == 0:
        return None
    return round((end_val / start_val - 1.0) * 100.0, 2)


# ── Regime classifier ─────────────────────────────────────────────────────────

def _classify_regime(
    inflation: Optional[float],
    fed_rate:  Optional[float],
    unemployment: Optional[float],
    yield_spread: Optional[float],
    rate_dir:  str,
    unem_dir:  str,
    inf_dir:   str,
) -> str:
    """
    Four-bucket regime classifier.  Priority order (highest first):

    1. recession_warning — yield curve inverted OR unemployment rising fast
    2. risk_off          — high inflation AND rates rising
    3. risk_on           — low inflation, low unemployment, normal yield curve
    4. cautious          — everything else
    """
    inf   = inflation    if inflation    is not None else 3.0
    unem  = unemployment if unemployment is not None else 4.0
    spread= yield_spread if yield_spread is not None else 0.5

    # 1. Recession warning
    if spread < _SPREAD_INV or unem_dir == "rising":
        return "recession_warning"

    # 2. Risk-off
    if inf > _INF_HIGH and rate_dir == "rising":
        return "risk_off"

    # 3. Risk-on
    if inf < _INF_LOW and unem < _UNEM_LOW and spread > _SPREAD_INV:
        return "risk_on"

    # 4. Default
    return "cautious"


# ── Public: main summary ──────────────────────────────────────────────────────

def get_macro_summary(fred_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derive a macro health snapshot from the output of
    ``FREDClient.get_macro_dashboard()``.

    Parameters
    ----------
    fred_data : dict
        Keys: fed_funds, cpiaucsl (CPI level), cpi_yoy, unemployment, t10yr, t2yr,
              yield_spread, gdp_growth, sp500, _is_fallback.
        Series DataFrames use a DatetimeIndex and a single ``value`` column.

    Returns
    -------
    dict with:
        current_fed_rate      float | None
        current_inflation     float | None
        current_unemployment  float | None
        yield_spread          float | None
        yield_inverted        bool
        sp500_ytd_return      float | None
        fed_rate_direction    "rising" | "falling" | "flat"
        inflation_direction   "rising" | "falling" | "flat"
        unemployment_direction "rising" | "falling" | "flat"
        rate_6mo_ago          float | None
        inflation_6mo_ago     float | None
        unemployment_6mo_ago  float | None
        regime                str  (one of REGIMES)
        is_fallback           bool
    """
    ff_df    = fred_data.get("fed_funds")
    cpi_df   = fred_data.get("cpi_yoy")
    unem_df  = fred_data.get("unemployment")
    sp_df    = fred_data.get("sp500")
    spr_df   = fred_data.get("yield_spread")

    # Current values
    fed_rate     = _latest(ff_df)
    inflation    = _latest(cpi_df)
    unemployment = _latest(unem_df)
    spread       = _latest(spr_df)
    sp500_ytd    = _sp500_ytd(sp_df)

    # 6-month-ago values for direction
    fed_6mo   = _n_months_ago(ff_df,   6)
    inf_6mo   = _n_months_ago(cpi_df,  6)
    unem_6mo  = _n_months_ago(unem_df, 6)

    # Directions (with tuned per-metric thresholds)
    rate_dir = _direction(fed_rate,     fed_6mo,  threshold=_RATE_RISE_FAST)
    inf_dir  = _direction(inflation,    inf_6mo,  threshold=0.20)
    unem_dir = _direction(unemployment, unem_6mo, threshold=_UNEM_RISE_FAST)

    regime = _classify_regime(
        inflation=inflation,
        fed_rate=fed_rate,
        unemployment=unemployment,
        yield_spread=spread,
        rate_dir=rate_dir,
        unem_dir=unem_dir,
        inf_dir=inf_dir,
    )

    return {
        # Current readings
        "current_fed_rate":        fed_rate,
        "current_inflation":       inflation,
        "current_unemployment":    unemployment,
        "yield_spread":            spread,
        "yield_inverted":          spread is not None and spread < _SPREAD_INV,
        "sp500_ytd_return":        sp500_ytd,
        # Six-months-ago readings (for delta display)
        "rate_6mo_ago":            fed_6mo,
        "inflation_6mo_ago":       inf_6mo,
        "unemployment_6mo_ago":    unem_6mo,
        # Directions
        "fed_rate_direction":      rate_dir,
        "inflation_direction":     inf_dir,
        "unemployment_direction":  unem_dir,
        # Regime
        "regime":                  regime,
        # Meta
        "is_fallback":             bool(fred_data.get("_is_fallback", False)),
    }


# ── Public: regime description ────────────────────────────────────────────────

_REGIME_DESCRIPTIONS: Dict[str, str] = {
    "risk_on": (
        "The economic backdrop is constructive. Inflation is contained, the "
        "labour market is healthy, and the yield curve is signalling normal "
        "growth expectations. Historically, this environment rewards risk assets "
        "— equities, growth investments, and reducing cash drag. "
        "Focus on building long-term positions while conditions are favourable."
    ),
    "cautious": (
        "The picture is mixed. Some indicators are healthy but others suggest "
        "uncertainty — inflation may be elevated, growth is slowing, or the "
        "labour market is showing early cracks. Now is a time to balance "
        "growth exposure with defensive positions: maintain your emergency fund, "
        "avoid over-leveraging, and keep some dry powder for opportunities."
    ),
    "risk_off": (
        "Inflation is running hot and the Fed is still tightening. This is a "
        "challenging environment for bonds (prices fall as yields rise) and "
        "for high-multiple equities. Favour short-duration fixed income, "
        "inflation-protected securities (TIPS, I-Bonds), real assets, and "
        "paying down variable-rate debt before rates climb further."
    ),
    "recession_warning": (
        "Warning signals are flashing. The yield curve is inverted and/or "
        "unemployment is trending up — two of the most reliable leading "
        "indicators of recession. This is not a prediction, but it warrants "
        "defensive positioning: strengthen your emergency fund to 6+ months, "
        "prioritise debt repayment, reduce speculative exposure, and hold "
        "more cash than usual. Capital preservation beats chasing yield here."
    ),
}


def regime_description(regime: str) -> str:
    """
    Return a plain-English explanation of what the current macro regime
    means for money allocation decisions.

    Parameters
    ----------
    regime : one of "risk_on", "cautious", "risk_off", "recession_warning".

    Returns
    -------
    str — multi-sentence description suitable for display in the UI.
    """
    return _REGIME_DESCRIPTIONS.get(
        regime,
        "Insufficient data to characterise the current economic regime. "
        "Check your API connections and try again.",
    )


# ── Public: rate environment advice ──────────────────────────────────────────

def rate_environment_advice(
    fed_rate:  Optional[float],
    inflation: Optional[float],
    regime:    str,
) -> Dict[str, str]:
    """
    Translate the current rate and inflation environment into actionable guidance.

    Parameters
    ----------
    fed_rate   : current Federal Funds rate in percent (e.g. 5.33).
    inflation  : current CPI year-over-year in percent (e.g. 3.2).
    regime     : regime string from get_macro_summary().

    Returns
    -------
    dict with:
        savings_rate_attractiveness : "high" | "moderate" | "low"
        bond_outlook                : short description string
        equity_outlook              : short description string
        debt_urgency                : "high" | "moderate" | "low"
        real_rate                   : str  (fed_rate - inflation, formatted)
        summary_line                : one-sentence action summary
    """
    ff  = fed_rate  if fed_rate  is not None else 0.0
    inf = inflation if inflation is not None else 0.0
    real_rate = ff - inf

    # ── Savings attractiveness ────────────────────────────────────────────────
    if ff >= 4.5:
        savings_attr = "high"
    elif ff >= 2.0:
        savings_attr = "moderate"
    else:
        savings_attr = "low"

    # ── Bond outlook ──────────────────────────────────────────────────────────
    if regime == "recession_warning":
        bond_outlook = (
            "Long-duration Treasuries can rally in a recession as rates fall. "
            "Consider shifting toward intermediate-term bonds or TIPS."
        )
    elif regime == "risk_off":
        bond_outlook = (
            "Avoid long-duration bonds — rising rates erode bond prices. "
            "Favour short-duration (< 2-year) Treasuries or money-market funds."
        )
    elif ff >= 4.0:
        bond_outlook = (
            "Short-term yields are attractive. Lock in rates with 3–12 month "
            "T-bills or high-yield savings rather than extending duration."
        )
    elif ff <= 1.5:
        bond_outlook = (
            "Low rates make bonds unattractive on a real return basis. "
            "Consider shorter maturities or inflation-linked bonds."
        )
    else:
        bond_outlook = (
            "Intermediate bonds offer reasonable real yields. "
            "A balanced duration (3–7 years) is appropriate."
        )

    # ── Equity outlook ────────────────────────────────────────────────────────
    if regime == "risk_on":
        equity_outlook = (
            "Equities are well-supported. Low rates and healthy growth "
            "favour broad index exposure and growth-oriented sectors."
        )
    elif regime == "cautious":
        equity_outlook = (
            "Mixed signals warrant balance. Tilt toward quality — "
            "profitable companies with strong balance sheets — and reduce "
            "speculative / high-multiple exposure."
        )
    elif regime == "risk_off":
        equity_outlook = (
            "High inflation and tight money compress valuations. "
            "Value sectors (energy, financials, consumer staples) tend to "
            "outperform growth in this environment."
        )
    else:  # recession_warning
        equity_outlook = (
            "Defensive positioning is prudent. Reduce equity concentration, "
            "particularly cyclical stocks. Defensive sectors (utilities, "
            "healthcare, staples) and dividend-payers tend to hold up better."
        )

    # ── Debt urgency ──────────────────────────────────────────────────────────
    if ff >= 4.5:
        debt_urgency = "high"
        debt_note    = "Variable-rate debt is expensive — pay it down aggressively."
    elif ff >= 2.5:
        debt_urgency = "moderate"
        debt_note    = "Moderate rates — prioritise high-interest debt above investing."
    else:
        debt_urgency = "low"
        debt_note    = "Low rates reduce debt urgency — investing may outperform early payoff."

    # ── Real rate note ────────────────────────────────────────────────────────
    if real_rate > 2.0:
        rr_str = f"+{real_rate:.1f}% (strongly positive — savers are rewarded)"
    elif real_rate > 0:
        rr_str = f"+{real_rate:.1f}% (positive — savings beat inflation)"
    elif real_rate > -1.0:
        rr_str = f"{real_rate:.1f}% (slightly negative — inflation eroding cash)"
    else:
        rr_str = f"{real_rate:.1f}% (negative — holding cash loses purchasing power)"

    # ── One-line summary ──────────────────────────────────────────────────────
    if regime == "risk_on":
        summary = "Deploy capital into growth assets — conditions are supportive."
    elif regime == "cautious":
        summary = "Stay balanced: maintain liquidity while keeping growth exposure."
    elif regime == "risk_off":
        summary = "Protect purchasing power: TIPS, short bonds, and debt paydown."
    else:
        summary = "Prioritise safety: shore up your emergency fund and cut debt."

    return {
        "savings_rate_attractiveness": savings_attr,
        "bond_outlook":                bond_outlook,
        "equity_outlook":              equity_outlook,
        "debt_urgency":                debt_urgency,
        "debt_note":                   debt_note,
        "real_rate":                   rr_str,
        "summary_line":                summary,
    }

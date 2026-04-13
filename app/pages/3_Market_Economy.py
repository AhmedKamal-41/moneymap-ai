"""
Market & Economy — Step 3
Live macro indicators, regime detection, yield curve, and investment guidance.
"""
from __future__ import annotations

import sys
import os

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
_app_dir = os.path.join(_root, "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from page_guards import require_mode, require_raw_data
from src.analysis.market_analyzer import (
    get_macro_summary,
    regime_description,
    rate_environment_advice,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Market & Economy | MoneyMap AI",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark theme CSS ────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] { background-color: #0e1117; }
    [data-testid="stSidebar"]          { background-color: #161b22; }
    [data-testid="stMetric"]           { background-color: #161b22;
                                         border: 1px solid #30363d;
                                         border-radius: 10px;
                                         padding: 0.9rem 1.1rem; }
    [data-testid="stMetricLabel"]      { color: #8b949e !important; font-size: 0.82rem; }
    [data-testid="stMetricValue"]      { color: #e6edf3 !important; }
    .section-header {
        font-size: 1.05rem; font-weight: 700; color: #e6edf3;
        margin-top: 1.5rem; margin-bottom: 0.4rem;
        padding-bottom: 0.35rem; border-bottom: 1px solid #30363d;
    }
    .regime-badge {
        border-radius: 10px; padding: 1rem 1.5rem;
        margin: 0.75rem 0 1rem;
    }
    .advice-card {
        background-color: #161b22; border: 1px solid #30363d;
        border-radius: 10px; padding: 1rem 1.25rem; height: 100%;
    }
    .advice-label { color: #8b949e; font-size: 0.78rem; font-weight: 600;
                    text-transform: uppercase; letter-spacing: 0.05em; }
    .advice-value { color: #e6edf3; font-size: 1.0rem; font-weight: 700;
                    margin: 0.2rem 0 0.5rem; }
    .advice-body  { color: #8b949e; font-size: 0.85rem; line-height: 1.5; }
    .fallback-note { background-color: #1c2128; border: 1px solid #d29922;
                     border-radius: 8px; padding: 0.5rem 1rem;
                     color: #d29922; font-size: 0.82rem; }
    div[data-testid="stHorizontalBlock"] > div { gap: 0.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

require_mode()
require_raw_data()

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "bg":      "#0e1117",
    "surface": "#161b22",
    "border":  "#30363d",
    "text":    "#e6edf3",
    "muted":   "#8b949e",
    "blue":    "#1f6feb",
    "green":   "#3fb950",
    "red":     "#f85149",
    "yellow":  "#d29922",
    "orange":  "#db6d28",
    "purple":  "#a371f7",
}

_REGIME_COLORS = {
    "risk_on":          C["green"],
    "cautious":         C["yellow"],
    "risk_off":         C["orange"],
    "recession_warning": C["red"],
}
_REGIME_LABELS = {
    "risk_on":          "RISK ON",
    "cautious":         "CAUTIOUS",
    "risk_off":         "RISK OFF",
    "recession_warning": "RECESSION WARNING",
}

_PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor=C["bg"],
    plot_bgcolor=C["surface"],
    font=dict(color=C["text"], family="Inter, sans-serif", size=12),
    margin=dict(l=16, r=16, t=44, b=16),
    xaxis=dict(gridcolor=C["border"], zerolinecolor=C["border"],
               tickfont=dict(color=C["muted"])),
    yaxis=dict(gridcolor=C["border"], zerolinecolor=C["border"],
               tickfont=dict(color=C["muted"])),
    legend=dict(orientation="h", x=0, y=1.08,
                font=dict(color=C["muted"]),
                bgcolor="rgba(0,0,0,0)"),
)


# ── Data fetch (cached for 1 hour) ───────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_fred() -> dict:
    """Fetch the macro dashboard from FRED — cached 1 hr; sample bundle if unavailable."""
    from src.api_clients.fred_client import FREDClient

    return FREDClient().get_macro_dashboard()


# ── Chart builders ────────────────────────────────────────────────────────────

def _yield_curve_chart(t10_df: pd.DataFrame, t2_df: pd.DataFrame,
                        spread_df: pd.DataFrame) -> go.Figure:
    """
    Dual-line chart of 10-Year vs 2-Year Treasury yields.
    Periods where 10Y < 2Y (yield curve inverted) are highlighted in red.
    """
    t10 = t10_df["value"].dropna() if "value" in t10_df.columns else pd.Series(dtype=float)
    t2 = t2_df["value"].dropna() if "value" in t2_df.columns else pd.Series(dtype=float)
    spr = spread_df["value"].dropna() if "value" in spread_df.columns else pd.Series(dtype=float)

    if t10.empty and t2.empty:
        fig = go.Figure()
        fig.update_layout(
            **_PLOTLY_BASE,
            title=dict(
                text="Yield Curve — no Treasury yield data available",
                font=dict(color=C["muted"], size=13),
                x=0,
            ),
            height=340,
            annotations=[
                dict(
                    text="Connect FRED or check your API key",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(color=C["muted"], size=13),
                )
            ],
        )
        return fig

    # Build inversion zones as vertical rect shapes
    inverted = spr < 0 if len(spr) else pd.Series(dtype=bool)
    shapes = []
    zone_start = None
    for i, (dt, is_inv) in enumerate(inverted.items()):
        if is_inv and zone_start is None:
            zone_start = dt
        elif not is_inv and zone_start is not None:
            shapes.append(dict(
                type="rect", xref="x", yref="paper",
                x0=str(zone_start), x1=str(dt),
                y0=0, y1=1,
                fillcolor="rgba(248,81,73,0.12)",
                line=dict(width=0),
                layer="below",
            ))
            zone_start = None
    if zone_start is not None and len(spr):
        shapes.append(dict(
            type="rect", xref="x", yref="paper",
            x0=str(zone_start), x1=str(spr.index[-1]),
            y0=0, y1=1,
            fillcolor="rgba(248,81,73,0.12)",
            line=dict(width=0),
            layer="below",
        ))

    # Invisible trace for inversion legend entry (only if zones exist)
    fig = go.Figure()
    if shapes:
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, color="rgba(248,81,73,0.40)", symbol="square"),
            name="Yield curve inverted",
            showlegend=True,
        ))

    fig.add_trace(go.Scatter(
        x=t10.index, y=t10.values,
        name="10-Year Treasury",
        mode="lines",
        line=dict(color=C["blue"], width=2),
        hovertemplate="%{x|%b %Y}<br><b>10Y: %{y:.2f}%</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=t2.index, y=t2.values,
        name="2-Year Treasury",
        mode="lines",
        line=dict(color=C["orange"], width=2),
        hovertemplate="%{x|%b %Y}<br><b>2Y: %{y:.2f}%</b><extra></extra>",
    ))

    layout = {**_PLOTLY_BASE}
    layout["shapes"] = shapes
    layout["title"] = dict(text="Yield Curve — 10Y vs 2Y Treasury",
                            font=dict(color=C["muted"], size=13), x=0)
    layout["height"] = 340
    layout["xaxis"] = {**_PLOTLY_BASE["xaxis"], "type": "date"}
    layout["yaxis"] = {**_PLOTLY_BASE["yaxis"],
                       "title": dict(text="Yield (%)", font=dict(color=C["muted"])),
                       "ticksuffix": "%"}
    layout["hovermode"] = "x unified"
    fig.update_layout(**layout)
    return fig


def _inflation_rates_chart(cpi_df: pd.DataFrame, ff_df: pd.DataFrame) -> go.Figure:
    """
    Dual-axis line chart: CPI YoY (left) vs Fed Funds Rate (right).
    Fed Funds is resampled to monthly to align with the monthly CPI series.
    """
    cpi = cpi_df["value"].dropna()
    # Resample daily fed funds to monthly-end to match CPI cadence
    ff_monthly = ff_df["value"].dropna().resample("ME").last()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # CPI YoY — primary axis (left)
    fig.add_trace(
        go.Scatter(
            x=cpi.index, y=cpi.values,
            name="CPI YoY Inflation",
            mode="lines",
            line=dict(color=C["red"], width=2),
            hovertemplate="%{x|%b %Y}<br><b>CPI: %{y:.1f}%</b><extra></extra>",
        ),
        secondary_y=False,
    )

    # Fed Funds — secondary axis (right)
    fig.add_trace(
        go.Scatter(
            x=ff_monthly.index, y=ff_monthly.values,
            name="Fed Funds Rate",
            mode="lines",
            line=dict(color=C["blue"], width=2, dash="dot"),
            hovertemplate="%{x|%b %Y}<br><b>Fed Funds: %{y:.2f}%</b><extra></extra>",
        ),
        secondary_y=True,
    )

    # Horizontal reference: 2% inflation target
    fig.add_hline(
        y=2.0, secondary_y=False,
        line=dict(color=C["green"], width=1, dash="dash"),
        annotation_text="2% target",
        annotation_font=dict(color=C["green"], size=10),
        annotation_position="top right",
    )

    fig.update_layout(
        **_PLOTLY_BASE,
        title=dict(text="Inflation vs Fed Funds Rate",
                   font=dict(color=C["muted"], size=13), x=0),
        height=340,
        hovermode="x unified",
    )
    fig.update_yaxes(
        title_text="CPI YoY (%)",
        title_font=dict(color=C["muted"]),
        ticksuffix="%",
        tickfont=dict(color=C["muted"]),
        gridcolor=C["border"],
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="Fed Funds (%)",
        title_font=dict(color=C["muted"]),
        ticksuffix="%",
        tickfont=dict(color=C["muted"]),
        gridcolor="rgba(0,0,0,0)",  # hide right-axis gridlines
        secondary_y=True,
    )
    fig.update_xaxes(
        gridcolor=C["border"],
        tickfont=dict(color=C["muted"]),
        type="date",
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Helpers for delta formatting in metric cards
# ─────────────────────────────────────────────────────────────────────────────

def _delta_str(current, past, suffix="%", precision=2) -> str | None:
    if current is None or past is None:
        return None
    delta = current - past
    sign  = "+" if delta >= 0 else ""
    return f"{sign}{delta:.{precision}f}{suffix} vs 6 mo ago"


def _fmt_rate(v: float | None, suffix="%", decimals=2) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}{suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    "<h2 style='color:#e6edf3; margin-bottom:0;'>🌐 Market & Economy</h2>"
    "<p style='color:#8b949e; margin-top:0.2rem;'>Macro indicators (FRED when configured; "
    "otherwise deterministic sample data) · Cached 1 hour</p>",
    unsafe_allow_html=True,
)

# ── Fetch data (FREDClient returns sample series when live FRED is unavailable) ──
with st.spinner("Fetching macro data from FRED…"):
    try:
        fred_data = _fetch_fred()
    except Exception as exc:
        st.warning(
            f"Macro data fetch raised an unexpected error ({exc}). "
            "Loading deterministic demonstration series so charts still render.",
            icon="⚠️",
        )
        from src.api_clients.fred_client import sample_macro_dashboard

        fred_data = sample_macro_dashboard()

summary = get_macro_summary(fred_data)
st.session_state["macro"] = dict(summary)

# Notice when live FRED data is not available (includes built-in sample from API client)
if summary.get("is_fallback"):
    st.markdown(
        "<div class='fallback-note'>"
        "<b>Demonstration macro data</b> — live FRED series are not in use "
        "(missing <code>FRED_API_KEY</code>, network/API error, or cached exception above). "
        "Charts below use deterministic <b>sample</b> values, not real market prints. "
        "Configure your key for production-style analysis."
        "</div><br>",
        unsafe_allow_html=True,
    )

# ── Metric cards ──────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    ff   = summary["current_fed_rate"]
    ff6  = summary["rate_6mo_ago"]
    st.metric(
        "Fed Funds Rate",
        _fmt_rate(ff),
        delta=_delta_str(ff, ff6),
        delta_color="inverse",   # rising rates = bad for most people
    )

with c2:
    inf  = summary["current_inflation"]
    inf6 = summary["inflation_6mo_ago"]
    st.metric(
        "CPI Inflation (YoY)",
        _fmt_rate(inf, decimals=1),
        delta=_delta_str(inf, inf6, precision=1),
        delta_color="inverse",
    )

with c3:
    un   = summary["current_unemployment"]
    un6  = summary["unemployment_6mo_ago"]
    st.metric(
        "Unemployment",
        _fmt_rate(un, decimals=1),
        delta=_delta_str(un, un6, precision=1),
        delta_color="inverse",
    )

with c4:
    spr = summary["yield_spread"]
    inv = summary["yield_inverted"]
    spr_str = _fmt_rate(spr, decimals=2) if spr is not None else "N/A"
    if inv:
        spr_str += " (inverted)"
    st.metric(
        "10Y–2Y Spread",
        spr_str,
        delta="Inverted — recession signal" if inv else None,
        delta_color="inverse" if inv else "normal",
    )

with c5:
    ytd = summary["sp500_ytd_return"]
    ytd_str = (f"{ytd:+.1f}%" if ytd is not None else "N/A")
    st.metric(
        "S&P 500 YTD",
        ytd_str,
        delta_color="normal",
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Regime badge ──────────────────────────────────────────────────────────────
regime     = summary["regime"]
reg_color  = _REGIME_COLORS.get(regime, C["muted"])
reg_label  = _REGIME_LABELS.get(regime, regime.upper())
reg_desc   = regime_description(regime)

st.markdown(
    f"<div class='regime-badge' style='background-color:{reg_color}18; "
    f"border:1px solid {reg_color}55;'>"
    f"<span style='background:{reg_color}; color:#fff; padding:0.2rem 0.7rem; "
    f"border-radius:6px; font-size:0.78rem; font-weight:700; "
    f"letter-spacing:0.08em;'>{reg_label}</span>"
    f"<p style='color:#e6edf3; margin: 0.6rem 0 0; font-size:0.93rem; "
    f"line-height:1.6;'>{reg_desc}</p>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Charts ────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2, gap="large")

with col_left:
    st.markdown('<p class="section-header">Yield Curve</p>', unsafe_allow_html=True)
    try:
        fig_yc = _yield_curve_chart(
            fred_data["t10yr"],
            fred_data["t2yr"],
            fred_data["yield_spread"],
        )
        st.plotly_chart(fig_yc, width='stretch')
    except Exception as exc:
        st.warning(f"Could not render yield curve chart: {exc}")

with col_right:
    st.markdown('<p class="section-header">Inflation vs Fed Funds Rate</p>',
                unsafe_allow_html=True)
    try:
        fig_inf = _inflation_rates_chart(fred_data["cpi_yoy"], fred_data["fed_funds"])
        st.plotly_chart(fig_inf, width='stretch')
    except Exception as exc:
        st.warning(f"Could not render inflation chart: {exc}")

st.markdown("<br>", unsafe_allow_html=True)

# ── What this means for you ───────────────────────────────────────────────────
advice = rate_environment_advice(
    fed_rate=summary["current_fed_rate"],
    inflation=summary["current_inflation"],
    regime=regime,
)

st.markdown('<p class="section-header">What This Means for You</p>',
            unsafe_allow_html=True)

# Summary banner
_bg   = C["surface"]
_muted = C["muted"]
_text  = C["text"]
st.markdown(
    f"<div style='background:{_bg}; border:1px solid {reg_color}44; "
    f"border-left:4px solid {reg_color}; border-radius:8px; "
    f"padding:0.75rem 1.25rem; margin-bottom:1rem;'>"
    f"<span style='color:{_muted}; font-size:0.8rem;'>ACTION SUMMARY</span><br>"
    f"<span style='color:{_text}; font-size:1.0rem; font-weight:600;'>"
    f"{advice['summary_line']}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

a1, a2, a3, a4 = st.columns(4)

_ATTRACT_COLOR = {"high": C["green"], "moderate": C["yellow"], "low": C["red"]}
_URGENCY_COLOR = {"high": C["red"],   "moderate": C["yellow"], "low": C["green"]}

with a1:
    attr = advice["savings_rate_attractiveness"]
    attr_color = _ATTRACT_COLOR.get(attr, C["muted"])
    st.markdown(
        f"<div class='advice-card'>"
        f"<div class='advice-label'>Savings Rate</div>"
        f"<div class='advice-value' style='color:{attr_color};'>"
        f"{attr.upper()} attractiveness</div>"
        f"<div class='advice-body'>Real rate: {advice['real_rate']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

with a2:
    urg = advice["debt_urgency"]
    urg_color = _URGENCY_COLOR.get(urg, C["muted"])
    st.markdown(
        f"<div class='advice-card'>"
        f"<div class='advice-label'>Debt Urgency</div>"
        f"<div class='advice-value' style='color:{urg_color};'>"
        f"{urg.upper()} priority</div>"
        f"<div class='advice-body'>{advice['debt_note']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

with a3:
    _blue = C["blue"]
    st.markdown(
        f"<div class='advice-card'>"
        f"<div class='advice-label'>Bond Outlook</div>"
        f"<div class='advice-value' style='color:{_blue};'>Fixed Income</div>"
        f"<div class='advice-body'>{advice['bond_outlook']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

with a4:
    eq_color = (
        C["green"]  if regime == "risk_on"
        else C["red"]    if regime == "recession_warning"
        else C["yellow"]
    )
    st.markdown(
        f"<div class='advice-card'>"
        f"<div class='advice-label'>Equity Outlook</div>"
        f"<div class='advice-value' style='color:{eq_color};'>Equities</div>"
        f"<div class='advice-body'>{advice['equity_outlook']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Direction indicators table ────────────────────────────────────────────────
st.markdown('<p class="section-header">Trend Directions (vs 6 months ago)</p>',
            unsafe_allow_html=True)

_DIR_ICON  = {"rising": "↑", "falling": "↓", "flat": "→"}
_DIR_COLOR = {
    "fed_rate_direction":      {"rising": C["red"], "falling": C["green"], "flat": C["muted"]},
    "inflation_direction":     {"rising": C["red"], "falling": C["green"], "flat": C["muted"]},
    "unemployment_direction":  {"rising": C["red"], "falling": C["green"], "flat": C["muted"]},
}

trend_rows = [
    ("Fed Funds Rate",  "fed_rate_direction",     summary["current_fed_rate"],    summary["rate_6mo_ago"]),
    ("CPI Inflation",   "inflation_direction",     summary["current_inflation"],   summary["inflation_6mo_ago"]),
    ("Unemployment",    "unemployment_direction",  summary["current_unemployment"],summary["unemployment_6mo_ago"]),
]

_csurface = C["surface"]
_cborder  = C["border"]
_cmuted   = C["muted"]
_ctext    = C["text"]

trend_cols = st.columns(3)
for col, (label, dir_key, curr, past) in zip(trend_cols, trend_rows):
    direction = summary.get(dir_key, "flat")
    icon      = _DIR_ICON[direction]
    color     = _DIR_COLOR[dir_key][direction]
    delta_val = _delta_str(curr, past)
    curr_str  = _fmt_rate(curr) if curr is not None else "N/A"
    dir_title = direction.title()
    with col:
        st.markdown(
            f"<div style='background:{_csurface}; border:1px solid {_cborder}; "
            f"border-radius:10px; padding:0.75rem 1rem;'>"
            f"<div style='color:{_cmuted}; font-size:0.78rem;'>{label}</div>"
            f"<div style='font-size:1.4rem; font-weight:700; color:{_ctext};'>"
            f"{curr_str}"
            f"  <span style='font-size:1.1rem; color:{color};'>{icon} {dir_title}</span>"
            f"</div>"
            f"<div style='color:{_cmuted}; font-size:0.8rem; margin-top:0.2rem;'>"
            f"{delta_val or 'No prior data'}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ── Navigation ────────────────────────────────────────────────────────────────
st.divider()
if st.button("Continue →  Scenario Lab", type="primary"):
    st.switch_page("pages/4_Scenario_Lab.py")

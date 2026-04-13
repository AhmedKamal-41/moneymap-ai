"""
Scenario Lab — Step 4
Interactive 12-month financial projections with Monte Carlo confidence bands,
base / upside / downside scenarios, and one-at-a-time sensitivity analysis.
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
import numpy as np
import pandas as pd

from page_guards import require_mode, require_raw_data
from src.analysis.scenario_engine import (
    build_scenarios,
    sensitivity_analysis,
    SCENARIO_META,
)
from src.utils.formatting import fmt_currency

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Scenario Lab | MoneyMap AI",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Dark theme CSS ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] { background-color: #0e1117; }
    [data-testid="stSidebar"]          { background-color: #161b22; }
    [data-testid="stMetric"]           { background-color: #161b22;
                                         border: 1px solid #30363d;
                                         border-radius: 10px;
                                         padding: 0.8rem 1rem; }
    [data-testid="stMetricLabel"]      { color: #8b949e !important; font-size: 0.8rem; }
    [data-testid="stMetricValue"]      { color: #e6edf3 !important; }
    .section-header {
        font-size: 1.05rem; font-weight: 700; color: #e6edf3;
        margin: 1.2rem 0 0.4rem;
        padding-bottom: 0.3rem; border-bottom: 1px solid #30363d;
    }
    .slider-section { color: #8b949e; font-size: 0.78rem; font-weight: 700;
                      text-transform: uppercase; letter-spacing: 0.06em;
                      margin: 1rem 0 0.4rem; }
    .outcome-card { background: #161b22; border: 1px solid #30363d;
                    border-radius: 10px; padding: 0.9rem 1.1rem; }
    .stSlider > label { color: #8b949e !important; font-size: 0.82rem; }
    div[data-testid="stHorizontalBlock"] > div { gap: 0.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

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
}

_PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor=C["bg"],
    plot_bgcolor=C["surface"],
    font=dict(color=C["text"], family="Inter, sans-serif", size=12),
    margin=dict(l=16, r=16, t=44, b=16),
    hovermode="x unified",
)

_AXIS_BASE = dict(
    gridcolor=C["border"], zerolinecolor=C["border"],
    tickfont=dict(color=C["muted"]),
)

require_mode()
require_raw_data()

# ─────────────────────────────────────────────────────────────────────────────
# Session state defaults
# ─────────────────────────────────────────────────────────────────────────────

mode: str = st.session_state["mode"]
raw_df = st.session_state["raw_df"]

# Try to derive defaults from uploaded data; fall back gracefully
_defaults_personal = {
    "monthly_income":    5_500.0,
    "monthly_expenses":  4_500.0,
    "savings":          13_000.0,
    "debt_balance":     15_000.0,
    "debt_rate":             0.07,
    "portfolio_value":  25_000.0,
    "expected_return":       0.08,
    "volatility":            0.15,
}
_defaults_business = {
    "monthly_revenue":  47_000.0,
    "monthly_expenses": 40_000.0,
    "cash_balance":     88_000.0,
    "debt_balance":     50_000.0,
    "growth_rate":           0.10,
    "marketing_budget":  5_000.0,
}

try:
    if mode == "personal":
        from src.data_loader import parse_personal_csv
        from src.analysis.financial_health import analyze_personal_health
        parsed = parse_personal_csv(raw_df)
        h = analyze_personal_health(parsed)
        _defaults_personal["monthly_income"]   = h["monthly_income"]
        _defaults_personal["monthly_expenses"]  = h["monthly_expenses"]
        _defaults_personal["savings"]           = max(h["net_cash"], 0.0)
    else:
        from src.data_loader import parse_business_csv
        from src.analysis.financial_health import analyze_business_health
        parsed = parse_business_csv(raw_df)
        h = analyze_business_health(parsed)
        _defaults_business["monthly_revenue"]   = h["monthly_revenue"]
        _defaults_business["monthly_expenses"]   = h["monthly_expenses"]
        _defaults_business["cash_balance"]       = max(h["net_income"], 0.0)
except Exception:
    pass  # stick with sample defaults


# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    "<h2 style='color:#e6edf3; margin-bottom:0;'>🔬 Scenario Lab</h2>"
    "<p style='color:#8b949e; margin-top:0.2rem;'>"
    "Adjust assumptions below and see how your financial position changes "
    "over 12 months across three scenarios — with Monte Carlo confidence bands."
    "</p>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Two-column layout: sliders (left) | charts (right)
# ─────────────────────────────────────────────────────────────────────────────

left, right = st.columns([1, 2.6], gap="large")

# ─────────────────────────────────────────────────────────────────────────────
# LEFT COLUMN — Sliders
# ─────────────────────────────────────────────────────────────────────────────

with left:
    st.markdown('<p class="section-header">Scenario Assumptions</p>',
                unsafe_allow_html=True)

    if mode == "personal":
        d = _defaults_personal

        st.markdown('<p class="slider-section">Income & Expenses</p>',
                    unsafe_allow_html=True)
        monthly_income = st.slider(
            "Monthly Income ($)",
            min_value=int(d["monthly_income"] * 0.5),
            max_value=int(d["monthly_income"] * 1.5),
            value=int(d["monthly_income"]),
            step=100,
        )
        monthly_expenses = st.slider(
            "Monthly Expenses ($)",
            min_value=int(d["monthly_expenses"] * 0.5),
            max_value=int(d["monthly_expenses"] * 1.5),
            value=int(d["monthly_expenses"]),
            step=100,
        )

        st.markdown('<p class="slider-section">Assets & Savings</p>',
                    unsafe_allow_html=True)
        savings = st.slider(
            "Current Savings / Emergency Fund ($)",
            min_value=0,
            max_value=int(max(d["savings"] * 3, 50_000)),
            value=int(d["savings"]),
            step=500,
        )
        emergency_fund_months = st.slider(
            "Emergency Fund Target (months)",
            min_value=1, max_value=12, value=3,
            help="How many months of expenses you want in liquid savings.",
        )

        st.markdown('<p class="slider-section">Investments</p>',
                    unsafe_allow_html=True)
        portfolio_value = st.slider(
            "Investment Portfolio Value ($)",
            min_value=0,
            max_value=int(max(d["portfolio_value"] * 3, 200_000)),
            value=int(d["portfolio_value"]),
            step=1_000,
        )
        expected_return_pct = st.slider(
            "Expected Annual Return (%)",
            min_value=0.0, max_value=15.0,
            value=float(d["expected_return"] * 100),
            step=0.5,
        )
        inflation_pct = st.slider(
            "Inflation Rate (%)",
            min_value=0.0, max_value=8.0, value=3.0, step=0.25,
            help="Used to compute the real return on your portfolio.",
        )

        st.markdown('<p class="slider-section">Debt</p>',
                    unsafe_allow_html=True)
        debt_balance = st.slider(
            "Total Debt Balance ($)",
            min_value=0,
            max_value=int(max(d["debt_balance"] * 3, 100_000)),
            value=int(d["debt_balance"]),
            step=500,
        )
        debt_rate_pct = st.slider(
            "Debt Interest Rate (%)",
            min_value=0.0, max_value=30.0,
            value=float(d["debt_rate"] * 100),
            step=0.25,
        )

        base_params = {
            "monthly_income":    float(monthly_income),
            "monthly_expenses":  float(monthly_expenses),
            "savings":           float(savings),
            "debt_balance":      float(debt_balance),
            "debt_rate":         debt_rate_pct / 100.0,
            "portfolio_value":   float(portfolio_value),
            "expected_return":   expected_return_pct / 100.0,
            "volatility":        0.15,
        }

        # Derived display values
        ef_target_cash = monthly_expenses * emergency_fund_months
        ef_gap         = ef_target_cash - savings
        real_return    = expected_return_pct - inflation_pct
        monthly_debt_cost = debt_balance * (debt_rate_pct / 100) / 12

        st.markdown("<hr style='border-color:#30363d; margin:1rem 0 0.75rem;'>",
                    unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:0.82rem; color:{C['muted']}; line-height:1.8;'>"
            f"<b style='color:{C['text']};'>Net cash/mo:</b> "
            f"{fmt_currency(monthly_income - monthly_expenses)}<br>"
            f"<b style='color:{C['text']};'>Monthly debt cost:</b> "
            f"{fmt_currency(monthly_debt_cost)}<br>"
            f"<b style='color:{C['text']};'>Real return:</b> {real_return:+.1f}%<br>"
            f"<b style='color:{C['text']};'>EF gap:</b> "
            f"{'On track' if ef_gap <= 0 else fmt_currency(ef_gap) + ' short'}"
            f"</div>",
            unsafe_allow_html=True,
        )

    else:  # business
        d = _defaults_business

        st.markdown('<p class="slider-section">Revenue & Growth</p>',
                    unsafe_allow_html=True)
        monthly_revenue = st.slider(
            "Monthly Revenue ($)",
            min_value=int(d["monthly_revenue"] * 0.5),
            max_value=int(d["monthly_revenue"] * 1.5),
            value=int(d["monthly_revenue"]),
            step=1_000,
        )
        growth_rate_pct = st.slider(
            "Revenue Growth Rate (% / year)",
            min_value=-30, max_value=50,
            value=int(d["growth_rate"] * 100),
            step=1,
        )

        st.markdown('<p class="slider-section">Expenses</p>',
                    unsafe_allow_html=True)
        monthly_expenses = st.slider(
            "Monthly Expenses ($)",
            min_value=int(d["monthly_expenses"] * 0.5),
            max_value=int(d["monthly_expenses"] * 1.5),
            value=int(d["monthly_expenses"]),
            step=1_000,
        )
        expense_growth_pct = st.slider(
            "Expense Growth Rate (% / year)",
            min_value=-10, max_value=30, value=5, step=1,
        )
        marketing_budget = st.slider(
            "Marketing Budget ($/mo)",
            min_value=0,
            max_value=int(max(d["marketing_budget"] * 4, 40_000)),
            value=int(d["marketing_budget"]),
            step=500,
        )

        st.markdown('<p class="slider-section">Cash & Debt</p>',
                    unsafe_allow_html=True)
        cash_balance = st.slider(
            "Current Cash Balance ($)",
            min_value=0,
            max_value=int(max(d["cash_balance"] * 3, 300_000)),
            value=int(d["cash_balance"]),
            step=5_000,
        )
        hiring_cost = st.slider(
            "New Hire Monthly Cost ($/mo per hire)",
            min_value=0, max_value=20_000, value=0, step=500,
            help="Added to monthly expenses.",
        )
        inventory_investment = st.slider(
            "Inventory Investment ($/mo)",
            min_value=0, max_value=50_000, value=0, step=1_000,
            help="Added to monthly expenses.",
        )

        total_expenses = monthly_expenses + hiring_cost + inventory_investment
        base_params = {
            "monthly_revenue":   float(monthly_revenue),
            "monthly_expenses":  float(total_expenses),
            "cash_balance":      float(cash_balance),
            "debt_balance":      float(d["debt_balance"]),
            "growth_rate":       growth_rate_pct / 100.0,
            "marketing_budget":  float(marketing_budget),
        }

        burn = total_expenses - monthly_revenue
        runway = (cash_balance / burn) if burn > 0 else None

        st.markdown("<hr style='border-color:#30363d; margin:1rem 0 0.75rem;'>",
                    unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:0.82rem; color:{C['muted']}; line-height:1.8;'>"
            f"<b style='color:{C['text']};'>Net/mo (base):</b> "
            f"{fmt_currency(monthly_revenue - total_expenses)}<br>"
            f"<b style='color:{C['text']};'>Burn rate:</b> "
            f"{fmt_currency(burn) if burn > 0 else 'Profitable'}/mo<br>"
            f"<b style='color:{C['text']};'>Runway (base):</b> "
            f"{f'{runway:.1f} mo' if runway and runway < 999 else 'Profitable'}"
            f"</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN — Charts and outcomes
# ─────────────────────────────────────────────────────────────────────────────

with right:

    # ── Run scenarios ─────────────────────────────────────────────────────────
    with st.spinner("Running simulations…"):
        try:
            scenarios = build_scenarios(base_params, mode)
            st.session_state["scenarios"] = scenarios
            st.session_state["scenario_params"] = base_params
        except Exception as exc:
            st.error(f"Simulation failed: {exc}")
            st.stop()

    # ── Outcome metric cards ──────────────────────────────────────────────────
    base_s = scenarios["base"]
    down_s = scenarios["downside"]
    up_s   = scenarios["upside"]

    label_cash = "12-Mo Ending Cash" if mode == "personal" else "12-Mo Cash Balance"

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric(f"Base — {label_cash}", fmt_currency(base_s["median_outcome"]))
    with mc2:
        st.metric("Upside", fmt_currency(up_s["median_outcome"]))
    with mc3:
        st.metric("Downside", fmt_currency(down_s["median_outcome"]))
    with mc4:
        prob = down_s["probability_of_negative"]
        st.metric(
            "Risk of Cash Shortfall",
            f"{prob * 100:.1f}%",
            delta="Downside scenario" if prob > 0 else None,
            delta_color="off",
        )

    # ── Three-panel scenario trajectory chart ────────────────────────────────
    st.markdown('<p class="section-header">12-Month Cash Projection — All Scenarios</p>',
                unsafe_allow_html=True)

    _scenario_order = [
        ("base",     scenarios["base"]),
        ("upside",   scenarios["upside"]),
        ("downside", scenarios["downside"]),
    ]

    fig_scenario = make_subplots(
        rows=1, cols=3,
        subplot_titles=[SCENARIO_META[k]["label"] for k, _ in _scenario_order],
        shared_yaxes=True,
        horizontal_spacing=0.04,
    )

    for col_idx, (key, sdata) in enumerate(_scenario_order, start=1):
        meta   = SCENARIO_META[key]
        months = sdata["months"]
        pp     = sdata["percentile_paths"]

        p5  = pp["p5"].tolist()
        p25 = pp["p25"].tolist()
        p50 = pp["p50"].tolist()
        p75 = pp["p75"].tolist()
        p95 = pp["p95"].tolist()

        color = meta["color"]
        band  = meta["band"]
        # Derive a slightly denser fill for the inner (P25-P75) band
        inner_band = band.replace("0.13)", "0.26)")

        # ── P5–P95 outer band ────────────────────────────────────────────────
        fig_scenario.add_trace(go.Scatter(
            x=months, y=p95,
            mode="lines",
            line=dict(color="rgba(0,0,0,0)", width=0),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=col_idx)
        fig_scenario.add_trace(go.Scatter(
            x=months, y=p5,
            fill="tonexty", fillcolor=band,
            mode="lines",
            line=dict(color="rgba(0,0,0,0)", width=0),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=col_idx)

        # ── P25–P75 inner band ───────────────────────────────────────────────
        fig_scenario.add_trace(go.Scatter(
            x=months, y=p75,
            mode="lines",
            line=dict(color="rgba(0,0,0,0)", width=0),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=col_idx)
        fig_scenario.add_trace(go.Scatter(
            x=months, y=p25,
            fill="tonexty", fillcolor=inner_band,
            mode="lines",
            line=dict(color="rgba(0,0,0,0)", width=0),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=col_idx)

        # ── Median line ──────────────────────────────────────────────────────
        fig_scenario.add_trace(go.Scatter(
            x=months, y=p50,
            mode="lines",
            name=meta["label"],
            line=dict(color=color, width=2.5),
            showlegend=False,
            hovertemplate=(
                f"Month %{{x}}<br>"
                f"<b>{meta['label']} median: %{{y:$,.0f}}</b>"
                f"<extra></extra>"
            ),
        ), row=1, col=col_idx)

        # ── Zero reference line ──────────────────────────────────────────────
        fig_scenario.add_hline(
            y=0,
            line=dict(color=C["red"], width=1, dash="dot"),
            row=1, col=col_idx,
        )

    fig_scenario.update_layout(
        template="plotly_dark",
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["surface"],
        font=dict(color=C["text"], family="Inter, sans-serif", size=12),
        margin=dict(l=16, r=16, t=56, b=16),
        hovermode="x unified",
        showlegend=False,
        height=360,
        title=dict(
            text="Monte Carlo Fan Chart — P5–P25–P75–P95 Confidence Bands",
            font=dict(color=C["muted"], size=12), x=0,
        ),
    )
    fig_scenario.update_xaxes(
        gridcolor=C["border"], zerolinecolor=C["border"],
        tickfont=dict(color=C["muted"]),
        title_text="Month", title_font=dict(color=C["muted"], size=10),
    )
    fig_scenario.update_yaxes(
        gridcolor=C["border"], zerolinecolor=C["border"],
        tickfont=dict(color=C["muted"]),
        tickprefix="$", tickformat=",.0f",
    )
    # Style auto-generated subplot title annotations
    for ann in fig_scenario.layout.annotations:
        ann.font = dict(color=C["text"], size=13, family="Inter, sans-serif")

    st.plotly_chart(fig_scenario, width='stretch')

    # ── Narrative summary ─────────────────────────────────────────────────────
    months_neg    = down_s.get("months_until_negative")
    prob_neg_pct  = down_s["probability_of_negative"] * 100
    base_med      = base_s["median_outcome"]
    base_p5       = base_s["p5_outcome"]
    base_p95      = base_s["p95_outcome"]

    neg_sentence = ""
    if months_neg is not None and prob_neg_pct > 1:
        neg_sentence = (
            f" In the downside scenario there is a <b>{prob_neg_pct:.0f}%</b> "
            f"chance of a cash shortfall by around month <b>{months_neg:.0f}</b>."
        )
    elif prob_neg_pct < 1:
        neg_sentence = " Even in the downside scenario, cash shortfall is very unlikely."

    st.markdown(
        f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
        f"border-left:4px solid {C['blue']}; border-radius:8px; "
        f"padding:0.7rem 1.1rem; margin-bottom:0.5rem; font-size:0.9rem; "
        f"color:{C['muted']}; line-height:1.7;'>"
        f"In the <b style='color:{C['text']};'>base case</b>, your 12-month ending "
        f"cash is <b style='color:{C['blue']};'>{fmt_currency(base_med)}</b> "
        f"(90% CI: {fmt_currency(base_p5)} to {fmt_currency(base_p95)})."
        f"{neg_sentence}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Portfolio add-on for personal mode — three-panel fan chart
    if mode == "personal" and "portfolio_median" in base_s:
        st.markdown('<p class="section-header">Investment Portfolio — 12-Month Projection</p>',
                    unsafe_allow_html=True)

        _port_order = [
            ("base",     base_s),
            ("upside",   up_s),
            ("downside", down_s),
        ]

        pa, pb, pc = st.columns(3)
        _port_cols = [pa, pb, pc]
        for _pcol, (key, sdata) in zip(_port_cols, _port_order):
            pmed = sdata.get("portfolio_median", 0)
            pp5  = sdata.get("portfolio_p5",    0)
            pp95 = sdata.get("portfolio_p95",   0)
            _color = SCENARIO_META[key]["color"]
            with _pcol:
                st.metric(
                    f"Portfolio — {SCENARIO_META[key]['label']}",
                    fmt_currency(pmed),
                    delta=f"90% CI: {fmt_currency(pp5)} – {fmt_currency(pp95)}",
                    delta_color="off",
                )

        # Fan chart for portfolio paths
        if "portfolio_paths" in base_s:
            fig_port = make_subplots(
                rows=1, cols=3,
                subplot_titles=[SCENARIO_META[k]["label"] for k, _ in _port_order],
                shared_yaxes=True,
                horizontal_spacing=0.04,
            )
            _port_days = list(range(1, len(next(iter(base_s["portfolio_paths"].values()))) + 1))
            for _ci, (key, sdata) in enumerate(_port_order, start=1):
                if "portfolio_paths" not in sdata:
                    continue
                pp   = sdata["portfolio_paths"]
                meta = SCENARIO_META[key]
                band = meta["band"]
                inner_band = band.replace("0.13)", "0.26)")
                color = meta["color"]

                for _upper, _lower, _fill in [
                    ("p95", "p5",  band),
                    ("p75", "p25", inner_band),
                ]:
                    fig_port.add_trace(go.Scatter(
                        x=_port_days, y=pp[_upper].tolist(),
                        mode="lines", line=dict(color="rgba(0,0,0,0)", width=0),
                        showlegend=False, hoverinfo="skip",
                    ), row=1, col=_ci)
                    fig_port.add_trace(go.Scatter(
                        x=_port_days, y=pp[_lower].tolist(),
                        fill="tonexty", fillcolor=_fill,
                        mode="lines", line=dict(color="rgba(0,0,0,0)", width=0),
                        showlegend=False, hoverinfo="skip",
                    ), row=1, col=_ci)

                fig_port.add_trace(go.Scatter(
                    x=_port_days, y=pp["p50"].tolist(),
                    mode="lines",
                    name=meta["label"],
                    line=dict(color=color, width=2.5),
                    showlegend=False,
                    hovertemplate=(
                        f"Day %{{x}}<br>"
                        f"<b>{meta['label']} portfolio: %{{y:$,.0f}}</b>"
                        f"<extra></extra>"
                    ),
                ), row=1, col=_ci)

            fig_port.update_layout(
                template="plotly_dark",
                paper_bgcolor=C["bg"],
                plot_bgcolor=C["surface"],
                font=dict(color=C["text"], family="Inter, sans-serif", size=12),
                margin=dict(l=16, r=16, t=56, b=16),
                hovermode="x unified",
                showlegend=False,
                height=300,
                title=dict(
                    text="Portfolio GBM Simulation — P5–P95 Confidence Bands",
                    font=dict(color=C["muted"], size=12), x=0,
                ),
            )
            fig_port.update_xaxes(
                gridcolor=C["border"], zerolinecolor=C["border"],
                tickfont=dict(color=C["muted"]),
                title_text="Trading Day", title_font=dict(color=C["muted"], size=10),
            )
            fig_port.update_yaxes(
                gridcolor=C["border"], zerolinecolor=C["border"],
                tickfont=dict(color=C["muted"]),
                tickprefix="$", tickformat=",.0f",
            )
            for ann in fig_port.layout.annotations:
                ann.font = dict(color=C["text"], size=13, family="Inter, sans-serif")
            st.plotly_chart(fig_port, width='stretch')

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Sensitivity analysis ──────────────────────────────────────────────────
    st.markdown('<p class="section-header">Sensitivity Analysis</p>',
                unsafe_allow_html=True)

    if mode == "personal":
        sensitivity_options = {
            "Monthly Income":           ("monthly_income",
                                         np.linspace(monthly_income * 0.5,
                                                      monthly_income * 1.5, 20)),
            "Monthly Expenses":         ("monthly_expenses",
                                         np.linspace(monthly_expenses * 0.5,
                                                      monthly_expenses * 1.5, 20)),
            "Starting Savings":         ("savings",
                                         np.linspace(0, max(savings * 3, 30_000), 20)),
            "Expected Return (portfolio)": ("expected_return",
                                            np.linspace(0.0, 0.20, 20)),
            "Debt Interest Rate":       ("debt_rate",
                                         np.linspace(0.0, 0.30, 20)),
        }
    else:
        sensitivity_options = {
            "Monthly Revenue":          ("monthly_revenue",
                                         np.linspace(monthly_revenue * 0.5,
                                                      monthly_revenue * 1.5, 20)),
            "Monthly Expenses (total)": ("monthly_expenses",
                                         np.linspace(monthly_expenses * 0.5,
                                                      monthly_expenses * 1.5, 20)),
            "Starting Cash Balance":    ("cash_balance",
                                         np.linspace(0, max(cash_balance * 3, 300_000), 20)),
            "Revenue Growth Rate":      ("growth_rate",
                                         np.linspace(-0.30, 0.50, 20)),
            "Marketing Budget":         ("marketing_budget",
                                         np.linspace(0, max(marketing_budget * 4, 20_000), 20)),
        }

    sa_col1, sa_col2 = st.columns([1, 3])
    with sa_col1:
        selected_var_label = st.selectbox(
            "Variable to analyse",
            list(sensitivity_options.keys()),
            label_visibility="collapsed",
        )

    var_key, var_range = sensitivity_options[selected_var_label]

    @st.cache_data(ttl=300, show_spinner=False)
    def _run_sensitivity(params_frozen: tuple, var_key: str,
                         range_arr: tuple, _mode: str) -> pd.DataFrame:
        p = dict(params_frozen)
        return sensitivity_analysis(p, var_key, list(range_arr), _mode)

    with st.spinner(f"Computing sensitivity for {selected_var_label}…"):
        sa_df = _run_sensitivity(
            tuple(sorted(base_params.items())),
            var_key,
            tuple(var_range.tolist()),
            mode,
        )

    # Sensitivity fan chart
    fig_sa = go.Figure()

    # P5-P95 band
    fig_sa.add_trace(go.Scatter(
        x=sa_df["variable_value"].tolist(),
        y=sa_df["p95_outcome"].tolist(),
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
        name="_p95",
    ))
    fig_sa.add_trace(go.Scatter(
        x=sa_df["variable_value"].tolist(),
        y=sa_df["p5_outcome"].tolist(),
        fill="tonexty",
        fillcolor="rgba(31,111,235,0.13)",
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False,
        hoverinfo="skip",
        name="_p5",
    ))

    # Median outcome line
    fig_sa.add_trace(go.Scatter(
        x=sa_df["variable_value"].tolist(),
        y=sa_df["median_outcome"].tolist(),
        mode="lines+markers",
        name="Median 12-mo outcome",
        line=dict(color=C["blue"], width=2),
        marker=dict(size=5, color=C["blue"]),
        hovertemplate=(
            f"{selected_var_label}: %{{x:,.1f}}<br>"
            "<b>Median outcome: %{y:$,.0f}</b><extra></extra>"
        ),
    ))

    # Current base value marker
    base_val = base_params.get(var_key, var_range[len(var_range) // 2])
    fig_sa.add_vline(
        x=base_val,
        line=dict(color=C["yellow"], width=1.5, dash="dash"),
        annotation_text="current",
        annotation_font=dict(color=C["yellow"], size=10),
        annotation_position="top",
    )

    # P-negative secondary axis (right y-axis)
    fig_sa.add_trace(go.Scatter(
        x=sa_df["variable_value"].tolist(),
        y=(sa_df["p_negative"] * 100).tolist(),
        mode="lines",
        name="Shortfall risk (%)",
        line=dict(color=C["red"], width=1.5, dash="dot"),
        yaxis="y2",
        hovertemplate=(
            f"{selected_var_label}: %{{x:,.1f}}<br>"
            "<b>Shortfall risk: %{y:.1f}%</b><extra></extra>"
        ),
    ))

    # Determine x-axis format ($ for money, % for rates)
    _money_vars = {"monthly_income", "monthly_expenses", "savings", "portfolio_value",
                   "debt_balance", "cash_balance", "monthly_revenue", "marketing_budget",
                   "monthly_revenue", "monthly_expenses"}
    x_fmt = "$,.0f" if var_key in _money_vars else ".2f"

    fig_sa.update_layout(
        **_PLOTLY_BASE,
        title=dict(
            text=f"How {selected_var_label} affects your 12-month outcome",
            font=dict(color=C["muted"], size=12), x=0,
        ),
        height=340,
        xaxis=dict(**_AXIS_BASE,
                   title=dict(text=selected_var_label, font=dict(color=C["muted"])),
                   tickformat=x_fmt),
        yaxis=dict(**_AXIS_BASE,
                   title=dict(text="12-mo Ending Cash", font=dict(color=C["muted"])),
                   tickprefix="$", tickformat=",.0f"),
        yaxis2=dict(
            overlaying="y",
            side="right",
            title=dict(text="Shortfall Risk (%)", font=dict(color=C["red"])),
            ticksuffix="%",
            tickfont=dict(color=C["red"]),
            gridcolor="rgba(0,0,0,0)",
            range=[0, max((sa_df["p_negative"] * 100).max() * 1.3, 10)],
        ),
        legend=dict(orientation="h", x=0, y=1.12,
                    font=dict(color=C["muted"]),
                    bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig_sa, width='stretch')

    # Quick interpretation
    worst_row  = sa_df.loc[sa_df["median_outcome"].idxmin()]
    best_row   = sa_df.loc[sa_df["median_outcome"].idxmax()]
    outcome_range = best_row["median_outcome"] - worst_row["median_outcome"]

    st.markdown(
        f"<div style='color:{C['muted']}; font-size:0.82rem;'>"
        f"Across the tested range of <b style='color:{C['text']};'>{selected_var_label}</b>, "
        f"your 12-month outcome spans "
        f"<b style='color:{C['text']};'>{fmt_currency(outcome_range)}</b> "
        f"(from {fmt_currency(worst_row['median_outcome'])} "
        f"to {fmt_currency(best_row['median_outcome'])})."
        f"</div>",
        unsafe_allow_html=True,
    )

# ── Navigation ────────────────────────────────────────────────────────────────
st.divider()
if st.button("Continue →  Allocation Engine", type="primary"):
    st.switch_page("pages/5_Allocation_Engine.py")

"""
Financial Health — Step 2
Cash position, burn rate, savings rate, spending breakdown, and anomaly detection.
"""
from __future__ import annotations

import sys
import os

# Ensure project root is on the path when Streamlit runs the page directly
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
_app_dir = os.path.join(_root, "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from page_guards import require_mode, require_raw_data
from src.data_loader import parse_personal_csv, parse_business_csv
from src.analysis.financial_health import (
    analyze_personal_health,
    analyze_business_health,
    detect_anomalies,
)
from src.utils.formatting import fmt_currency, fmt_percent

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Health | MoneyMap AI",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark theme CSS (mirrors Home.py palette) ──────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] { background-color: #0e1117; }
    [data-testid="stSidebar"]          { background-color: #161b22; }
    [data-testid="stMetric"]           { background-color: #161b22;
                                         border: 1px solid #30363d;
                                         border-radius: 10px;
                                         padding: 1rem 1.25rem; }
    [data-testid="stMetricLabel"]      { color: #8b949e !important; font-size: 0.85rem; }
    [data-testid="stMetricValue"]      { color: #e6edf3 !important; }
    [data-testid="stMetricDelta"]      { font-size: 0.8rem; }
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #e6edf3;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid #30363d;
    }
    .flag-card {
        border-radius: 8px;
        padding: 0.6rem 1rem;
        margin-bottom: 0.4rem;
        font-size: 0.93rem;
    }
    .stExpander { border: 1px solid #30363d !important; border-radius: 8px; }
    div[data-testid="stHorizontalBlock"] > div { gap: 0.75rem; }
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

_BAR_PALETTE = [
    "#1f6feb", "#388bfd", "#58a6ff",
    "#3fb950", "#56d364", "#7ee787",
    "#d29922", "#e3b341", "#f0c53f",
    "#f85149", "#ff7b72", "#ffa198",
]

_PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor=C["bg"],
    plot_bgcolor=C["surface"],
    font=dict(color=C["text"], family="Inter, sans-serif", size=12),
    margin=dict(l=12, r=12, t=36, b=12),
)

_AXIS_BASE = dict(
    gridcolor=C["border"], zerolinecolor=C["border"],
    tickfont=dict(color=C["muted"]),
)


raw_df: pd.DataFrame = st.session_state["raw_df"]
mode: str = st.session_state.get("mode", "personal")

st.markdown(
    f"<h2 style='color:#e6edf3; margin-bottom:0;'>📊 Financial Health</h2>"
    f"<p style='color:#8b949e; margin-top:0.2rem;'>Mode: <b>{mode.capitalize()}</b></p>",
    unsafe_allow_html=True,
)


# ── Parse + analyse (cache in session_state keyed by df hash + mode) ──────────
@st.cache_data(show_spinner=False)
def _parse_and_analyse(df: pd.DataFrame, _mode: str):
    if _mode == "personal":
        parsed = parse_personal_csv(df)
        health = analyze_personal_health(parsed)
    else:
        parsed = parse_business_csv(df)
        health = analyze_business_health(parsed)
    anomalies = detect_anomalies(parsed, _mode)
    return parsed, health, anomalies


with st.spinner("Analysing your finances…"):
    try:
        parsed_df, health, anomalies = _parse_and_analyse(raw_df, mode)
    except Exception as exc:
        st.error(f"Failed to analyse data: {exc}")
        st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Chart builders
# ─────────────────────────────────────────────────────────────────────────────

def _bar_chart(categories: dict, title: str) -> go.Figure:
    """Horizontal bar chart for category breakdown."""
    cats = list(categories.keys())
    vals = [categories[c] for c in cats]
    colours = [_BAR_PALETTE[i % len(_BAR_PALETTE)] for i in range(len(cats))]

    fig = go.Figure(
        go.Bar(
            x=vals,
            y=cats,
            orientation="h",
            marker=dict(color=colours, line=dict(width=0)),
            hovertemplate="%{y}<br><b>$%{x:,.0f}</b><extra></extra>",
            text=[f"${v:,.0f}" for v in vals],
            textposition="outside",
            textfont=dict(color=C["muted"], size=11),
        )
    )
    fig.update_layout(
        **_PLOTLY_BASE,
        title=dict(text=title, font=dict(color=C["muted"], size=13), x=0),
        height=max(220, len(cats) * 42 + 60),
        xaxis=dict(**_AXIS_BASE, tickprefix="$", tickformat=",.0f"),
        yaxis=dict(**_AXIS_BASE, autorange="reversed"),
        bargap=0.35,
    )
    return fig


def _trend_chart_personal(inc_series: list, exp_series: list) -> go.Figure:
    """Line chart: monthly income vs expenses."""
    inc_months = [r["month"] for r in inc_series]
    inc_vals   = [r["value"] for r in inc_series]
    exp_months = [r["month"] for r in exp_series]
    exp_vals   = [r["value"] for r in exp_series]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=inc_months, y=inc_vals,
        name="Income",
        mode="lines+markers",
        line=dict(color=C["green"], width=2),
        marker=dict(size=6, color=C["green"]),
        hovertemplate="%{x}<br><b>Income: $%{y:,.0f}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=exp_months, y=exp_vals,
        name="Expenses",
        mode="lines+markers",
        line=dict(color=C["red"], width=2),
        marker=dict(size=6, color=C["red"]),
        hovertemplate="%{x}<br><b>Expenses: $%{y:,.0f}</b><extra></extra>",
    ))
    fig.update_layout(
        **_PLOTLY_BASE,
        title=dict(text="Monthly Income vs Expenses", font=dict(color=C["muted"], size=13), x=0),
        height=320,
        legend=dict(
            orientation="h", x=0, y=1.12,
            font=dict(color=C["muted"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=_AXIS_BASE,
        yaxis=dict(**_AXIS_BASE, tickprefix="$", tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


def _trend_chart_business(rev_series: list, exp_series: list, net_series: list) -> go.Figure:
    """Line chart: monthly revenue, expenses, and net income."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[r["month"] for r in rev_series],
        y=[r["value"] for r in rev_series],
        name="Revenue",
        mode="lines+markers",
        line=dict(color=C["green"], width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br><b>Revenue: $%{y:,.0f}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[r["month"] for r in exp_series],
        y=[r["value"] for r in exp_series],
        name="Expenses",
        mode="lines+markers",
        line=dict(color=C["red"], width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br><b>Expenses: $%{y:,.0f}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[r["month"] for r in net_series],
        y=[r["value"] for r in net_series],
        name="Net Income",
        mode="lines+markers",
        line=dict(color=C["blue"], width=2, dash="dot"),
        marker=dict(size=5),
        hovertemplate="%{x}<br><b>Net: $%{y:,.0f}</b><extra></extra>",
    ))
    fig.update_layout(
        **_PLOTLY_BASE,
        title=dict(text="Monthly Revenue vs Expenses", font=dict(color=C["muted"], size=13), x=0),
        height=340,
        legend=dict(
            orientation="h", x=0, y=1.12,
            font=dict(color=C["muted"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=_AXIS_BASE,
        yaxis=dict(**_AXIS_BASE, tickprefix="$", tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Flag renderer
# ─────────────────────────────────────────────────────────────────────────────

def _render_flags(flags: list[dict]) -> None:
    if not flags:
        st.success("No warnings detected. Financials look healthy.", icon="✅")
        return
    for flag in flags:
        level = flag.get("level", "info")
        msg   = flag.get("msg", "")
        if level == "error":
            st.error(msg, icon="🚨")
        elif level == "warning":
            st.warning(msg, icon="⚠️")
        else:
            st.info(msg, icon="ℹ️")


# ─────────────────────────────────────────────────────────────────────────────
# PERSONAL MODE
# ─────────────────────────────────────────────────────────────────────────────

if mode == "personal":
    h = health

    # ── Metric cards ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        delta_inc = (
            fmt_currency(h["income_delta"]) if h.get("income_delta") is not None else None
        )
        st.metric(
            "Avg Monthly Income",
            fmt_currency(h["monthly_income"]),
            delta=delta_inc,
        )
    with c2:
        delta_exp = (
            fmt_currency(h["expense_delta"]) if h.get("expense_delta") is not None else None
        )
        # Invert delta colour — higher expenses is bad
        st.metric(
            "Avg Monthly Expenses",
            fmt_currency(h["monthly_expenses"]),
            delta=delta_exp,
            delta_color="inverse",
        )
    with c3:
        sr = h["savings_rate"]
        sr_str = fmt_percent(sr)
        st.metric("Savings Rate", sr_str)
    with c4:
        ef = h["emergency_fund_months"]
        ef_str = f"{ef:.1f} mo" if ef < 999 else "∞"
        st.metric("Emergency Fund", ef_str)

    st.markdown("<br>", unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        # ── Spending breakdown bar chart ───────────────────────────────────────
        st.markdown('<p class="section-header">Spending by Category</p>', unsafe_allow_html=True)
        st.plotly_chart(
            _bar_chart(h["spending_by_category"], "Total spend per category (all months)"),
            width='stretch',
        )

        # ── Monthly trend ──────────────────────────────────────────────────────
        st.markdown('<p class="section-header">Monthly Income vs Expenses</p>', unsafe_allow_html=True)
        st.plotly_chart(
            _trend_chart_personal(h["monthly_income_series"], h["monthly_expense_series"]),
            width='stretch',
        )

    with col_right:
        # ── Extra scalar metrics ───────────────────────────────────────────────
        st.markdown('<p class="section-header">Key Ratios</p>', unsafe_allow_html=True)
        dti = h["debt_to_income_ratio"]
        m_inner1, m_inner2 = st.columns(2)
        with m_inner1:
            st.metric("Debt-to-Income", fmt_percent(dti))
            st.metric("Total Net Saved", fmt_currency(h["net_cash"]))
        with m_inner2:
            st.metric("Debt Payments", fmt_currency(h["monthly_expenses"] * dti if dti else 0, decimals=0) + "/mo")
            st.metric("Data Span", f"{h['n_months']} months")

        # ── Top growing categories ─────────────────────────────────────────────
        top_growing = h.get("top_3_growing_categories", [])
        if top_growing:
            st.markdown('<p class="section-header">Fastest Growing Spend</p>', unsafe_allow_html=True)
            for item in top_growing:
                pct = item["pct_change"] * 100
                arrow = "↑" if pct > 0 else "↓"
                colour = C["red"] if pct > 0 else C["green"]
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; "
                    f"padding:0.4rem 0; border-bottom:1px solid {C['border']};'>"
                    f"<span style='color:{C['text']};'>{item['category'].title()}</span>"
                    f"<span style='color:{colour}; font-weight:600;'>{arrow} {abs(pct):.0f}%</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("<br>", unsafe_allow_html=True)

        # ── Subscription breakdown ─────────────────────────────────────────────
        st.markdown('<p class="section-header">Subscriptions</p>', unsafe_allow_html=True)
        st.markdown(
            f"<p style='color:{C['muted']}; font-size:0.85rem; margin-bottom:0.5rem;'>"
            f"Monthly total: <b style='color:{C['text']};'>{fmt_currency(h['subscription_total'])}</b></p>",
            unsafe_allow_html=True,
        )
        sub_list = h.get("subscription_list", [])
        if sub_list:
            for sub in sub_list[:8]:
                st.markdown(
                    f"<div style='display:flex; justify-content:space-between; "
                    f"padding:0.3rem 0; border-bottom:1px solid {C['border']};'>"
                    f"<span style='color:{C['muted']}; font-size:0.88rem;'>{sub['name'][:38]}</span>"
                    f"<span style='color:{C['text']}; font-size:0.88rem;'>{fmt_currency(sub['monthly_avg'])}/mo</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Flags / warnings ──────────────────────────────────────────────────────
    st.markdown('<p class="section-header">Warnings & Flags</p>', unsafe_allow_html=True)
    _render_flags(h["flags"])


# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS MODE
# ─────────────────────────────────────────────────────────────────────────────

else:  # business
    h = health

    # ── Metric cards ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        delta_rev = (
            fmt_currency(h["revenue_delta"]) if h.get("revenue_delta") is not None else None
        )
        st.metric("Avg Monthly Revenue", fmt_currency(h["monthly_revenue"]), delta=delta_rev)

    with c2:
        delta_exp = (
            fmt_currency(h["expense_delta"]) if h.get("expense_delta") is not None else None
        )
        st.metric(
            "Avg Monthly Expenses",
            fmt_currency(h["monthly_expenses"]),
            delta=delta_exp,
            delta_color="inverse",
        )

    with c3:
        gm = h["gross_margin_pct"]
        nm = h["net_margin_pct"]
        st.metric("Gross Margin", fmt_percent(gm))
        st.metric("Net Margin",   fmt_percent(nm))

    with c4:
        burn = h["burn_rate"]
        runway = h.get("runway_months")
        st.metric("Burn Rate", fmt_currency(burn) + "/mo" if burn > 0 else "$0/mo")
        st.metric(
            "Runway",
            f"{runway:.1f} mo" if runway is not None else "Profitable",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        # ── Expense breakdown ──────────────────────────────────────────────────
        st.markdown('<p class="section-header">Expense Breakdown</p>', unsafe_allow_html=True)
        st.plotly_chart(
            _bar_chart(h["expense_breakdown"], "Total expenses per category (all months)"),
            width='stretch',
        )

        # ── Monthly trend ──────────────────────────────────────────────────────
        st.markdown('<p class="section-header">Monthly Revenue vs Expenses</p>', unsafe_allow_html=True)
        st.plotly_chart(
            _trend_chart_business(
                h["monthly_revenue_series"],
                h["monthly_expense_series"],
                h["monthly_net_series"],
            ),
            width='stretch',
        )

    with col_right:
        # ── P&L summary ────────────────────────────────────────────────────────
        st.markdown('<p class="section-header">P&L Summary</p>', unsafe_allow_html=True)
        m_inner1, m_inner2 = st.columns(2)
        with m_inner1:
            st.metric("Total Revenue",  fmt_currency(h["total_revenue"]))
            st.metric("Gross Profit",   fmt_currency(h["gross_profit"]))
        with m_inner2:
            st.metric("Total Expenses", fmt_currency(h["total_expenses"]))
            st.metric("Net Income",     fmt_currency(h["net_income"]))

        # ── Revenue trend ──────────────────────────────────────────────────────
        rev_trend = h.get("revenue_trend", {})
        exp_trend = h.get("expense_trend", {})
        st.markdown('<p class="section-header">Trend Summary</p>', unsafe_allow_html=True)
        _TREND_ICON = {"increasing": "↑", "decreasing": "↓", "stable": "→"}
        _TREND_COLOR = {
            "increasing": {"rev": C["green"],  "exp": C["red"]},
            "decreasing": {"rev": C["red"],    "exp": C["green"]},
            "stable":     {"rev": C["muted"],  "exp": C["muted"]},
        }
        for label, trend, role in [
            ("Revenue trend", rev_trend, "rev"),
            ("Expense trend", exp_trend, "exp"),
        ]:
            t = trend.get("trend", "stable")
            icon = _TREND_ICON.get(t, "→")
            colour = _TREND_COLOR.get(t, {}).get(role, C["muted"])
            pct = trend.get("pct_change_avg", 0) * 100
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; "
                f"padding:0.4rem 0; border-bottom:1px solid {C['border']};'>"
                f"<span style='color:{C['muted']};'>{label}</span>"
                f"<span style='color:{colour}; font-weight:600;'>{icon} {t.title()} ({pct:+.1f}%/mo)</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ── Revenue concentration ──────────────────────────────────────────────
        rev_cv = h.get("revenue_concentration_cv", 0)
        payroll_pct = h.get("payroll_pct_of_revenue", 0)
        payroll_colour = C["red"] if payroll_pct > 0.50 else C["text"]
        st.markdown('<p class="section-header">Concentration Risk</p>', unsafe_allow_html=True)
        st.markdown(
            f"<div style='padding:0.4rem 0; border-bottom:1px solid {C['border']};'>"
            f"<span style='color:{C['muted']};'>Revenue volatility (CV)</span>"
            f"<span style='float:right; color:{C['text']};'>{rev_cv:.2f}</span></div>"
            f"<div style='padding:0.4rem 0;'>"
            f"<span style='color:{C['muted']};'>Payroll % of revenue</span>"
            f"<span style='float:right; color:{payroll_colour};'>"
            f"{fmt_percent(payroll_pct)}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Flags ─────────────────────────────────────────────────────────────────
    st.markdown('<p class="section-header">Warnings & Flags</p>', unsafe_allow_html=True)
    _render_flags(h["flags"])


# ─────────────────────────────────────────────────────────────────────────────
# Anomalies (both modes)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)
anomaly_label = f"Anomalies Detected — {len(anomalies)} found" if anomalies else "Anomaly Scan — Nothing unusual found"

with st.expander(anomaly_label, expanded=bool(anomalies)):
    if not anomalies:
        st.success("No anomalies detected across statistical outliers, duplicates, or spending spikes.", icon="✅")
    else:
        # Group by type
        _TYPE_LABEL = {
            "statistical_outlier": ("🔍 Statistical Outliers", "Transactions more than 3σ above their category mean"),
            "duplicate_charge":    ("🔁 Possible Duplicates",  "Same amount charged multiple times on the same day"),
            "spending_spike":      ("📈 Monthly Spend Spikes",  "Months where total spending jumped >30% vs prior month"),
        }
        by_type: dict[str, list] = {}
        for a in anomalies:
            by_type.setdefault(a["anomaly_type"], []).append(a)

        for atype, items in by_type.items():
            title, subtitle = _TYPE_LABEL.get(atype, (atype, ""))
            st.markdown(
                f"<p style='color:{C['text']}; font-weight:600; margin-bottom:0.1rem;'>{title}</p>"
                f"<p style='color:{C['muted']}; font-size:0.82rem; margin-top:0;'>{subtitle}</p>",
                unsafe_allow_html=True,
            )
            rows = []
            for a in items:
                rows.append({
                    "Date":        a["date"],
                    "Amount":      fmt_currency(a["amount"]) if a["amount"] is not None else "—",
                    "Category":    a.get("category", ""),
                    "Description": a.get("description", ""),
                    "Reason":      a["reason"],
                })
            st.dataframe(
                pd.DataFrame(rows),
                width='stretch',
                hide_index=True,
                column_config={
                    "Reason": st.column_config.TextColumn(width="large"),
                },
            )

# ─────────────────────────────────────────────────────────────────────────────
# Navigation
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
if st.button("Continue →  Market & Economy", type="primary", width='content'):
    st.switch_page("pages/3_Market_Economy.py")

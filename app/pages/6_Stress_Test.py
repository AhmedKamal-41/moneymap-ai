"""
Stress Test — Step 6
How Would You Handle a Crash?
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

from page_guards import require_mode, require_raw_data, require_scenarios
from src.analysis.stress_test import (
    SCENARIOS,
    run_all_stress_tests,
    resilience_score,
)
from src.utils.formatting import fmt_currency, fmt_percent

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stress Test | MoneyMap AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "bg":      "#0e1117",
    "surface": "#161b22",
    "surface2":"#1c2128",
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

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{ background-color: {C["bg"]}; }}
[data-testid="stSidebar"]          {{ background-color: {C["surface"]}; }}
[data-testid="stMetric"]           {{
    background: {C["surface"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    padding: 0.7rem 0.9rem;
}}
[data-testid="stMetricLabel"] {{ color: {C["muted"]} !important; font-size: 0.78rem; }}
[data-testid="stMetricValue"] {{ color: {C["text"]}  !important; }}
.stExpander {{
    border: 1px solid {C["border"]} !important;
    border-radius: 12px !important;
    background: {C["surface"]};
    margin-bottom: 0.5rem !important;
}}
.stExpander summary {{
    color: {C["text"]} !important;
    font-weight: 600 !important;
    padding: 0.6rem 0.8rem !important;
}}
div[data-testid="stHorizontalBlock"] > div {{ gap: 0.4rem; }}
hr {{ border-color: {C["border"]}; margin: 1rem 0; }}
</style>
""", unsafe_allow_html=True)

require_mode()
require_raw_data()
require_scenarios()

_PLOTLY_BASE = dict(
    template="plotly_dark",
    paper_bgcolor=C["bg"],
    plot_bgcolor=C["surface"],
    font=dict(color=C["text"], family="Inter, sans-serif", size=11),
    margin=dict(l=16, r=16, t=44, b=16),
    hovermode="x unified",
)

# ─────────────────────────────────────────────────────────────────────────────
# Session state & financial health builder
# ─────────────────────────────────────────────────────────────────────────────

mode     = st.session_state["mode"]
raw_df   = st.session_state["raw_df"]
sp       = st.session_state.get("scenario_params", {}) or {}


@st.cache_data(show_spinner=False)
def _parse_personal(df):
    from src.data_loader import parse_personal_csv
    from src.analysis.financial_health import analyze_personal_health
    return analyze_personal_health(parse_personal_csv(df))


@st.cache_data(show_spinner=False)
def _parse_business(df):
    from src.data_loader import parse_business_csv
    from src.analysis.financial_health import analyze_business_health
    return analyze_business_health(parse_business_csv(df))


def _build_financial_health() -> dict:
    fh: dict = {}
    if mode == "personal":
        if raw_df is not None:
            try:
                h = _parse_personal(raw_df)
                fh = {
                    "monthly_income":        h["monthly_income"],
                    "monthly_expenses":      h["monthly_expenses"],
                    "net_cash":              h["net_cash"],
                    "emergency_fund_months": h["emergency_fund_months"],
                }
            except Exception:
                pass
        fh.setdefault("monthly_income",   float(sp.get("monthly_income",   5_500.0)))
        fh.setdefault("monthly_expenses", float(sp.get("monthly_expenses", 4_500.0)))
        fh.setdefault("net_cash",         float(sp.get("savings",         13_000.0)))
        fh["debt_rate"]    = float(sp.get("debt_rate",    0.07))
        fh["debt_balance"] = float(sp.get("debt_balance", 15_000.0))

    else:
        if raw_df is not None:
            try:
                h = _parse_business(raw_df)
                fh = {
                    "monthly_revenue":  h["monthly_revenue"],
                    "monthly_expenses": h["monthly_expenses"],
                    "gross_margin_pct": h["gross_margin_pct"],
                    "runway_months":    h["runway_months"],
                }
            except Exception:
                pass
        fh.setdefault("monthly_revenue",  float(sp.get("monthly_revenue",  47_000.0)))
        fh.setdefault("monthly_expenses", float(sp.get("monthly_expenses", 40_000.0)))
        fh["cash_balance"]  = float(sp.get("cash_balance",  88_000.0))
        fh["debt_rate"]     = float(sp.get("debt_rate",         0.07))
        fh["debt_balance"]  = float(sp.get("debt_balance",  50_000.0))
        fh.setdefault("gross_margin_pct", 0.15)

    return fh


fh            = _build_financial_health()
portfolio_val = float(sp.get("portfolio_value", 25_000.0)) if mode == "personal" else 0.0

# ─────────────────────────────────────────────────────────────────────────────
# Run all stress tests (cached)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _run_all(fh_frozen: tuple, pv: float, _mode: str):
    return run_all_stress_tests(dict(fh_frozen), pv, _mode)


with st.spinner("Running stress scenarios…"):
    try:
        all_results = _run_all(tuple(sorted(fh.items())), portfolio_val, mode)
        resil = resilience_score(all_results)
    except Exception as _run_err:
        st.error(f"Failed to run stress scenarios: {_run_err}", icon="💥")
        st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Chart builders
# ─────────────────────────────────────────────────────────────────────────────

def _hex_rgba(hex_color: str, alpha: float) -> str:
    """Convert a 6-char hex color to an rgba() string with the given alpha.
    Plotly does not accept 8-char hex (#RRGGBBAA)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _trajectory_chart(result: dict) -> go.Figure:
    """Base vs stressed cash trajectory with shock period annotation."""
    base     = result["cash_path_base"]
    stressed = result["cash_path_stressed"]
    duration = int(SCENARIOS[result["scenario_name"]].get("duration_months", 12))
    label    = result["label"]
    color    = result["color"]
    n        = len(base)
    months   = list(range(n))

    fig = go.Figure()

    # ── Shock period shading ──────────────────────────────────────────────────
    shock_end = min(duration, n - 1)
    fig.add_vrect(
        x0=0, x1=shock_end,
        fillcolor=_hex_rgba(color, 0.094),
        line_color="rgba(0,0,0,0)",
        annotation_text="shock period",
        annotation_position="top left",
        annotation_font=dict(color=C["muted"], size=9),
    )

    # ── Gap fill between base and stressed (damage area) ─────────────────────
    # Upper boundary = base, lower = stressed; fill between them shows the cost
    fig.add_trace(go.Scatter(
        x=months, y=base,
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False, hoverinfo="skip", name="_base_upper",
    ))
    fig.add_trace(go.Scatter(
        x=months, y=stressed,
        fill="tonexty",
        fillcolor=_hex_rgba(color, 0.133),
        mode="lines",
        line=dict(color="rgba(0,0,0,0)", width=0),
        showlegend=False, hoverinfo="skip", name="_stressed_lower",
    ))

    # ── Base trajectory (blue, solid) ─────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=months, y=base,
        mode="lines",
        name="No shock (base)",
        line=dict(color=C["blue"], width=2, dash="dot"),
        hovertemplate="Month %{x}<br>Base: %{y:$,.0f}<extra></extra>",
    ))

    # ── Stressed trajectory ────────────────────────────────────────────────────
    end_val   = stressed[-1]
    line_col  = C["green"] if end_val >= 0 else C["red"]
    fig.add_trace(go.Scatter(
        x=months, y=stressed,
        mode="lines",
        name=label,
        line=dict(color=line_col, width=2.5),
        hovertemplate="Month %{x}<br>Stressed: %{y:$,.0f}<extra></extra>",
    ))

    # ── Zero reference ─────────────────────────────────────────────────────────
    fig.add_hline(
        y=0,
        line=dict(color=C["red"], width=1, dash="dot"),
        annotation_text="$0",
        annotation_font=dict(color=C["red"], size=9),
        annotation_position="bottom right",
    )

    # ── Worst-month marker ─────────────────────────────────────────────────────
    wm = result["worst_month"]
    if 0 < wm < n:
        fig.add_trace(go.Scatter(
            x=[wm], y=[stressed[wm]],
            mode="markers+text",
            marker=dict(color=color, size=9, symbol="circle"),
            text=[f"  worst: {fmt_currency(stressed[wm])}"],
            textposition="middle right",
            textfont=dict(color=C["muted"], size=9),
            showlegend=False,
            hoverinfo="skip",
        ))

    fig.update_layout(
        **_PLOTLY_BASE,
        title=dict(
            text=f"24-Month Trajectory — {label}",
            font=dict(color=C["muted"], size=12), x=0,
        ),
        height=300,
        xaxis=dict(
            **_PLOTLY_BASE.get("xaxis", {}),
            gridcolor=C["border"], zerolinecolor=C["border"],
            tickfont=dict(color=C["muted"]),
            title=dict(text="Month", font=dict(color=C["muted"], size=10)),
        ),
        yaxis=dict(
            gridcolor=C["border"], zerolinecolor=C["border"],
            tickfont=dict(color=C["muted"]),
            tickprefix="$", tickformat=",.0f",
        ),
        legend=dict(
            orientation="h", x=0, y=1.12,
            font=dict(color=C["muted"], size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


def _summary_bar_chart(all_results: list) -> go.Figure:
    """Horizontal bar chart: portfolio impact % across all scenarios."""
    labels  = [r["label"]               for r in all_results]
    impacts = [r["portfolio_impact_pct"] * 100 for r in all_results]
    colors  = [r["color"]                for r in all_results]

    fig = go.Figure(go.Bar(
        x=impacts, y=labels,
        orientation="h",
        marker=dict(color=colors, opacity=0.85, line=dict(width=0)),
        text=[f"{v:.0f}%" for v in impacts],
        textposition="outside",
        textfont=dict(color=C["muted"], size=10),
        hovertemplate="<b>%{y}</b><br>Portfolio impact: %{x:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        **_PLOTLY_BASE,
        title=dict(text="Portfolio Impact by Scenario (%)",
                   font=dict(color=C["muted"], size=12), x=0),
        height=220,
        xaxis=dict(
            gridcolor=C["border"], tickfont=dict(color=C["muted"]),
            ticksuffix="%", range=[min(impacts) * 1.25, 5],
        ),
        yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(color=C["text"], size=10)),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

header_left, header_right = st.columns([2.4, 1], gap="large")

with header_left:
    st.markdown(
        f"<h1 style='color:{C['text']}; font-size:2.1rem; font-weight:800; "
        f"letter-spacing:-0.02em; margin:0 0 0.2rem'>💥 How Would You Handle a Crash?</h1>"
        f"<p style='color:{C['muted']}; margin:0 0 0.8rem; font-size:0.96rem'>"
        f"Each scenario applies historical shocks to your {'income, savings, and portfolio' if mode == 'personal' else 'revenue, cash balance, and portfolio'}. "
        f"See how your position holds up across five of the most severe financial events of the past 30 years."
        f"</p>",
        unsafe_allow_html=True,
    )

with header_right:
    # ── Resilience score gauge ─────────────────────────────────────────────
    sc    = resil["score"]
    scol  = resil["color"]
    slbl  = resil["label"]
    sdet  = resil["detail"]
    surv  = resil["survived"]
    stot  = resil["total"]

    st.markdown(
        f"<div style='background: linear-gradient(135deg, {C['surface2']} 0%, {C['surface']} 100%); "
        f"border:1px solid {scol}55; border-radius:14px; padding:1.1rem 1.3rem; text-align:center'>"
        f"<div style='font-size:0.72rem; color:{C['muted']}; font-weight:700; "
        f"text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.5rem'>"
        f"Your Resilience Score</div>"
        # big ring-style score
        f"<div style='position:relative; display:inline-block; margin-bottom:0.4rem'>"
        f"<svg viewBox='0 0 80 80' width='88' height='88'>"
        f"<circle cx='40' cy='40' r='34' fill='none' stroke='{C['border']}' stroke-width='7'/>"
        f"<circle cx='40' cy='40' r='34' fill='none' stroke='{scol}' stroke-width='7' "
        f"stroke-dasharray='{sc * 2.136:.1f} 213.6' "
        f"stroke-dashoffset='53.4' stroke-linecap='round' "
        f"transform='rotate(-90 40 40)'/>"
        f"<text x='40' y='44' text-anchor='middle' fill='{C['text']}' "
        f"font-size='18' font-weight='800' font-family='Inter,sans-serif'>{sc}</text>"
        f"</svg>"
        f"</div>"
        f"<div style='font-size:1.1rem; font-weight:800; color:{scol}; margin-bottom:0.3rem'>"
        f"{slbl}</div>"
        f"<div style='font-size:0.78rem; color:{C['muted']}'>"
        f"Survives <b style='color:{C['text']}'>{surv}</b> of <b style='color:{C['text']}'>{stot}</b> scenarios at month 12</div>"
        f"<div style='font-size:0.76rem; color:{C['muted']}; margin-top:0.35rem; line-height:1.5'>{sdet}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("<hr>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Context strip
# ─────────────────────────────────────────────────────────────────────────────

if mode == "personal":
    m_income = fh.get("monthly_income", 5500)
    m_exp    = fh.get("monthly_expenses", 4500)
    savings  = fh.get("net_cash", 13000)
    d_rate   = fh.get("debt_rate", 0.07)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Monthly Income",   fmt_currency(m_income))
    m2.metric("Monthly Expenses", fmt_currency(m_exp))
    m3.metric("Liquid Savings",   fmt_currency(savings))
    m4.metric("Debt APR",         fmt_percent(d_rate),
              delta="High" if d_rate > 0.15 else ("Moderate" if d_rate > 0.08 else "Low"),
              delta_color="inverse" if d_rate > 0.15 else "off")
else:
    m_rev    = fh.get("monthly_revenue", 47000)
    m_exp    = fh.get("monthly_expenses", 40000)
    cash_bal = fh.get("cash_balance", 88000)
    gm       = fh.get("gross_margin_pct", 0.15)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Monthly Revenue",  fmt_currency(m_rev))
    m2.metric("Monthly Expenses", fmt_currency(m_exp))
    m3.metric("Cash Balance",     fmt_currency(cash_bal))
    m4.metric("Gross Margin",     fmt_percent(gm))

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Scenario cards (expandable)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<h3 style='color:{C['text']}; font-size:1.1rem; font-weight:700; "
    f"margin:0 0 0.8rem; padding-bottom:0.35rem; border-bottom:1px solid {C['border']}'>"
    f"Scenario Deep Dives</h3>",
    unsafe_allow_html=True,
)

# Worst scenario auto-expanded
worst_name = all_results[0]["scenario_name"] if all_results else None

for result in all_results:
    sname      = result["scenario_name"]
    label      = result["label"]
    desc       = result["description"]
    icon       = result["icon"]
    color      = result["color"]
    port_pct   = result["portfolio_impact_pct"]
    port_usd   = result["portfolio_impact_dollars"]
    new_port   = result["new_portfolio_value"]
    new_net    = result["new_monthly_net"]
    base_net   = result["base_monthly_net"]
    burn       = result["new_monthly_burn"]
    breached   = result["floor_breached"]
    worst_mo   = result["worst_month"]
    recov_mo   = result["recovery_months"]
    recov_summ = result["recovery_summary"]
    severity   = result["severity_score"]

    # Pick survival metric label based on mode
    if mode == "personal":
        survival_val = result.get("months_until_savings_depleted")
        survival_lbl = "Months Until Depletion"
    else:
        survival_val = result.get("new_runway_months")
        survival_lbl = "Runway Under Shock"

    # Expander header line
    sev_label  = "Severe" if severity > 65 else ("Moderate" if severity > 35 else "Mild")
    sev_color  = C["red"] if severity > 65 else (C["yellow"] if severity > 35 else C["green"])
    port_str   = f"{port_pct*100:.0f}% portfolio"
    breach_str = " · cash floor breached" if breached else ""
    is_worst   = sname == worst_name

    with st.expander(
        f"{icon}  {label}  —  {port_str}{breach_str}",
        expanded=is_worst,
    ):
        # ── Description banner ────────────────────────────────────────────
        st.markdown(
            f"<div style='background:{C['surface2']}; border:1px solid {color}40; "
            f"border-left:3px solid {color}; border-radius:8px; "
            f"padding:0.65rem 1rem; margin-bottom:1rem; font-size:0.86rem; "
            f"color:{C['muted']}; line-height:1.55'>"
            f"<span style='color:{color}; font-weight:700'>{sev_label}</span>"
            f" &nbsp;·&nbsp; {desc}</div>",
            unsafe_allow_html=True,
        )

        # ── Four key metrics ──────────────────────────────────────────────
        mc1, mc2, mc3, mc4 = st.columns(4)

        with mc1:
            port_color = C["red"] if port_pct < -0.3 else (C["yellow"] if port_pct < -0.1 else C["muted"])
            st.markdown(
                f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
                f"border-radius:10px; padding:0.75rem 1rem'>"
                f"<div style='font-size:0.72rem; color:{C['muted']}; margin-bottom:4px'>"
                f"Portfolio Impact</div>"
                f"<div style='font-size:1.6rem; font-weight:900; color:{port_color}; "
                f"line-height:1'>{port_pct*100:.0f}%</div>"
                f"<div style='font-size:0.8rem; color:{C['muted']}; margin-top:3px'>"
                f"{fmt_currency(port_usd)} &nbsp;→&nbsp; {fmt_currency(new_port)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with mc2:
            burn_color    = C["red"] if burn > 500 else (C["yellow"] if burn > 0 else C["green"])
            net_delta     = new_net - base_net
            net_delta_clr = C["red"] if net_delta < 0 else C["green"]
            st.markdown(
                f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
                f"border-radius:10px; padding:0.75rem 1rem'>"
                f"<div style='font-size:0.72rem; color:{C['muted']}; margin-bottom:4px'>"
                f"Monthly Net Change</div>"
                f"<div style='font-size:1.6rem; font-weight:900; "
                f"color:{net_delta_clr}; line-height:1'>"
                f"{fmt_currency(net_delta)}</div>"
                f"<div style='font-size:0.8rem; color:{C['muted']}; margin-top:3px'>"
                f"New net: {fmt_currency(new_net)}/mo</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with mc3:
            if survival_val is None:
                sv_str   = "Profitable"
                sv_color = C["green"]
                sv_sub   = "net positive even under shock"
            elif survival_val < 3:
                sv_str   = f"{survival_val:.1f} mo"
                sv_color = C["red"]
                sv_sub   = "critical — cash depletes fast"
            elif survival_val < 9:
                sv_str   = f"{survival_val:.1f} mo"
                sv_color = C["yellow"]
                sv_sub   = "limited buffer"
            else:
                sv_str   = f"{survival_val:.1f} mo"
                sv_color = C["green"]
                sv_sub   = "adequate cushion"

            st.markdown(
                f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
                f"border-radius:10px; padding:0.75rem 1rem'>"
                f"<div style='font-size:0.72rem; color:{C['muted']}; margin-bottom:4px'>"
                f"{survival_lbl}</div>"
                f"<div style='font-size:1.6rem; font-weight:900; color:{sv_color}; line-height:1'>"
                f"{sv_str}</div>"
                f"<div style='font-size:0.8rem; color:{C['muted']}; margin-top:3px'>{sv_sub}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with mc4:
            if recov_mo == 0:
                rc_str   = "No impact"
                rc_color = C["green"]
                rc_sub   = "cash not depleted by shock"
            elif recov_mo is None:
                rc_str   = "Uncertain"
                rc_color = C["red"]
                rc_sub   = "positive cash flow needed first"
            elif recov_mo <= 6:
                rc_str   = f"~{recov_mo} mo"
                rc_color = C["green"]
                rc_sub   = "rapid recovery"
            elif recov_mo <= 18:
                rc_str   = f"~{recov_mo} mo"
                rc_color = C["yellow"]
                rc_sub   = "moderate recovery"
            else:
                rc_str   = f"~{recov_mo} mo"
                rc_color = C["red"]
                rc_sub   = "extended recovery"

            st.markdown(
                f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
                f"border-radius:10px; padding:0.75rem 1rem'>"
                f"<div style='font-size:0.72rem; color:{C['muted']}; margin-bottom:4px'>"
                f"Recovery Time</div>"
                f"<div style='font-size:1.6rem; font-weight:900; color:{rc_color}; line-height:1'>"
                f"{rc_str}</div>"
                f"<div style='font-size:0.8rem; color:{C['muted']}; margin-top:3px'>{rc_sub}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Trajectory chart ──────────────────────────────────────────────
        try:
            st.plotly_chart(_trajectory_chart(result), width='stretch')
        except Exception as _chart_err:
            st.error(f"Could not render trajectory chart: {_chart_err}", icon="⚠️")

        # ── Recovery narrative ────────────────────────────────────────────
        st.markdown(
            f"<div style='background:{C['surface2']}; border:1px solid {C['border']}; "
            f"border-radius:8px; padding:0.65rem 1rem; font-size:0.82rem; "
            f"color:{C['muted']}; line-height:1.6'>"
            f"<b style='color:{C['text']}'>Recovery outlook:</b> {recov_summ}"
            f"</div>",
            unsafe_allow_html=True,
        )

# ─────────────────────────────────────────────────────────────────────────────
# Summary table — all scenarios side by side
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f"<h3 style='color:{C['text']}; font-size:1.1rem; font-weight:700; "
    f"margin:0 0 0.8rem; padding-bottom:0.35rem; border-bottom:1px solid {C['border']}'>"
    f"All Scenarios — Side by Side</h3>",
    unsafe_allow_html=True,
)

# Left: summary bar chart  |  Right: table
chart_col, table_col = st.columns([1, 1.5], gap="large")

with chart_col:
    try:
        st.plotly_chart(_summary_bar_chart(all_results), width='stretch')
    except Exception as _bar_err:
        st.error(f"Could not render summary chart: {_bar_err}", icon="⚠️")

with table_col:
    # Build styled HTML table
    def _cell_color(val: float, lo: float, hi: float, invert: bool = False) -> str:
        """Map a value to green/yellow/red based on thresholds."""
        if invert:
            if val < lo:
                return C["green"]
            if val < hi:
                return C["yellow"]
            return C["red"]
        else:
            if val > hi:
                return C["green"]
            if val > lo:
                return C["yellow"]
            return C["red"]

    tbl = (
        f"<table style='width:100%; border-collapse:collapse; font-size:0.82rem'>"
        f"<thead><tr>"
        f"<th style='text-align:left; padding:6px 8px; color:{C['muted']}; "
        f"border-bottom:1px solid {C['border']}; white-space:nowrap'>Scenario</th>"
        f"<th style='padding:6px 8px; color:{C['muted']}; border-bottom:1px solid {C['border']}; "
        f"text-align:right'>Portfolio</th>"
        f"<th style='padding:6px 8px; color:{C['muted']}; border-bottom:1px solid {C['border']}; "
        f"text-align:right'>Net Δ/mo</th>"
        f"<th style='padding:6px 8px; color:{C['muted']}; border-bottom:1px solid {C['border']}; "
        f"text-align:right'>Recovery</th>"
        f"<th style='padding:6px 8px; color:{C['muted']}; border-bottom:1px solid {C['border']}; "
        f"text-align:center'>Cash Safe?</th>"
        f"</tr></thead><tbody>"
    )
    for r in all_results:
        pp      = r["portfolio_impact_pct"]
        nd      = r["new_monthly_net"] - r["base_monthly_net"]
        rc      = r["recovery_months"]
        bf      = r["floor_breached"]
        rc_str  = f"~{rc} mo" if rc is not None and rc > 0 else ("None" if rc == 0 else "—")
        pp_col  = _cell_color(pp,   -0.30, -0.10, invert=True)
        nd_col  = C["green"] if nd >= 0 else (C["yellow"] if nd >= -500 else C["red"])
        rc_col  = _cell_color(rc or 99, 6, 18, invert=True)
        bf_col  = C["green"] if not bf else C["red"]
        bf_str  = "✓ Yes" if not bf else "✗ Breached"

        tbl += (
            f"<tr style='border-bottom:1px solid {C['border']}40'>"
            f"<td style='padding:6px 8px; color:{r['color']}; font-weight:600'>"
            f"{r['icon']} {r['label']}</td>"
            f"<td style='padding:6px 8px; text-align:right; font-weight:700; color:{pp_col}'>"
            f"{pp*100:.0f}%</td>"
            f"<td style='padding:6px 8px; text-align:right; color:{nd_col}'>"
            f"{fmt_currency(nd)}</td>"
            f"<td style='padding:6px 8px; text-align:right; color:{rc_col}'>"
            f"{rc_str}</td>"
            f"<td style='padding:6px 8px; text-align:center; color:{bf_col}; font-weight:700'>"
            f"{bf_str}</td>"
            f"</tr>"
        )
    tbl += "</tbody></table>"
    st.markdown(tbl, unsafe_allow_html=True)

# ── Resilience breakdown ──────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
survived_names = [
    r["label"] for r in all_results
    if (len(r["cash_path_stressed"]) > 12 and r["cash_path_stressed"][12] > 0)
]
failed_names   = [
    r["label"] for r in all_results
    if (len(r["cash_path_stressed"]) > 12 and r["cash_path_stressed"][12] <= 0)
]

if survived_names or failed_names:
    surv_str = ", ".join(survived_names) if survived_names else "none"
    fail_str = ", ".join(failed_names)   if failed_names   else "none"
    st.markdown(
        f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
        f"border-radius:10px; padding:1rem 1.2rem; font-size:0.86rem; color:{C['muted']}'>"
        f"<b style='color:{C['text']}'>Resilience breakdown</b> "
        f"(positive cash at month 12)<br>"
        f"<span style='color:{C['green']}'>✓ Survive:</span> {surv_str}<br>"
        f"<span style='color:{C['red']}'>✗ Cash depleted:</span> {fail_str}"
        f"</div>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Navigation
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
if st.button("Continue →  Report Center", type="primary"):
    st.switch_page("pages/7_Report_Center.py")

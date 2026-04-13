"""
Allocation Engine — Step 5
Where Your Next Dollar Should Go.
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
from src.analysis.allocation_engine import (
    recommend,
    explain_recommendation,
)
from src.utils.formatting import fmt_percent

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Allocation Engine | MoneyMap AI",
    page_icon="🎯",
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
    "gold":    "#e3b341",
}

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{ background-color: {C["bg"]}; }}
[data-testid="stSidebar"]          {{ background-color: {C["surface"]}; }}
[data-testid="stMetric"]           {{
    background-color: {C["surface"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    padding: 0.8rem 1rem;
}}
[data-testid="stMetricLabel"]  {{ color: {C["muted"]} !important; font-size: 0.8rem; }}
[data-testid="stMetricValue"]  {{ color: {C["text"]}  !important; }}
.stExpander {{
    border: 1px solid {C["border"]} !important;
    border-radius: 10px !important;
    background: {C["surface"]};
}}
.stExpander summary {{
    color: {C["text"]} !important;
    font-weight: 600 !important;
}}
div[data-testid="stHorizontalBlock"] > div {{ gap: 0.5rem; }}
hr {{ border-color: {C["border"]}; }}

/* ── Allocation option cards ─────────────────────────────────────────── */
.alloc-card {{
    background: {C["surface"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    padding: 1rem 1.1rem;
    height: 100%;
    box-sizing: border-box;
    transition: border-color 0.2s;
}}
.alloc-card:hover {{ border-color: {C["blue"]}80; }}

/* ── Top-recommendation hero card ────────────────────────────────────── */
.hero-card {{
    background: linear-gradient(135deg, {C["surface2"]} 0%, #1a2540 100%);
    border: 1px solid {C["gold"]}60;
    border-left: 5px solid {C["gold"]};
    border-radius: 14px;
    padding: 1.6rem 2rem;
    margin-bottom: 1.8rem;
}}

/* ── Score bar ───────────────────────────────────────────────────────── */
.score-track {{
    height: 6px;
    background: {C["border"]};
    border-radius: 4px;
    margin: 6px 0 10px;
    overflow: hidden;
}}

/* ── Risk badge ──────────────────────────────────────────────────────── */
.badge {{
    display: inline-block;
    border-radius: 5px;
    padding: 2px 9px;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}}
.badge-none   {{ background: {C["green"]}22; color: {C["green"]}; }}
.badge-low    {{ background: {C["blue"]}22;  color: {C["blue"]};  }}
.badge-medium {{ background: {C["yellow"]}22; color: {C["yellow"]}; }}
.badge-high   {{ background: {C["red"]}22;   color: {C["red"]};   }}

/* ── Regime table ────────────────────────────────────────────────────── */
.regime-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
.regime-table th {{
    text-align: left;
    padding: 0.5rem 0.8rem;
    color: {C["muted"]};
    font-weight: 600;
    border-bottom: 1px solid {C["border"]};
}}
.regime-table td {{
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid {C["border"]}55;
    color: {C["text"]};
    vertical-align: top;
}}
.regime-table tr:last-child td {{ border-bottom: none; }}
</style>
""", unsafe_allow_html=True)

require_mode()
require_raw_data()
require_scenarios()

# ─────────────────────────────────────────────────────────────────────────────
# Session state & context builder
# ─────────────────────────────────────────────────────────────────────────────

mode: str = st.session_state["mode"]
raw_df    = st.session_state["raw_df"]
macro     = st.session_state.get("macro", {}) or {}
scenarios = st.session_state.get("scenarios", {}) or {}
sp        = st.session_state.get("scenario_params", {}) or {}


@st.cache_data(show_spinner=False)
def _parse_personal(df):
    from src.data_loader import parse_personal_csv
    from src.analysis.financial_health import analyze_personal_health
    parsed = parse_personal_csv(df)
    return analyze_personal_health(parsed)


@st.cache_data(show_spinner=False)
def _parse_business(df):
    from src.data_loader import parse_business_csv
    from src.analysis.financial_health import analyze_business_health
    parsed = parse_business_csv(df)
    return analyze_business_health(parsed)


def _build_context(mode: str) -> dict:
    fh: dict = {}

    if mode == "personal":
        if raw_df is not None:
            try:
                h = _parse_personal(raw_df)
                fh = {
                    "monthly_income":        h["monthly_income"],
                    "monthly_expenses":      h["monthly_expenses"],
                    "savings_rate":          h["savings_rate"],
                    "emergency_fund_months": h["emergency_fund_months"],
                    "net_cash":              h["net_cash"],
                }
            except Exception:
                pass

        # Fill gaps / add debt+portfolio from scenario_params
        fh.setdefault("monthly_income",        float(sp.get("monthly_income",    5_500.0)))
        fh.setdefault("monthly_expenses",      float(sp.get("monthly_expenses",  4_500.0)))
        fh.setdefault("net_cash",              float(sp.get("savings",          13_000.0)))
        fh["debt_rate"]       = float(sp.get("debt_rate",       0.07))
        fh["debt_balance"]    = float(sp.get("debt_balance",   15_000.0))
        fh["portfolio_value"] = float(sp.get("portfolio_value", 25_000.0))
        fh["expected_return"] = float(sp.get("expected_return",     0.08))

        # Derive EF months from savings if health didn't provide it
        if "emergency_fund_months" not in fh or fh.get("emergency_fund_months", 0) == 0:
            savings_val = float(sp.get("savings", fh["net_cash"]))
            monthly_exp = fh["monthly_expenses"]
            fh["emergency_fund_months"] = savings_val / monthly_exp if monthly_exp > 0 else 0.0

        if "savings_rate" not in fh:
            inc = fh["monthly_income"]
            exp = fh["monthly_expenses"]
            fh["savings_rate"] = max(0.0, (inc - exp) / inc) if inc > 0 else 0.0

    else:  # business
        if raw_df is not None:
            try:
                h = _parse_business(raw_df)
                fh = {
                    "monthly_revenue":   h["monthly_revenue"],
                    "monthly_expenses":  h["monthly_expenses"],
                    "gross_margin_pct":  h["gross_margin_pct"],
                    "net_margin_pct":    h["net_margin_pct"],
                    "burn_rate":         h["burn_rate"],
                    "runway_months":     h["runway_months"],
                    "revenue_growth":    h["revenue_trend"].get("pct_change_avg", 0.0),
                }
            except Exception:
                pass

        fh.setdefault("monthly_revenue",  float(sp.get("monthly_revenue",   47_000.0)))
        fh.setdefault("monthly_expenses", float(sp.get("monthly_expenses",  40_000.0)))
        fh.setdefault("gross_margin_pct", 0.15)
        fh.setdefault("net_margin_pct",   0.05)
        fh.setdefault("burn_rate",        0.0)
        fh.setdefault("revenue_growth",   float(sp.get("growth_rate", 0.0)) / 12.0)
        fh["cash_balance"]     = float(sp.get("cash_balance",      88_000.0))
        fh["debt_rate"]        = float(sp.get("debt_rate",              0.07))
        fh["debt_balance"]     = float(sp.get("debt_balance",       50_000.0))
        fh["marketing_budget"] = float(sp.get("marketing_budget",    5_000.0))

        if fh.get("runway_months") is None:
            net_mo = fh["monthly_revenue"] - fh["monthly_expenses"]
            if net_mo < 0:
                fh["runway_months"] = fh["cash_balance"] / abs(net_mo)

    macro_summary = {
        "current_fed_rate":     float(macro.get("current_fed_rate")     or 5.0),
        "current_inflation":    float(macro.get("current_inflation")    or 3.2),
        "current_unemployment": float(macro.get("current_unemployment") or 4.0),
        "yield_spread":         float(macro.get("yield_spread")         or 0.5),
        "sp500_ytd_return":     macro.get("sp500_ytd_return"),
    }
    regime = str(macro.get("regime", "cautious") or "cautious").lower()

    return {
        "financial_health": fh,
        "macro_summary":    macro_summary,
        "regime":           regime,
        "risk_profile":     "moderate",
        "scenarios":        scenarios,
        "mode":             mode,
    }


ctx = _build_context(mode)
fh      = ctx["financial_health"]
ms      = ctx["macro_summary"]
regime  = ctx["regime"]

# ─────────────────────────────────────────────────────────────────────────────
# Regime display metadata
# ─────────────────────────────────────────────────────────────────────────────

_REGIME_META = {
    "risk_on":          {"label": "Risk-On",          "color": C["green"],  "icon": "📈"},
    "cautious":         {"label": "Cautious",          "color": C["yellow"], "icon": "⚖️"},
    "risk_off":         {"label": "Risk-Off",          "color": C["orange"], "icon": "🛡️"},
    "recession_warning":{"label": "Recession Warning", "color": C["red"],    "icon": "⚠️"},
}
rm = _REGIME_META.get(regime, _REGIME_META["cautious"])

# ─────────────────────────────────────────────────────────────────────────────
# Run engine
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Computing allocation priorities…"):
    result  = recommend(ctx, mode)
    ranked  = result["ranked"]
    top_rec = result["top_recommendation"]
    explanation = explain_recommendation(ranked, ctx)

st.session_state["allocation"] = result

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<div style='margin-bottom:0.2rem'>"
    f"<span style='background:{rm['color']}22; color:{rm['color']}; "
    f"border-radius:5px; padding:3px 10px; font-size:0.78rem; font-weight:700; "
    f"letter-spacing:0.05em; text-transform:uppercase'>"
    f"{rm['icon']} {rm['label']} Regime</span>"
    f"&nbsp;&nbsp;"
    f"<span style='background:{C['surface']}; color:{C['muted']}; "
    f"border-radius:5px; padding:3px 10px; font-size:0.78rem; border:1px solid {C['border']}'>"
    f"{'Personal' if mode == 'personal' else 'Business'} Mode</span>"
    f"</div>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<h1 style='color:{C['text']}; font-size:2.2rem; margin:0.4rem 0 0.15rem; "
    f"letter-spacing:-0.02em'>Where Your Next Dollar Should Go</h1>"
    f"<p style='color:{C['muted']}; margin:0 0 1.2rem; font-size:1rem'>"
    f"Priority-scored recommendations based on your finances, macro regime, and scenario outlook.</p>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Context metrics strip
# ─────────────────────────────────────────────────────────────────────────────

fed_rate  = ms["current_fed_rate"]
inflation = ms["current_inflation"]
spread    = ms["yield_spread"]

if mode == "personal":
    ef_months = fh.get("emergency_fund_months", 0.0)
    debt_rate = fh.get("debt_rate", 0.0) * 100
    sav_rate  = fh.get("savings_rate", 0.0)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Fed Funds Rate",     f"{fed_rate:.1f}%",
              delta=f"Real rate {fed_rate - inflation:+.1f}%", delta_color="off")
    m2.metric("Inflation (CPI)",    f"{inflation:.1f}%",
              delta="High" if inflation > 4 else ("Moderate" if inflation > 2.5 else "Low"),
              delta_color="inverse" if inflation > 4 else ("off" if inflation > 2.5 else "normal"))
    m3.metric("Yield Spread (10-2)", f"{spread:+.2f}pp",
              delta="Inverted" if spread < 0 else "Normal",
              delta_color="inverse" if spread < 0 else "normal")
    m4.metric("Emergency Fund",     f"{ef_months:.1f} mo",
              delta="Critical" if ef_months < 1 else ("Below target" if ef_months < 3 else "Healthy"),
              delta_color="inverse" if ef_months < 3 else "normal")
    m5.metric("Savings Rate",       fmt_percent(sav_rate),
              delta="Below 20%" if sav_rate < 0.20 else "On track",
              delta_color="inverse" if sav_rate < 0.20 else "normal")

else:
    runway      = fh.get("runway_months")
    gross_margin = fh.get("gross_margin_pct", 0.0)
    rev_growth  = fh.get("revenue_growth", 0.0) * 100

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Fed Funds Rate",  f"{fed_rate:.1f}%",
              delta=f"Real rate {fed_rate - inflation:+.1f}%", delta_color="off")
    m2.metric("Inflation (CPI)", f"{inflation:.1f}%",
              delta="High" if inflation > 4 else "Moderate",
              delta_color="inverse" if inflation > 4 else "off")
    m3.metric("Cash Runway",
              f"{runway:.1f} mo" if runway is not None else "Profitable",
              delta="Critical" if runway is not None and runway < 3 else
                    ("Low" if runway is not None and runway < 6 else "Healthy"),
              delta_color="inverse" if runway is not None and runway < 6 else "normal")
    m4.metric("Gross Margin",    fmt_percent(gross_margin),
              delta="Healthy" if gross_margin > 0.20 else "Thin",
              delta_color="normal" if gross_margin > 0.20 else "inverse")
    m5.metric("Revenue Growth",  f"{rev_growth:+.1f}%/mo",
              delta="Growing" if rev_growth > 0 else "Declining",
              delta_color="normal" if rev_growth > 0 else "inverse")

st.markdown("<hr style='margin:1rem 0 1.5rem'>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Hero card — top recommendation
# ─────────────────────────────────────────────────────────────────────────────

top = ranked[0]
top_score = top["score"]
top_sc = C["green"] if top_score >= 70 else (C["yellow"] if top_score >= 40 else C["red"])
top_risk_class = f"badge-{top['risk_level']}"

st.markdown(
    f"<div class='hero-card'>"
    f"<div style='font-size:0.78rem; color:{C['gold']}; font-weight:700; "
    f"text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.5rem'>"
    f"⭐ Top Recommendation</div>"
    f"<div style='display:flex; justify-content:space-between; align-items:flex-start; "
    f"flex-wrap:wrap; gap:0.5rem'>"
    f"<div style='flex:1; min-width:260px'>"
    f"<div style='font-size:1.55rem; font-weight:800; color:{C['text']}; "
    f"letter-spacing:-0.01em; margin-bottom:0.35rem'>{top['label']}</div>"
    f"<div style='font-size:0.92rem; color:{C['muted']}; line-height:1.65; "
    f"max-width:620px'>{top_rec}</div>"
    f"</div>"
    f"<div style='display:flex; flex-direction:column; align-items:flex-end; gap:8px'>"
    f"<div style='font-size:2.2rem; font-weight:900; color:{top_sc}; "
    f"line-height:1'>{top_score}</div>"
    f"<div style='font-size:0.72rem; color:{C['muted']}; margin-top:-4px'>/ 100</div>"
    f"<span class='badge {top_risk_class}'>Risk: {top['risk_level']}</span>"
    f"</div>"
    f"</div>"
    f"<div style='margin-top:0.9rem; height:6px; background:{C['border']}; "
    f"border-radius:4px; overflow:hidden'>"
    f"<div style='height:6px; width:{top_score}%; background:{top_sc}; "
    f"border-radius:4px'></div>"
    f"</div>"
    f"<div style='margin-top:0.6rem; font-size:0.82rem; color:{C['muted']}'>"
    f"<b style='color:{C['text']}'>Expected benefit:</b> {top['expected_benefit']}"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# All recommendations — card grid
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<h3 style='color:{C['text']}; font-size:1.15rem; font-weight:700; "
    f"margin:0.2rem 0 0.8rem; padding-bottom:0.4rem; "
    f"border-bottom:1px solid {C['border']}'>All Options — Ranked</h3>",
    unsafe_allow_html=True,
)

# Build priority-score bar chart (right column)
chart_col, grid_col = st.columns([1, 1.8], gap="large")

with chart_col:
    recs_rev = list(reversed(ranked))
    labels   = [r["label"] for r in recs_rev]
    scores   = [r["score"] for r in recs_rev]
    bar_clrs = [
        C["green"]  if s >= 70 else
        C["yellow"] if s >= 40 else
        C["red"]
        for s in scores
    ]

    fig = go.Figure(go.Bar(
        x=scores, y=labels,
        orientation="h",
        marker=dict(color=bar_clrs, line=dict(width=0)),
        text=[f"{s}" for s in scores],
        textposition="inside",
        textfont=dict(color="#0e1117", size=11, family="'JetBrains Mono', monospace"),
        customdata=[[r["risk_level"]] for r in recs_rev],
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Score: %{x}/100<br>"
            "Risk: %{customdata[0]}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["surface"],
        font=dict(color=C["text"], family="Inter, sans-serif", size=12),
        margin=dict(l=10, r=20, t=10, b=10),
        height=max(260, len(ranked) * 40 + 40),
        xaxis=dict(
            range=[0, 108],
            gridcolor=C["border"],
            tickfont=dict(color=C["muted"]),
            title=dict(text="Priority Score", font=dict(color=C["muted"], size=11)),
        ),
        yaxis=dict(
            gridcolor="rgba(0,0,0,0)",
            tickfont=dict(color=C["text"], size=11),
        ),
    )
    st.plotly_chart(fig, width='stretch')

    # Legend
    st.markdown(
        f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
        f"border-radius:8px; padding:0.6rem 0.9rem; font-size:0.78rem'>"
        f"<div style='color:{C['muted']}; margin-bottom:4px; font-weight:700'>Score Guide</div>"
        f"<div style='display:flex; gap:1rem; flex-wrap:wrap'>"
        f"<span style='color:{C['green']}'>■ 70–100 High priority</span>"
        f"<span style='color:{C['yellow']}'>■ 40–69 Moderate</span>"
        f"<span style='color:{C['red']}'>■ 0–39 Lower priority</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

with grid_col:
    # Render cards in pairs (2 per row)
    for i in range(0, len(ranked), 2):
        cols = st.columns(2, gap="small")
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(ranked):
                break
            rec   = ranked[idx]
            rank  = idx + 1
            score = rec["score"]
            sc    = (C["green"]  if score >= 70 else
                     C["yellow"] if score >= 40 else C["red"])
            risk_cls = f"badge-{rec['risk_level']}"

            with col:
                st.markdown(
                    f"<div class='alloc-card' style='border-left:3px solid {sc}'>"
                    # ── header row
                    f"<div style='display:flex; justify-content:space-between; "
                    f"align-items:center; margin-bottom:4px'>"
                    f"<div style='display:flex; align-items:center; gap:7px'>"
                    f"<span style='background:{sc}22; color:{sc}; border-radius:50%; "
                    f"width:22px; height:22px; display:inline-flex; align-items:center; "
                    f"justify-content:center; font-size:0.72rem; font-weight:800'>#{rank}</span>"
                    f"<span style='color:{C['text']}; font-weight:700; font-size:0.92rem'>"
                    f"{rec['label']}</span>"
                    f"</div>"
                    f"<span style='color:{sc}; font-weight:800; font-size:0.88rem'>{score}</span>"
                    f"</div>"
                    # ── score bar
                    f"<div class='score-track'>"
                    f"<div style='height:6px; width:{score}%; background:{sc}; "
                    f"border-radius:4px'></div>"
                    f"</div>"
                    # ── reasoning
                    f"<p style='color:{C['muted']}; font-size:0.8rem; margin:0 0 8px; "
                    f"line-height:1.55'>{rec['reasoning']}</p>"
                    # ── benefit + badge row
                    f"<div style='display:flex; justify-content:space-between; "
                    f"align-items:flex-end; gap:6px; flex-wrap:wrap'>"
                    f"<span style='color:{C['text']}; font-size:0.78rem; flex:1'>"
                    f"<b>Benefit:</b> {rec['expected_benefit'][:80]}"
                    f"{'…' if len(rec['expected_benefit']) > 80 else ''}</span>"
                    f"<span class='badge {risk_cls}'>{rec['risk_level']} risk</span>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

# ─────────────────────────────────────────────────────────────────────────────
# Why this recommendation?
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)

with st.expander("💡  Why this recommendation? — Full reasoning chain", expanded=False):
    st.markdown(
        f"<div style='padding:0.5rem 0; line-height:1.8; color:{C['muted']}; font-size:0.91rem'>"
        + explanation.replace("\n\n", "<br><br>")
                      .replace("**", "<b>").replace("</b>", "</b>")  # md bold → html
        + "</div>",
        unsafe_allow_html=True,
    )
    # Quick visual — ranked scores as a clean table
    st.markdown(
        f"<table style='width:100%; border-collapse:collapse; font-size:0.82rem; "
        f"margin-top:1rem'>"
        f"<thead><tr>"
        f"<th style='text-align:left; padding:6px 10px; color:{C['muted']}; "
        f"border-bottom:1px solid {C['border']}'>Option</th>"
        f"<th style='text-align:right; padding:6px 10px; color:{C['muted']}; "
        f"border-bottom:1px solid {C['border']}'>Score</th>"
        f"<th style='padding:6px 10px; color:{C['muted']}; "
        f"border-bottom:1px solid {C['border']}'>Risk</th>"
        f"</tr></thead><tbody>"
        + "".join(
            f"<tr>"
            f"<td style='padding:5px 10px; color:{C['text']}'>{r['label']}</td>"
            f"<td style='padding:5px 10px; text-align:right; font-weight:700; "
            f"color:{ C['green'] if r['score']>=70 else C['yellow'] if r['score']>=40 else C['red'] }'>"
            f"{r['score']}</td>"
            f"<td style='padding:5px 10px'>"
            f"<span class='badge badge-{r['risk_level']}'>{r['risk_level']}</span>"
            f"</td>"
            f"</tr>"
            for r in ranked
        )
        + "</tbody></table>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# What if the economy changes? — regime sensitivity table
# ─────────────────────────────────────────────────────────────────────────────

_ALL_REGIMES = [
    ("risk_on",           "📈 Risk-On",          C["green"]),
    ("cautious",          "⚖️ Cautious",          C["yellow"]),
    ("risk_off",          "🛡️ Risk-Off",          C["orange"]),
    ("recession_warning", "⚠️ Recession Warning", C["red"]),
]


@st.cache_data(show_spinner=False, ttl=300)
def _regime_sensitivity(ctx_frozen: tuple, mode: str) -> list:
    """Run recommend() for each of the 4 regimes, hold everything else constant."""
    import copy
    base_ctx = dict(ctx_frozen)
    rows = []
    for regime_key, regime_label, color in _ALL_REGIMES:
        c = copy.deepcopy(base_ctx)
        c["regime"] = regime_key
        res = recommend(c, mode)
        top1 = res["ranked"][0]
        top2 = res["ranked"][1] if len(res["ranked"]) > 1 else {}
        rows.append({
            "regime_key":   regime_key,
            "regime_label": regime_label,
            "color":        color,
            "top_label":    top1["label"],
            "top_score":    top1["score"],
            "top_reason":   top1["reasoning"],
            "second_label": top2.get("label", ""),
            "second_score": top2.get("score", 0),
        })
    return rows


with st.expander("🌐  What if the economy changes? — Regime sensitivity", expanded=False):
    st.markdown(
        f"<p style='color:{C['muted']}; font-size:0.88rem; margin:0 0 1rem'>"
        "The table below shows how your #1 allocation recommendation shifts under each "
        "macro regime — holding your personal financial profile constant.</p>",
        unsafe_allow_html=True,
    )

    # Build a hashable context for caching
    _ctx_for_cache = {
        k: (tuple(sorted(v.items())) if isinstance(v, dict) else v)
        for k, v in ctx.items()
        if k != "scenarios"
    }
    try:
        regime_rows = _regime_sensitivity(tuple(sorted(str(ctx).split(","))), mode)
    except Exception:
        # Fallback: run without cache if serialisation fails
        import copy
        regime_rows = []
        for rk, rl, rc in _ALL_REGIMES:
            c = copy.deepcopy(ctx)
            c["regime"] = rk
            res = recommend(c, mode)
            top1 = res["ranked"][0]
            top2 = res["ranked"][1] if len(res["ranked"]) > 1 else {}
            regime_rows.append({
                "regime_key":   rk,
                "regime_label": rl,
                "color":        rc,
                "top_label":    top1["label"],
                "top_score":    top1["score"],
                "top_reason":   top1["reasoning"],
                "second_label": top2.get("label", ""),
                "second_score": top2.get("score", 0),
            })

    # Highlight current regime
    table_html = (
        "<table class='regime-table'>"
        "<thead><tr>"
        "<th>Regime</th>"
        "<th>#1 Recommendation</th>"
        "<th>Score</th>"
        "<th>#2 Recommendation</th>"
        "<th>Key Logic</th>"
        "</tr></thead><tbody>"
    )
    for row in regime_rows:
        is_current = row["regime_key"] == regime
        row_bg = f"background:{C['surface2']};" if is_current else ""
        current_tag = (
            f" <span style='background:{row['color']}22; color:{row['color']}; "
            f"border-radius:4px; padding:1px 6px; font-size:0.7rem; font-weight:700'>current</span>"
            if is_current else ""
        )
        score_color = (C["green"]  if row["top_score"] >= 70 else
                       C["yellow"] if row["top_score"] >= 40 else C["red"])
        second_suffix = ""
        if row["second_label"]:
            second_suffix = (
                f"&nbsp;<span style='color:{C['muted']}; font-size:0.78rem'>"
                f"({row['second_score']})</span>"
            )
        table_html += (
            f"<tr style='{row_bg}'>"
            f"<td style='font-weight:700; color:{row['color']}; white-space:nowrap'>"
            f"{row['regime_label']}{current_tag}</td>"
            f"<td style='font-weight:600; color:{C['text']}'>{row['top_label']}</td>"
            f"<td style='font-weight:800; color:{score_color}; text-align:center'>"
            f"{row['top_score']}</td>"
            f"<td style='color:{C['muted']}'>{row['second_label']}{second_suffix}</td>"
            f"<td style='color:{C['muted']}; font-size:0.82rem; max-width:280px'>"
            f"{row['top_reason'][:120]}{'…' if len(row['top_reason']) > 120 else ''}</td>"
            f"</tr>"
        )
    table_html += "</tbody></table>"

    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown(
        f"<p style='color:{C['muted']}; font-size:0.78rem; margin-top:0.8rem'>"
        "Scores and rankings above hold your personal financials constant — only the "
        "macro regime changes. Use this to stress-test how sensitive your plan is to "
        "economic conditions.</p>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Navigation
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
if st.button("Continue →  Stress Test", type="primary"):
    st.switch_page("pages/6_Stress_Test.py")

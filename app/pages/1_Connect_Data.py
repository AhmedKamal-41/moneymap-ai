# -*- coding: utf-8 -*-
"""
Connect Data — Step 1
Upload a CSV / XLSX or use sample data to connect your financial information.
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

import io
import pandas as pd
import streamlit as st

from page_guards import require_mode
from src.data_loader import parse_personal_csv, parse_business_csv, compute_summary

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Connect Data | MoneyMap AI",
    page_icon="🔗",
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
    "gold":    "#e3b341",
    "purple":  "#a371f7",
}

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{ background-color: {C["bg"]}; }}
[data-testid="stSidebar"]          {{ background-color: {C["surface"]}; }}
[data-testid="stTabs"]             {{ background: transparent; }}
[data-testid="stTabsContent"]      {{ background: transparent; }}

/* Tab bar */
button[data-baseweb="tab"] {{
    color: {C["muted"]} !important;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.5rem 1.4rem;
    border-radius: 6px 6px 0 0;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    color: {C["text"]} !important;
    border-bottom: 2px solid {C["blue"]} !important;
}}

/* File uploader */
[data-testid="stFileUploadDropzone"] {{
    background: {C["surface"]} !important;
    border: 2px dashed {C["border"]} !important;
    border-radius: 12px !important;
    transition: border-color 0.2s;
}}
[data-testid="stFileUploadDropzone"]:hover {{
    border-color: {C["blue"]} !important;
}}

/* Expanders */
.stExpander {{
    border: 1px solid {C["border"]} !important;
    border-radius: 10px !important;
    background: {C["surface"]};
    margin-bottom: 0.5rem !important;
}}
.stExpander summary {{
    color: {C["text"]} !important;
    font-weight: 600 !important;
}}

/* Number / text inputs */
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"]   input {{
    background: {C["surface2"]} !important;
    color: {C["text"]} !important;
    border-color: {C["border"]} !important;
}}

/* Metric cards */
[data-testid="stMetric"] {{
    background: {C["surface"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    padding: 0.75rem 1rem;
}}
[data-testid="stMetricLabel"] {{ color: {C["muted"]} !important; font-size: 0.78rem; }}
[data-testid="stMetricValue"] {{ color: {C["text"]}  !important; }}

/* Dataframe */
[data-testid="stDataFrame"] {{ border: 1px solid {C["border"]}; border-radius: 8px; }}

hr {{ border-color: {C["border"]}; }}
div[data-testid="stHorizontalBlock"] > div {{ gap: 0.5rem; }}
</style>
""", unsafe_allow_html=True)

require_mode()
_mode: str = st.session_state["mode"]
_sample_path = {
    "personal": os.path.join(_root, "data", "sample", "sample_personal.csv"),
    "business": os.path.join(_root, "data", "sample", "sample_business.csv"),
}

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    f"<h1 style='font-size:2rem; font-weight:900; color:{C['text']}; margin-bottom:0.1rem'>"
    f"Connect Your Financial Data</h1>"
    f"<p style='color:{C['muted']}; font-size:0.92rem; margin-top:0'>"
    f"Upload a CSV or XLSX file, or explore with sample data. "
    f"All processing happens locally &mdash; nothing is stored externally.</p>",
    unsafe_allow_html=True,
)

_badge_color = C["blue"] if _mode == "personal" else C["purple"]
_badge_label = "Personal Mode" if _mode == "personal" else "Business Mode"
st.markdown(
    f"<span style='background:{_badge_color}22; color:{_badge_color}; "
    f"border-radius:6px; padding:3px 12px; font-size:0.78rem; font-weight:700; "
    f"letter-spacing:0.04em; text-transform:uppercase'>{_badge_label}</span>"
    f"<span style='color:{C['muted']}; font-size:0.78rem; margin-left:12px'>"
    f"Not the right mode? Change it on the home page.</span>",
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse(source, mode: str) -> pd.DataFrame:
    """Run the appropriate parser for the given mode."""
    if mode == "personal":
        return parse_personal_csv(source)
    return parse_business_csv(source)


def _read_xlsx(uploaded_file) -> io.BytesIO:
    """Convert an XLSX UploadedFile to a BytesIO CSV in memory."""
    data = uploaded_file.read()
    xls_df = pd.read_excel(io.BytesIO(data))
    buf = io.BytesIO()
    xls_df.to_csv(buf, index=False)
    buf.seek(0)
    return buf


def _fmt_currency(v) -> str:
    if v is None:
        return "N/A"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


def _fmt_percent(v) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.1f}%"


def _show_preview(df: pd.DataFrame):
    """Render a styled preview of the first 10 rows."""
    st.markdown(
        f"<div style='font-size:0.75rem; color:{C['muted']}; font-weight:700; "
        f"text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px'>"
        f"Data Preview &mdash; first 10 rows</div>",
        unsafe_allow_html=True,
    )
    preview = df.head(10).copy()
    # Convert Period columns to string for display
    for col in preview.columns:
        if hasattr(preview[col], "dt") or str(preview[col].dtype) == "period[M]":
            try:
                preview[col] = preview[col].astype(str)
            except Exception:
                pass
    st.dataframe(preview, width='stretch', hide_index=True)
    st.markdown(
        f"<div style='font-size:0.76rem; color:{C['muted']}; margin-top:2px'>"
        f"{len(df):,} total rows &nbsp;&bull;&nbsp; "
        f"{df.shape[1]} columns: {', '.join(df.columns.tolist())}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _show_personal_summary(s: dict):
    """Display computed personal finance summary as metric cards + category bars."""
    st.markdown(
        f"<div style='font-size:0.75rem; color:{C['muted']}; font-weight:700; "
        f"text-transform:uppercase; letter-spacing:0.06em; margin:1rem 0 0.5rem'>"
        f"Financial Summary</div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Avg Monthly Income",    _fmt_currency(s.get("monthly_income_avg")))
    m2.metric("Avg Monthly Expenses",  _fmt_currency(s.get("monthly_burn")))
    m3.metric("Savings Rate",          _fmt_percent(s.get("savings_rate")))
    m4.metric("Net Savings",           _fmt_currency(s.get("net_savings")))

    # Months covered
    st.markdown(
        f"<div style='font-size:0.78rem; color:{C['muted']}; margin-top:0.3rem'>"
        f"Data covers <b style='color:{C['text']}'>{s.get('n_months', 1)}</b> month(s)."
        f"</div>",
        unsafe_allow_html=True,
    )

    # Top spending categories
    top_cats = s.get("top_spending_categories", {})
    if top_cats:
        st.markdown(
            f"<div style='font-size:0.75rem; color:{C['muted']}; font-weight:700; "
            f"text-transform:uppercase; letter-spacing:0.06em; margin:0.9rem 0 0.4rem'>"
            f"Top Spending Categories</div>",
            unsafe_allow_html=True,
        )
        max_val = max(top_cats.values()) if top_cats else 1
        for cat, amt in top_cats.items():
            pct = amt / max_val
            bar_w = int(pct * 100)
            st.markdown(
                f"<div style='display:flex; align-items:center; gap:10px; margin-bottom:5px'>"
                f"<div style='width:110px; font-size:0.82rem; color:{C['muted']}; "
                f"text-transform:capitalize; flex-shrink:0'>{cat.replace('_',' ')}</div>"
                f"<div style='flex:1; background:{C['border']}; border-radius:4px; height:6px'>"
                f"<div style='width:{bar_w}%; background:{C['blue']}; "
                f"border-radius:4px; height:6px'></div></div>"
                f"<div style='width:70px; text-align:right; font-size:0.82rem; "
                f"color:{C['text']}'>${amt:,.0f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _show_business_summary(s: dict):
    """Display computed business finance summary as metric cards."""
    st.markdown(
        f"<div style='font-size:0.75rem; color:{C['muted']}; font-weight:700; "
        f"text-transform:uppercase; letter-spacing:0.06em; margin:1rem 0 0.5rem'>"
        f"Business Summary</div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Avg Monthly Revenue",  _fmt_currency(s.get("monthly_revenue_avg")))
    m2.metric("Avg Monthly Expenses", _fmt_currency(s.get("monthly_expense_avg")))
    m3.metric("Gross Margin",         _fmt_percent(s.get("gross_margin")))
    m4.metric("Net Income",           _fmt_currency(s.get("net_income")))

    m5, m6, m7, m8 = st.columns(4)
    runway = s.get("runway_months")
    m5.metric(
        "Cash Runway",
        f"{runway:.1f} mo" if runway is not None and runway != float("inf") else "Profitable",
    )
    m6.metric("Burn Rate",  _fmt_currency(s.get("burn_rate")) + "/mo")
    m7.metric("Months",     str(s.get("n_months", 1)))
    m8.metric("Total Revenue", _fmt_currency(s.get("total_revenue")))

    top_cats = s.get("top_expense_categories", {})
    if top_cats:
        st.markdown(
            f"<div style='font-size:0.75rem; color:{C['muted']}; font-weight:700; "
            f"text-transform:uppercase; letter-spacing:0.06em; margin:0.9rem 0 0.4rem'>"
            f"Top Expense Categories</div>",
            unsafe_allow_html=True,
        )
        max_val = max(top_cats.values()) if top_cats else 1
        for cat, amt in top_cats.items():
            bar_w = int((amt / max_val) * 100)
            st.markdown(
                f"<div style='display:flex; align-items:center; gap:10px; margin-bottom:5px'>"
                f"<div style='width:110px; font-size:0.82rem; color:{C['muted']}; "
                f"text-transform:capitalize; flex-shrink:0'>{cat.replace('_',' ')}</div>"
                f"<div style='flex:1; background:{C['border']}; border-radius:4px; height:6px'>"
                f"<div style='width:{bar_w}%; background:{C['orange']}; "
                f"border-radius:4px; height:6px'></div></div>"
                f"<div style='width:80px; text-align:right; font-size:0.82rem; "
                f"color:{C['text']}'>${amt:,.0f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def _show_summary(df: pd.DataFrame, mode: str):
    """Dispatcher for summary display."""
    s = compute_summary(df, mode)
    if mode == "personal":
        _show_personal_summary(s)
    else:
        _show_business_summary(s)
    return s


def _continue_button(df: pd.DataFrame, summary: dict, source_label: str):
    """
    Save the parsed data + summary to session_state and signal readiness.
    Shows a Continue button that navigates to the Financial Health page.
    """
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='background:{C['green']}18; border:1px solid {C['green']}40; "
        f"border-left:4px solid {C['green']}; border-radius:8px; "
        f"padding:0.65rem 1rem; font-size:0.85rem; color:{C['text']}; margin-bottom:1rem'>"
        f"<b style='color:{C['green']}'>Data ready.</b> "
        f"{len(df):,} rows loaded from {source_label}. "
        f"Click Continue to proceed to Financial Health analysis."
        f"</div>",
        unsafe_allow_html=True,
    )

    if st.button("Continue to Financial Health →", type="primary", width='content'):
        st.session_state["raw_df"]  = df
        st.session_state["summary"] = summary
        st.session_state["data_source_label"] = source_label
        st.switch_page("pages/2_Financial_Health.py")


# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_upload, tab_sample = st.tabs(["Upload Your Data", "Use Sample Data"])


# ── Tab 1: Upload ─────────────────────────────────────────────────────────────
with tab_upload:
    st.markdown(
        f"<p style='color:{C['muted']}; font-size:0.88rem; margin-bottom:1rem'>"
        f"Upload a CSV or XLSX file with at least a <code>date</code> and "
        f"<code>amount</code> column. Optional: <code>category</code>, <code>description</code>"
        f"{', <code>type</code>' if _mode == 'business' else ''}.</p>",
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Drop your file here",
        type=["csv", "xlsx"],
        label_visibility="collapsed",
        key="file_upload",
    )

    if uploaded is not None:
        # ── Parse ──────────────────────────────────────────────────────────────
        with st.spinner("Parsing your file…"):
            try:
                if uploaded.name.lower().endswith(".xlsx"):
                    source = _read_xlsx(uploaded)
                else:
                    source = uploaded

                df_upload = _parse(source, _mode)
                parse_error = None
            except Exception as exc:
                df_upload  = None
                parse_error = str(exc)

        if parse_error:
            st.markdown(
                f"<div style='background:{C['red']}18; border:1px solid {C['red']}40; "
                f"border-left:4px solid {C['red']}; border-radius:8px; "
                f"padding:0.75rem 1rem; font-size:0.86rem; color:{C['text']}'>"
                f"<b style='color:{C['red']}'>Could not parse your file.</b><br>"
                f"{parse_error}<br><br>"
                f"<span style='color:{C['muted']}'>"
                f"Required columns: <code>date</code>, <code>amount</code>. "
                f"Dates must be parseable (YYYY-MM-DD recommended). "
                f"Amounts may include $ signs and commas.</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<hr style='margin:0.8rem 0'>", unsafe_allow_html=True)
            _show_preview(df_upload)
            st.markdown("<hr style='margin:0.8rem 0'>", unsafe_allow_html=True)
            summary_upload = _show_summary(df_upload, _mode)
            _continue_button(df_upload, summary_upload, f"uploaded file '{uploaded.name}'")

    else:
        # ── Format hints when no file is loaded ────────────────────────────────
        hint_col1, hint_col2 = st.columns(2)
        with hint_col1:
            if _mode == "personal":
                st.markdown(
                    f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
                    f"border-radius:10px; padding:1rem 1.2rem; font-size:0.83rem'>"
                    f"<div style='color:{C['blue']}; font-weight:700; margin-bottom:0.5rem'>"
                    f"Personal CSV format</div>"
                    f"<code style='color:{C['muted']}'>date, amount, category, description</code>"
                    f"<div style='color:{C['muted']}; margin-top:0.6rem; line-height:1.7'>"
                    f"2024-01-01, -45.99, dining, Dinner at Nobu<br>"
                    f"2024-01-05, 3200.00, income, Payroll deposit<br>"
                    f"2024-01-07, -12.99, subscriptions, Netflix</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
                    f"border-radius:10px; padding:1rem 1.2rem; font-size:0.83rem'>"
                    f"<div style='color:{C['purple']}; font-weight:700; margin-bottom:0.5rem'>"
                    f"Business CSV format</div>"
                    f"<code style='color:{C['muted']}'>date, type, category, amount, description</code>"
                    f"<div style='color:{C['muted']}; margin-top:0.6rem; line-height:1.7'>"
                    f"2024-01-01, revenue, revenue, 28000, SaaS MRR<br>"
                    f"2024-01-01, expense, payroll, -8500, Engineering payroll<br>"
                    f"2024-01-02, expense, marketing, -3200, Google Ads</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        with hint_col2:
            st.markdown(
                f"<div style='background:{C['surface']}; border:1px solid {C['border']}; "
                f"border-radius:10px; padding:1rem 1.2rem; font-size:0.83rem'>"
                f"<div style='color:{C['gold']}; font-weight:700; margin-bottom:0.5rem'>"
                f"Tips</div>"
                f"<ul style='color:{C['muted']}; margin:0; padding-left:1.1rem; line-height:1.8'>"
                f"<li>Dates: YYYY-MM-DD or MM/DD/YYYY</li>"
                f"<li>Amounts: positive = income/revenue, negative = expense</li>"
                f"<li><code>category</code> is optional &mdash; we infer it</li>"
                f"<li>XLSX files are automatically converted</li>"
                f"<li>Export from Mint, YNAB, QuickBooks, or your bank</li>"
                f"</ul>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ── Tab 2: Sample Data ────────────────────────────────────────────────────────
with tab_sample:
    mode_label  = "Personal" if _mode == "personal" else "Business"
    sample_file = _sample_path[_mode]

    st.markdown(
        f"<p style='color:{C['muted']}; font-size:0.88rem; margin-bottom:1rem'>"
        f"No file handy? Load the built-in {mode_label.lower()} sample dataset "
        f"to explore MoneyMap AI's full feature set.</p>",
        unsafe_allow_html=True,
    )

    if st.button(
        f"Load Sample {mode_label} Data",
        type="primary",
        key="load_sample",
    ):
        st.session_state["_sample_loaded"] = True

    if st.session_state.get("_sample_loaded"):
        with st.spinner("Loading sample data…"):
            try:
                df_sample   = _parse(sample_file, _mode)
                sample_err  = None
            except Exception as exc:
                df_sample  = None
                sample_err = str(exc)

        if sample_err:
            st.error(f"Could not load sample data: {sample_err}", icon="⚠️")
        else:
            st.markdown(
                f"<div style='background:{C['blue']}18; border:1px solid {C['blue']}40; "
                f"border-left:4px solid {C['blue']}; border-radius:8px; "
                f"padding:0.55rem 1rem; font-size:0.84rem; color:{C['muted']}; "
                f"margin-bottom:0.8rem'>"
                f"<b style='color:{C['blue']}'>Sample dataset loaded.</b> "
                f"This is synthetic data generated for demonstration only.</div>",
                unsafe_allow_html=True,
            )
            st.markdown("<hr style='margin:0.6rem 0'>", unsafe_allow_html=True)
            _show_preview(df_sample)
            st.markdown("<hr style='margin:0.6rem 0'>", unsafe_allow_html=True)
            summary_sample = _show_summary(df_sample, _mode)
            _continue_button(df_sample, summary_sample, f"sample {mode_label.lower()} dataset")


# ─────────────────────────────────────────────────────────────────────────────
# Optional enrichment — Portfolio Info (personal only)
# ─────────────────────────────────────────────────────────────────────────────

if _mode == "personal":
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("Add Portfolio Info (optional)", expanded=False):
        st.markdown(
            f"<p style='color:{C['muted']}; font-size:0.85rem; margin-bottom:0.8rem'>"
            f"Add your investment portfolio so the Stress Test and Allocation Engine "
            f"can account for market risk on your holdings.</p>",
            unsafe_allow_html=True,
        )
        port_col1, port_col2 = st.columns(2)

        with port_col1:
            portfolio_value = st.number_input(
                "Current portfolio value ($)",
                min_value=0.0,
                value=float(st.session_state.get("scenario_params", {}).get("portfolio_value", 25_000.0)),
                step=1_000.0,
                format="%.0f",
                help="Total value of stocks, ETFs, mutual funds, crypto, etc.",
                key="port_value_input",
            )
            tickers_raw = st.text_input(
                "Holdings (tickers, comma-separated)",
                value=st.session_state.get("portfolio_tickers", ""),
                placeholder="e.g. VTI, AAPL, QQQ, BTC",
                help="Optional — used for display and future portfolio analytics.",
                key="port_tickers_input",
            )

        with port_col2:
            expected_return = st.number_input(
                "Expected annual return (%)",
                min_value=0.0,
                max_value=50.0,
                value=float(
                    st.session_state.get("scenario_params", {}).get("expected_return", 0.08)
                ) * 100,
                step=0.5,
                format="%.1f",
                help="Your long-run expected annual return (e.g. 8 for 8%).",
                key="port_return_input",
            )
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f"<div style='font-size:0.8rem; color:{C['muted']}; line-height:1.6'>"
                f"Typical benchmarks: &nbsp;"
                f"<b style='color:{C['text']}'>S&amp;P 500</b> ~10% (historical), &nbsp;"
                f"<b style='color:{C['text']}'>60/40 portfolio</b> ~7%"
                f"</div>",
                unsafe_allow_html=True,
            )

        if st.button("Save Portfolio Info", key="save_portfolio"):
            sp = dict(st.session_state.get("scenario_params", {}))
            sp["portfolio_value"]  = portfolio_value
            sp["expected_return"]  = expected_return / 100.0
            st.session_state["scenario_params"]   = sp
            st.session_state["portfolio_tickers"] = (
                [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
                if tickers_raw else []
            )
            st.success(
                f"Portfolio info saved: ${portfolio_value:,.0f} at "
                f"{expected_return:.1f}% expected return.",
                icon="✅",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Optional enrichment — Debt Info
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("<br>" if _mode == "business" else "", unsafe_allow_html=True)
with st.expander("Add Debt Info (optional)", expanded=False):
    st.markdown(
        f"<p style='color:{C['muted']}; font-size:0.85rem; margin-bottom:0.8rem'>"
        f"Providing debt details improves the allocation engine's recommendations "
        f"and stress-test accuracy.</p>",
        unsafe_allow_html=True,
    )
    debt_col1, debt_col2 = st.columns(2)

    _sp_now = st.session_state.get("scenario_params", {})
    with debt_col1:
        debt_balance = st.number_input(
            "Total debt balance ($)",
            min_value=0.0,
            value=float(_sp_now.get("debt_balance", 15_000.0 if _mode == "personal" else 50_000.0)),
            step=500.0,
            format="%.0f",
            help="Sum of all loans, credit cards, and lines of credit.",
            key="debt_balance_input",
        )
    with debt_col2:
        debt_rate_pct = st.number_input(
            "Average interest rate (%)",
            min_value=0.0,
            max_value=50.0,
            value=float(_sp_now.get("debt_rate", 0.07)) * 100,
            step=0.25,
            format="%.2f",
            help="Weighted average APR across all your debt (e.g. 7 for 7%).",
            key="debt_rate_input",
        )

    if st.button("Save Debt Info", key="save_debt"):
        sp = dict(st.session_state.get("scenario_params", {}))
        sp["debt_balance"] = debt_balance
        sp["debt_rate"]    = debt_rate_pct / 100.0
        st.session_state["scenario_params"] = sp
        st.success(
            f"Debt info saved: ${debt_balance:,.0f} at {debt_rate_pct:.2f}% APR.",
            icon="✅",
        )

# -*- coding: utf-8 -*-
"""
Report Center — Step 7
Your Recommendation Report: full analysis compiled, rendered, and downloadable.
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

from page_guards import (
    require_allocation,
    require_mode,
    require_raw_data,
    require_scenarios,
)
from src.analysis.report_builder import (
    build_report,
    report_to_markdown,
    report_to_pdf_bytes,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Report Center | MoneyMap AI",
    page_icon="📄",
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

div[data-testid="stDownloadButton"] > button {{
    width: 100%;
    border-radius: 8px;
    font-weight: 700;
    font-size: 0.9rem;
    padding: 0.55rem 1rem;
    transition: opacity 0.15s;
}}
div[data-testid="stDownloadButton"] > button:hover {{ opacity: 0.85; }}

.report-prose {{
    background: {C["surface"]};
    border: 1px solid {C["border"]};
    border-radius: 12px;
    padding: 2rem 2.4rem;
    line-height: 1.75;
    font-size: 0.93rem;
    color: {C["text"]};
}}
.report-prose h1 {{
    color: {C["text"]};
    font-size: 1.6rem;
    border-bottom: 2px solid {C["blue"]}40;
    padding-bottom: 0.4rem;
    margin-top: 0.4rem;
    margin-bottom: 0.6rem;
}}
.report-prose h2 {{
    color: {C["text"]};
    font-size: 1.15rem;
    border-bottom: 1px solid {C["border"]};
    padding-bottom: 0.3rem;
    margin-top: 1.6rem;
    margin-bottom: 0.5rem;
}}
.report-prose h3 {{
    color: {C["gold"]};
    font-size: 1rem;
    margin-top: 1.2rem;
    margin-bottom: 0.3rem;
}}
.report-prose table {{
    border-collapse: collapse;
    width: 100%;
    margin: 0.8rem 0;
    font-size: 0.86rem;
}}
.report-prose th {{
    background: {C["surface2"]};
    color: {C["blue"]};
    font-weight: 700;
    text-align: left;
    padding: 6px 10px;
    border: 1px solid {C["border"]};
}}
.report-prose td {{
    padding: 5px 10px;
    border: 1px solid {C["border"]};
    color: {C["text"]};
    vertical-align: top;
}}
.report-prose tr:nth-child(even) td {{ background: {C["surface2"]}; }}
.report-prose blockquote {{
    border-left: 3px solid {C["yellow"]};
    background: {C["surface2"]};
    border-radius: 0 8px 8px 0;
    margin: 0.8rem 0;
    padding: 0.6rem 1rem;
    color: {C["muted"]};
    font-size: 0.88rem;
}}
.report-prose strong {{ color: {C["text"]}; }}
.report-prose em     {{ color: {C["muted"]}; font-style: italic; }}
.report-prose hr {{
    border: none;
    border-top: 1px solid {C["border"]};
    margin: 1.4rem 0;
}}

.stExpander {{
    border: 1px solid {C["border"]} !important;
    border-radius: 10px !important;
    background: {C["surface"]};
    margin-bottom: 0.6rem !important;
}}
.stExpander summary {{
    color: {C["text"]} !important;
    font-weight: 600 !important;
}}
hr {{ border-color: {C["border"]}; }}
</style>
""", unsafe_allow_html=True)

require_mode()
require_raw_data()
require_scenarios()
require_allocation()


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

import json as _json


def _freeze(d: dict) -> str:
    """Serialize a dict to a JSON string for use as a hashable cache key.
    Values stay nested — round-tripping via json.loads() gives back real
    dicts/floats/ints rather than strings, so report_builder can call .get()."""
    return _json.dumps(d, default=str, sort_keys=True)


def _slim_scenarios(scenarios: dict) -> dict:
    """Drop large numpy arrays (percentile_paths, portfolio paths) before hashing."""
    _KEEP = {
        "median_outcome", "p5_outcome", "p25_outcome",
        "p75_outcome", "p95_outcome",
        "probability_of_negative", "months_until_negative",
    }
    out: dict = {}
    for k, sc in scenarios.items():
        if isinstance(sc, dict):
            out[k] = {sk: sv for sk, sv in sc.items() if sk in _KEEP}
    return out


@st.cache_data(show_spinner=False, ttl=300)
def _build_cached(
    mode: str,
    sp_json: str,
    macro_json: str,
    alloc_json: str,
    scenarios_json: str,
) -> dict:
    ss_proxy = {
        "mode":            mode,
        "scenario_params": _json.loads(sp_json),
        "macro":           _json.loads(macro_json),
        "allocation":      _json.loads(alloc_json),
        "scenarios":       _json.loads(scenarios_json),
    }
    return build_report(ss_proxy)


# ─────────────────────────────────────────────────────────────────────────────
# Read session state
# ─────────────────────────────────────────────────────────────────────────────

_mode      = st.session_state["mode"]
_sp        = dict(st.session_state.get("scenario_params", {}) or {})
_macro     = dict(st.session_state.get("macro", {}) or {})
_alloc_raw = dict(st.session_state.get("allocation", {}) or {})
_scenarios = dict(st.session_state.get("scenarios", {}) or {})

# Drop non-serialisable ranked list (large); keep only top_recommendation for cache key
_alloc_key = {k: v for k, v in _alloc_raw.items() if k != "ranked"}

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<h1 style='font-size:2rem; font-weight:900; color:{C['text']}; margin-bottom:0.1rem'>"
    f"Your Recommendation Report</h1>"
    f"<p style='color:{C['muted']}; font-size:0.92rem; margin-top:0'>"
    f"Full analysis compiled across all steps &mdash; review below or download.</p>",
    unsafe_allow_html=True,
)

badge_color = C["blue"] if _mode == "personal" else C["purple"]
badge_label = "Personal Mode" if _mode == "personal" else "Business Mode"
st.markdown(
    f"<span style='background:{badge_color}22; color:{badge_color}; "
    f"border-radius:6px; padding:3px 12px; font-size:0.78rem; font-weight:700; "
    f"letter-spacing:0.04em; text-transform:uppercase'>{badge_label}</span>",
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Build report
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Compiling your report…"):
    try:
        report = _build_cached(
            _mode,
            _freeze(_sp),
            _freeze(_macro),
            _freeze(_alloc_key),
            _freeze(_slim_scenarios(_scenarios)),
        )
        _err = None
    except Exception as exc:
        report = None
        _err = str(exc)

if _err or report is None:
    st.error(
        f"Could not compile the report: {_err or 'unknown error'}.",
        icon="⚠️",
    )
    st.markdown(
        "<p style='color:#8b949e'>Complete the workflow in order, then return here.</p>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Connect Data", width='stretch'):
            st.switch_page("pages/1_Connect_Data.py")
    with c2:
        if st.button("Scenario Lab", width='stretch'):
            st.switch_page("pages/4_Scenario_Lab.py")
    with c3:
        if st.button("Allocation Engine", width='stretch'):
            st.switch_page("pages/5_Allocation_Engine.py")
    st.stop()

md_text = report_to_markdown(report)

# ─────────────────────────────────────────────────────────────────────────────
# Download buttons
# ─────────────────────────────────────────────────────────────────────────────

_date_slug = report["generated_date"].replace(" ", "_").replace(":", "")
dl1, dl2, _gap = st.columns([1.6, 1.6, 5])

with dl1:
    try:
        pdf_bytes = report_to_pdf_bytes(report)
        st.download_button(
            label="\u2B07  Download as PDF",
            data=pdf_bytes,
            file_name=f"moneymap_report_{_mode}_{_date_slug}.pdf",
            mime="application/pdf",
            width='stretch',
        )
    except Exception as pdf_exc:
        st.warning(f"PDF unavailable: {pdf_exc}", icon="⚠️")

with dl2:
    st.download_button(
        label="\u2B07  Download as Markdown",
        data=md_text.encode("utf-8"),
        file_name=f"moneymap_report_{_mode}_{_date_slug}.md",
        mime="text/markdown",
        width='stretch',
    )

st.caption(
    "Educational tool only — not financial advice. See the Disclaimer below for full terms."
)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Render report inside styled container
# ─────────────────────────────────────────────────────────────────────────────

import re as _re


def _md_to_html(md: str) -> str:
    """
    Lightweight Markdown → HTML converter for the styled report container.
    Handles: headings, bold/italic, blockquotes, pipe tables, horizontal rules,
    and wraps bare paragraphs in <p> tags.
    """
    lines = md.split("\n")
    out: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Pipe tables ────────────────────────────────────────────────────────
        if (line.strip().startswith("|") and
                i + 1 < len(lines) and
                _re.match(r"^\s*\|[\s|\-:]+\|\s*$", lines[i + 1])):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip separator row
            body_rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                body_rows.append(cells)
                i += 1
            th = "".join(f"<th>{h}</th>" for h in headers)
            trs = "".join(
                "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
                for row in body_rows
            )
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>")
            continue

        # ── Headings ───────────────────────────────────────────────────────────
        m = _re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            text  = m.group(2)
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # ── Horizontal rule ────────────────────────────────────────────────────
        if _re.match(r"^---+\s*$", line.strip()):
            out.append("<hr>")
            i += 1
            continue

        # ── Blockquote ─────────────────────────────────────────────────────────
        if line.startswith("> "):
            content = line[2:]
            out.append(f"<blockquote>{content}</blockquote>")
            i += 1
            continue

        # ── Blank line (paragraph boundary) ───────────────────────────────────
        if not line.strip():
            out.append("")
            i += 1
            continue

        # ── Plain text / inline markdown ───────────────────────────────────────
        text = line
        text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = _re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         text)
        out.append(text)
        i += 1

    # Group consecutive non-tag lines into <p> paragraphs
    result: list[str] = []
    buf: list[str] = []

    def flush_buf():
        if buf:
            joined = " ".join(buf).strip()
            if joined:
                result.append(f"<p>{joined}</p>")
            buf.clear()

    for token in out:
        if token == "":
            flush_buf()
        elif token.startswith("<") and not token.startswith("<strong") and not token.startswith("<em"):
            flush_buf()
            result.append(token)
        else:
            buf.append(token)

    flush_buf()
    return "\n".join(result)


html_report = _md_to_html(md_text)

st.markdown(
    f"<div class='report-prose'>{html_report}</div>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Assumptions Used expander
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)

with st.expander("Assumptions Used", expanded=False):
    assm  = report.get("assumptions_used", {})
    mode_ = report.get("mode", "personal")

    data_src  = assm.get("data_source", "Fallback (demo)")
    src_color = C["green"] if "FRED" in data_src else C["yellow"]

    st.markdown(
        f"<div style='font-size:0.82rem; margin-bottom:1rem'>"
        f"<span style='color:{C['muted']}'>Market data source: </span>"
        f"<span style='color:{src_color}; font-weight:700'>{data_src}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    def _assm_section(title: str, rows: list[tuple[str, str]]):
        st.markdown(
            f"<div style='font-size:0.73rem; color:{C['muted']}; font-weight:700; "
            f"text-transform:uppercase; letter-spacing:0.06em; "
            f"border-bottom:1px solid {C['border']}; padding-bottom:4px; margin-bottom:6px'>"
            f"{title}</div>",
            unsafe_allow_html=True,
        )
        for lbl, val in rows:
            c1, c2 = st.columns([2, 3])
            c1.markdown(
                f"<div style='font-size:0.83rem; color:{C['muted']}; padding:3px 0'>{lbl}</div>",
                unsafe_allow_html=True,
            )
            c2.markdown(
                f"<div style='font-size:0.83rem; color:{C['text']}; padding:3px 0'>{val}</div>",
                unsafe_allow_html=True,
            )
        st.markdown("<br>", unsafe_allow_html=True)

    # Macro
    ms   = report.get("market_environment", {})
    ys   = ms.get("yield_spread")
    sp5  = ms.get("sp500_ytd_return")
    _assm_section("Market Indicators", [
        ("Fed Funds Rate",       f"{ms.get('current_fed_rate', 'N/A'):.2f}%"),
        ("CPI Inflation",        f"{ms.get('current_inflation', 'N/A'):.1f}%"),
        ("Unemployment",         f"{ms.get('current_unemployment', 'N/A'):.1f}%"),
        ("Yield Spread (10Y-2Y)",
         f"{ys:+.2f}%" if isinstance(ys, (int, float)) else "N/A"),
        ("S&P 500 YTD",
         f"{sp5:.1f}%" if isinstance(sp5, (int, float)) else "N/A"),
        ("Macro Regime",         report.get("regime", "N/A").replace("_", " ").title()),
    ])

    # Financial inputs
    if mode_ == "personal":
        _assm_section("Your Financial Inputs", [
            ("Monthly Income",    f"${assm.get('monthly_income', 0):,.0f}"),
            ("Monthly Expenses",  f"${assm.get('monthly_expenses', 0):,.0f}"),
            ("Savings",           f"${assm.get('savings', 0):,.0f}"),
            ("Debt APR",          f"{assm.get('debt_rate_pct', 0):.1f}%"),
            ("Debt Balance",      f"${assm.get('debt_balance', 0):,.0f}"),
            ("Portfolio Value",   f"${assm.get('portfolio_value', 0):,.0f}"),
            ("Expected Return",   f"{assm.get('expected_return_pct', 0):.1f}%"),
        ])
    else:
        _assm_section("Your Financial Inputs", [
            ("Monthly Revenue",   f"${assm.get('monthly_revenue', 0):,.0f}"),
            ("Monthly Expenses",  f"${assm.get('monthly_expenses', 0):,.0f}"),
            ("Cash Balance",      f"${assm.get('cash_balance', 0):,.0f}"),
            ("Debt APR",          f"{assm.get('debt_rate_pct', 0):.1f}%"),
            ("Debt Balance",      f"${assm.get('debt_balance', 0):,.0f}"),
            ("Marketing Budget",  f"${assm.get('marketing_budget', 0):,.0f}/mo"),
            ("Monthly Growth",    f"{assm.get('growth_rate_pct', 0):.2f}%"),
        ])

    # Model parameters footnote
    st.markdown(
        f"<div style='font-size:0.76rem; color:{C['border']}; "
        f"border-top:1px solid {C['border']}; padding-top:0.5rem'>"
        f"Monte Carlo: 5,000 paths/scenario &nbsp;&bull;&nbsp; "
        f"Stress tests: 5 historical scenarios &nbsp;&bull;&nbsp; "
        f"Horizon: 12 months (cash flow) / 252 trading days (portfolio)"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Disclaimer
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("Disclaimer", expanded=False):
    st.markdown(
        f"""<div style='font-size:0.86rem; color:{C['muted']}; line-height:1.85'>

<strong style='color:{C['text']}'>For educational purposes only &mdash; not financial advice.</strong>

<p>MoneyMap AI is a personal finance education and analysis tool. Nothing in this
application &mdash; including reports, recommendations, projections, stress tests,
or any other output &mdash; constitutes investment advice, financial advice, trading
advice, or any other form of professional advice. MoneyMap AI is not a registered
investment adviser, broker-dealer, financial planner, or tax professional.</p>

<p><strong style='color:{C['text']}'>Projections are not guarantees.</strong>
All forward-looking projections are generated from user-supplied inputs and
historical market data. Past performance is not indicative of future results.
Monte Carlo simulations model probabilistic outcomes but cannot predict the future.
Actual results may differ materially &mdash; and often will.</p>

<p><strong style='color:{C['text']}'>Market data may be delayed or estimated.</strong>
Macro indicators (Federal Funds Rate, CPI, unemployment, yield spread) are sourced
from public APIs (FRED) and may be delayed, estimated, or replaced by fallback values
when live data is unavailable. Always verify current figures from official sources
such as the Federal Reserve, U.S. Bureau of Labor Statistics, and the U.S. Treasury.</p>

<p><strong style='color:{C['text']}'>Consult a qualified professional.</strong>
Before making any investment, borrowing, spending, or savings decision, please consult
a licensed financial adviser, CPA, or legal professional who understands your complete
personal and financial situation. No tool can substitute for personalised advice.</p>

<p style='font-size:0.76rem; color:{C['border']}; border-top:1px solid {C['border']};
padding-top:0.5rem; margin-top:1rem'>
MoneyMap AI is provided &ldquo;as is&rdquo; without warranty of any kind.
The developers accept no liability whatsoever for financial decisions made
in reliance on this tool&rsquo;s output.
</p></div>""",
        unsafe_allow_html=True,
    )

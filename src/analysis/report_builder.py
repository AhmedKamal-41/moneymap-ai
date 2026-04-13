# -*- coding: utf-8 -*-
"""
report_builder.py
-----------------
Compile all MoneyMap AI analysis results into a structured report and
render it as clean Markdown or as a downloadable PDF (via fpdf2).

Public API
----------
build_report(session_state)    -> dict
report_to_markdown(report)     -> str
report_to_pdf_bytes(report)    -> bytes
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe(text: str) -> str:
    """Strip characters outside the latin-1 range (emoji, CJK, etc.)
    so fpdf2 core fonts don't raise UnicodeEncodeError."""
    if not isinstance(text, str):
        text = str(text)
    # Replace common emoji with text equivalents before stripping
    _EMOJI_MAP = {
        "\U0001f4c8": "[up]",  "\U0001f4c9": "[dn]",  "\U0001f3e6": "[bank]",
        "\U0001f9a0": "[bio]", "\U0001f4b0": "[money]","\U0001f4bc": "[biz]",
        "\U000026a0": "[warn]","\u2705": "[ok]", "\u274c": "[x]",
        "\U0001f6a8": "[alert]", "\u2696": "[scale]", "\U0001f6e1": "[shield]",
    }
    for emoji, repl in _EMOJI_MAP.items():
        text = text.replace(emoji, repl)
    # Drop anything still outside latin-1
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _fmtc(v: Optional[float], symbol: str = "$") -> str:
    if v is None:
        return "N/A"
    sign = "-" if v < 0 else ""
    return f"{sign}{symbol}{abs(v):,.0f}"


def _fmtp(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.{decimals}f}%"


def _fmtf(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "N/A"
    return f"{v:,.{decimals}f}"


# ─────────────────────────────────────────────────────────────────────────────
# Financial-health builder (mirrors page logic, accepts plain dict)
# ─────────────────────────────────────────────────────────────────────────────

def _build_fh(mode: str, sp: dict) -> dict:
    """Reconstruct financial health dict from scenario_params sliders."""
    fh: dict = {}
    if mode == "personal":
        fh["monthly_income"]        = float(sp.get("monthly_income",    5_500.0))
        fh["monthly_expenses"]      = float(sp.get("monthly_expenses",  4_500.0))
        fh["net_cash"]              = float(sp.get("savings",          13_000.0))
        fh["debt_rate"]             = float(sp.get("debt_rate",             0.07))
        fh["debt_balance"]          = float(sp.get("debt_balance",     15_000.0))
        fh["portfolio_value"]       = float(sp.get("portfolio_value",  25_000.0))
        fh["expected_return"]       = float(sp.get("expected_return",       0.08))
        inc  = fh["monthly_income"]
        exp  = fh["monthly_expenses"]
        fh["savings_rate"]          = max(0.0, (inc - exp) / inc) if inc > 0 else 0.0
        fh["emergency_fund_months"] = fh["net_cash"] / exp if exp > 0 else 0.0
    else:
        fh["monthly_revenue"]  = float(sp.get("monthly_revenue",  47_000.0))
        fh["monthly_expenses"] = float(sp.get("monthly_expenses", 40_000.0))
        fh["cash_balance"]     = float(sp.get("cash_balance",     88_000.0))
        fh["debt_rate"]        = float(sp.get("debt_rate",             0.07))
        fh["debt_balance"]     = float(sp.get("debt_balance",     50_000.0))
        fh["marketing_budget"] = float(sp.get("marketing_budget",  5_000.0))
        fh["gross_margin_pct"] = 0.15
        fh["net_margin_pct"]   = 0.05
        fh["burn_rate"]        = 0.0
        fh["revenue_growth"]   = float(sp.get("growth_rate", 0.0)) / 12.0
        net_mo = fh["monthly_revenue"] - fh["monthly_expenses"]
        fh["runway_months"] = (
            fh["cash_balance"] / abs(net_mo) if net_mo < 0 else None
        )
    return fh


def _build_assumptions(mode: str, sp: dict, ms: dict, raw_macro: dict) -> dict:
    """Build a flat dict of every parameter and its data source."""
    data_source = "Fallback (demo)" if raw_macro.get("is_fallback", True) else "FRED API"
    out: dict = {
        "data_source":       data_source,
        "fed_rate_pct":      ms.get("current_fed_rate"),
        "inflation_pct":     ms.get("current_inflation"),
        "unemployment_pct":  ms.get("current_unemployment"),
        "yield_spread":      ms.get("yield_spread"),
        "sp500_ytd_return":  ms.get("sp500_ytd_return"),
    }
    if mode == "personal":
        out.update({
            "monthly_income":    sp.get("monthly_income",    5_500.0),
            "monthly_expenses":  sp.get("monthly_expenses",  4_500.0),
            "savings":           sp.get("savings",          13_000.0),
            "debt_rate_pct":     float(sp.get("debt_rate",       0.07)) * 100,
            "debt_balance":      sp.get("debt_balance",     15_000.0),
            "portfolio_value":   sp.get("portfolio_value",  25_000.0),
            "expected_return_pct": float(sp.get("expected_return", 0.08)) * 100,
        })
    else:
        out.update({
            "monthly_revenue":   sp.get("monthly_revenue",  47_000.0),
            "monthly_expenses":  sp.get("monthly_expenses", 40_000.0),
            "cash_balance":      sp.get("cash_balance",     88_000.0),
            "debt_rate_pct":     float(sp.get("debt_rate",       0.07)) * 100,
            "debt_balance":      sp.get("debt_balance",     50_000.0),
            "marketing_budget":  sp.get("marketing_budget",  5_000.0),
            "growth_rate_pct":   sp.get("growth_rate",           0.0),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# build_report
# ─────────────────────────────────────────────────────────────────────────────

def build_report(session_state) -> dict:
    """
    Compile everything into a structured report dict.

    Parameters
    ----------
    session_state : dict-like (Streamlit session_state or plain dict)

    Returns
    -------
    dict with keys:
        mode, financial_health_summary, market_environment, regime,
        top_recommendation, ranked_allocations, allocation_explanation,
        scenario_results, stress_test_results, resilience_score,
        assumptions_used, generated_date
    """
    from src.analysis.allocation_engine import recommend, explain_recommendation
    from src.analysis.stress_test import run_all_stress_tests, resilience_score

    mode      = session_state.get("mode", "personal")
    macro     = dict(session_state.get("macro", {}) or {})
    scenarios = dict(session_state.get("scenarios", {}) or {})
    sp        = dict(session_state.get("scenario_params", {}) or {})
    cached_alloc = dict(session_state.get("allocation", {}) or {})

    # ── Financial health ───────────────────────────────────────────────────────
    fh = _build_fh(mode, sp)

    # ── Macro summary ──────────────────────────────────────────────────────────
    ms: dict = {
        "current_fed_rate":     float(macro.get("current_fed_rate")     or 5.0),
        "current_inflation":    float(macro.get("current_inflation")    or 3.2),
        "current_unemployment": float(macro.get("current_unemployment") or 4.0),
        "yield_spread":         float(macro.get("yield_spread")         or 0.5),
        "sp500_ytd_return":     macro.get("sp500_ytd_return"),
        "is_fallback":          bool(macro.get("is_fallback", True)),
    }
    regime = str(macro.get("regime", "cautious") or "cautious").lower()

    # ── Allocation ─────────────────────────────────────────────────────────────
    ctx = {
        "financial_health": fh,
        "macro_summary":    ms,
        "regime":           regime,
        "risk_profile":     "moderate",
        "scenarios":        scenarios,
        "mode":             mode,
    }

    if cached_alloc.get("ranked"):
        ranked  = cached_alloc["ranked"]
        top_rec = cached_alloc["top_recommendation"]
    else:
        result  = recommend(ctx, mode)
        ranked  = result["ranked"]
        top_rec = result["top_recommendation"]

    explanation = explain_recommendation(ranked, ctx)
    top_option  = next((r for r in ranked if r["option"] == top_rec), ranked[0] if ranked else {})

    # ── Scenario key numbers ───────────────────────────────────────────────────
    scenario_results: dict = {}
    for key in ("base", "upside", "downside"):
        sc = scenarios.get(key, {})
        if sc:
            scenario_results[key] = {
                "median_outcome":          sc.get("median_outcome"),
                "p5_outcome":              sc.get("p5_outcome"),
                "p95_outcome":             sc.get("p95_outcome"),
                "probability_of_negative": sc.get("probability_of_negative"),
                "months_until_negative":   sc.get("months_until_negative"),
            }

    # ── Stress tests ───────────────────────────────────────────────────────────
    portfolio_val = float(sp.get("portfolio_value", 25_000.0)) if mode == "personal" else 0.0
    all_stress    = run_all_stress_tests(fh, portfolio_val, mode)
    resil         = resilience_score(all_stress)

    # Strip heavy cash-path arrays from the report dict
    stress_slim = [
        {k: v for k, v in r.items() if k not in ("cash_path_base", "cash_path_stressed")}
        for r in all_stress
    ]

    return {
        "mode":                     mode,
        "financial_health_summary": fh,
        "market_environment":       ms,
        "regime":                   regime,
        "top_recommendation": {
            "option":           top_rec,
            "label":            top_option.get("label",            top_rec),
            "score":            top_option.get("score",            0),
            "reasoning":        top_option.get("reasoning",        ""),
            "expected_benefit": top_option.get("expected_benefit", ""),
            "risk_level":       top_option.get("risk_level",       ""),
        },
        "ranked_allocations":   ranked,
        "allocation_explanation": explanation,
        "scenario_results":     scenario_results,
        "stress_test_results":  stress_slim,
        "resilience_score":     resil,
        "assumptions_used":     _build_assumptions(mode, sp, ms, macro),
        "generated_date":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# report_to_markdown
# ─────────────────────────────────────────────────────────────────────────────

def report_to_markdown(report: dict) -> str:
    """Render the report as clean, readable GitHub-flavored Markdown."""
    mode  = report["mode"].capitalize()
    date  = report["generated_date"]
    fh    = report["financial_health_summary"]
    ms    = report["market_environment"]
    reg   = report["regime"].replace("_", " ").title()
    top   = report["top_recommendation"]
    sc    = report["scenario_results"]
    st_r  = report["stress_test_results"]
    resil = report["resilience_score"]
    assm  = report["assumptions_used"]
    rnkd  = report["ranked_allocations"]
    expln = report.get("allocation_explanation", "")

    lines: list[str] = []
    a = lines.append

    # ── Title ──────────────────────────────────────────────────────────────────
    a("# MoneyMap AI — Your Allocation Report")
    a("")
    a(f"**Mode:** {mode}  |  **Regime:** {reg}  |  **Generated:** {date}")
    a("")
    a("---")
    a("")

    # ── Executive Summary ──────────────────────────────────────────────────────
    a("## Executive Summary")
    a("")
    a(f"**Top Recommendation: {top['label']}** (Score: {top['score']:.0f}/100)")
    a("")
    a(f"> {top['reasoning']}")
    a("")
    a(f"**Expected benefit:** {top['expected_benefit']}")
    a(f"**Risk level:** {top['risk_level'].title()}")
    a("")
    a("---")
    a("")

    # ── Market Environment ─────────────────────────────────────────────────────
    a("## Market Environment")
    a("")
    data_src = assm.get("data_source", "Fallback (demo)")
    a(f"*Data source: {data_src}*")
    a("")
    a("| Indicator | Value |")
    a("|-----------|-------|")
    a(f"| Fed Funds Rate | {_fmtf(ms.get('current_fed_rate'))}% |")
    a(f"| CPI Inflation | {_fmtf(ms.get('current_inflation'))}% |")
    a(f"| Unemployment | {_fmtf(ms.get('current_unemployment'))}% |")
    a(f"| Yield Spread (10Y-2Y) | {ms.get('yield_spread', 'N/A'):+.2f}% |"
      if isinstance(ms.get("yield_spread"), (int, float)) else
      f"| Yield Spread (10Y-2Y) | N/A |")
    sp500 = ms.get("sp500_ytd_return")
    a(f"| S&P 500 YTD | {_fmtf(sp500)}% |" if sp500 is not None else "| S&P 500 YTD | N/A |")
    a(f"| Macro Regime | **{reg}** |")
    a("")
    a("---")
    a("")

    # ── Financial Health ───────────────────────────────────────────────────────
    a("## Financial Health")
    a("")
    a("| Metric | Value |")
    a("|--------|-------|")
    if report["mode"] == "personal":
        a(f"| Monthly Income | {_fmtc(fh.get('monthly_income'))} |")
        a(f"| Monthly Expenses | {_fmtc(fh.get('monthly_expenses'))} |")
        net = fh.get("monthly_income", 0) - fh.get("monthly_expenses", 0)
        a(f"| Monthly Net | {_fmtc(net)} |")
        a(f"| Savings Rate | {_fmtp(fh.get('savings_rate'))} |")
        a(f"| Emergency Fund | {_fmtf(fh.get('emergency_fund_months'))} months |")
        a(f"| Net Savings | {_fmtc(fh.get('net_cash'))} |")
        a(f"| Debt Balance | {_fmtc(fh.get('debt_balance'))} @ {_fmtp(fh.get('debt_rate'))} APR |")
        a(f"| Portfolio Value | {_fmtc(fh.get('portfolio_value'))} |")
    else:
        a(f"| Monthly Revenue | {_fmtc(fh.get('monthly_revenue'))} |")
        a(f"| Monthly Expenses | {_fmtc(fh.get('monthly_expenses'))} |")
        net = fh.get("monthly_revenue", 0) - fh.get("monthly_expenses", 0)
        a(f"| Monthly Net | {_fmtc(net)} |")
        a(f"| Cash Balance | {_fmtc(fh.get('cash_balance'))} |")
        rwy = fh.get("runway_months")
        a(f"| Cash Runway | {_fmtf(rwy)} months |" if rwy else "| Cash Runway | Profitable |")
        a(f"| Debt Balance | {_fmtc(fh.get('debt_balance'))} @ {_fmtp(fh.get('debt_rate'))} APR |")
        a(f"| Marketing Budget | {_fmtc(fh.get('marketing_budget'))} /mo |")
    a("")
    a("---")
    a("")

    # ── Scenario Projections ───────────────────────────────────────────────────
    a("## 12-Month Scenario Projections")
    a("")
    if sc:
        a("| Scenario | Median Outcome | Bear (P5) | Bull (P95) | P(Negative) |")
        a("|----------|---------------|-----------|------------|-------------|")
        for key, label in (("base", "Base Case"), ("upside", "Upside"), ("downside", "Downside")):
            s = sc.get(key)
            if s:
                neg_pct = _fmtp(s.get("probability_of_negative"))
                a(f"| {label} | {_fmtc(s.get('median_outcome'))} | "
                  f"{_fmtc(s.get('p5_outcome'))} | "
                  f"{_fmtc(s.get('p95_outcome'))} | "
                  f"{neg_pct} |")
    else:
        a("*Run the Scenario Lab (Step 4) to generate projections.*")
    a("")
    a("---")
    a("")

    # ── Stress Test Results ────────────────────────────────────────────────────
    a("## Stress Test Results")
    a("")
    a(f"**Resilience Score: {resil['score']}/100 — {resil['label']}**  "
      f"({resil['survived']}/{resil['total']} scenarios survived)")
    a("")
    if st_r:
        a("| Scenario | Severity | Portfolio Impact | New Monthly Net | Recovery |")
        a("|----------|----------|-----------------|-----------------|----------|")
        for r in st_r:
            sev   = r.get("severity_score", 0)
            sev_l = "Severe" if sev >= 50 else ("Moderate" if sev >= 25 else "Mild")
            p_imp = _fmtp(r.get("portfolio_impact_pct"))
            n_net = _fmtc(r.get("new_monthly_net"))
            recov = r.get("recovery_months")
            r_str = f"{recov} mo" if recov else "N/A"
            a(f"| {r.get('label', r.get('scenario_name', ''))} | "
              f"{sev_l} ({sev:.0f}) | {p_imp} | {n_net} | {r_str} |")
    a("")
    a("---")
    a("")

    # ── Full Allocation Rankings ───────────────────────────────────────────────
    a("## Allocation Rankings")
    a("")
    a("| Rank | Option | Score | Risk | Expected Benefit |")
    a("|------|--------|-------|------|-----------------|")
    for i, r in enumerate(rnkd, 1):
        a(f"| #{i} | {r.get('label', r.get('option', ''))} | "
          f"{r.get('score', 0):.0f}/100 | "
          f"{r.get('risk_level', '').title()} | "
          f"{r.get('expected_benefit', '')} |")
    a("")

    # ── Allocation Reasoning ───────────────────────────────────────────────────
    if expln:
        a("### Why This Recommendation?")
        a("")
        a(expln)
        a("")

    a("---")
    a("")

    # ── Assumptions ───────────────────────────────────────────────────────────
    a("## Assumptions Used")
    a("")
    a("| Parameter | Value |")
    a("|-----------|-------|")
    _LABELS = {
        "data_source":           "Data Source",
        "fed_rate_pct":          "Fed Funds Rate (%)",
        "inflation_pct":         "CPI Inflation (%)",
        "unemployment_pct":      "Unemployment (%)",
        "yield_spread":          "Yield Spread (pp)",
        "sp500_ytd_return":      "S&P 500 YTD (%)",
        "monthly_income":        "Monthly Income",
        "monthly_expenses":      "Monthly Expenses",
        "savings":               "Savings",
        "debt_rate_pct":         "Debt APR (%)",
        "debt_balance":          "Debt Balance",
        "portfolio_value":       "Portfolio Value",
        "expected_return_pct":   "Expected Return (%)",
        "monthly_revenue":       "Monthly Revenue",
        "cash_balance":          "Cash Balance",
        "marketing_budget":      "Marketing Budget /mo",
        "growth_rate_pct":       "Monthly Growth Rate (%)",
    }
    for key, val in assm.items():
        lbl = _LABELS.get(key, key.replace("_", " ").title())
        if isinstance(val, float) and key not in ("data_source",):
            val_str = f"{val:,.2f}"
        else:
            val_str = str(val) if val is not None else "N/A"
        a(f"| {lbl} | {val_str} |")
    a("")
    a("---")
    a("")

    # ── Disclaimer ────────────────────────────────────────────────────────────
    a("## Disclaimer")
    a("")
    a("> **This report is for educational and informational purposes only.**  "
      "MoneyMap AI does not provide investment, tax, or legal advice. All projections "
      "are based on user-supplied inputs and historical market data; past performance "
      "is not indicative of future results. Monte Carlo simulations involve inherent "
      "uncertainty — actual outcomes may differ materially. Consult a licensed "
      "financial advisor before making any financial decisions.")
    a("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# report_to_pdf_bytes
# ─────────────────────────────────────────────────────────────────────────────

def report_to_pdf_bytes(report: dict) -> bytes:
    """
    Generate a clean PDF from the report dict using fpdf2.

    Returns raw PDF bytes suitable for st.download_button.
    """
    from fpdf import FPDF

    # ── Colour palette (R, G, B) ───────────────────────────────────────────────
    BLACK  = (15,  17,  23)
    DARK   = (22,  27,  34)
    BORDER = (48,  54,  61)
    TEXT   = (230, 237, 243)
    MUTED  = (139, 148, 158)
    BLUE   = (31,  111, 235)
    GREEN  = (63,  185,  80)
    RED    = (248,  81,  73)
    GOLD   = (227, 179,  65)
    WHITE  = (255, 255, 255)

    # ── Setup ──────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()

    W = pdf.w - pdf.l_margin - pdf.r_margin   # usable width

    def h1(text: str):
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(*TEXT)
        pdf.multi_cell(W, 9, _safe(text), ln=True)
        pdf.ln(1)

    def h2(text: str):
        pdf.ln(4)
        pdf.set_fill_color(*DARK)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*BLUE)
        pdf.multi_cell(W, 8, _safe(text), fill=True, ln=True)
        pdf.ln(1)

    def h3(text: str):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*GOLD)
        pdf.multi_cell(W, 7, _safe(text), ln=True)

    def body(text: str, color=None):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*(color or MUTED))
        pdf.multi_cell(W, 5.5, _safe(text), ln=True)

    def kv(label: str, value: str, label_w: float = 70):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(label_w, 6, _safe(label), ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*TEXT)
        pdf.multi_cell(W - label_w, 6, _safe(str(value)), ln=True)

    def rule():
        pdf.ln(2)
        pdf.set_draw_color(*BORDER)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + W, pdf.get_y())
        pdf.ln(3)

    def table_header(*cols_widths):
        pdf.set_fill_color(*DARK)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*BLUE)
        for label, w in cols_widths:
            pdf.cell(w, 6, _safe(label), border=0, fill=True, ln=False)
        pdf.ln()

    def table_row(*cells_widths, alt: bool = False):
        if alt:
            pdf.set_fill_color(28, 33, 40)
        else:
            pdf.set_fill_color(*BLACK)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*TEXT)
        for text, w in cells_widths:
            pdf.cell(w, 5.5, _safe(str(text)), border=0, fill=True, ln=False)
        pdf.ln()

    # ── Cover ──────────────────────────────────────────────────────────────────
    pdf.set_fill_color(*BLACK)
    pdf.rect(0, 0, pdf.w, pdf.h, "F")

    pdf.ln(6)
    h1("MoneyMap AI")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*GOLD)
    pdf.multi_cell(W, 7, "Your Allocation Report", ln=True)
    pdf.ln(1)

    mode  = report["mode"].capitalize()
    date  = report["generated_date"]
    reg   = report["regime"].replace("_", " ").title()
    body(f"Mode: {mode}   |   Regime: {reg}   |   Generated: {date}", color=MUTED)
    rule()

    # ── Executive Summary ──────────────────────────────────────────────────────
    h2("1. Executive Summary")
    top = report["top_recommendation"]
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*GOLD)
    pdf.multi_cell(W, 7, _safe(f"Top Recommendation: {top['label']}"), ln=True)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*TEXT)
    pdf.multi_cell(W, 6, _safe(f"Score: {top['score']:.0f}/100  |  Risk: {top['risk_level'].title()}"), ln=True)
    pdf.ln(1)
    body(top["reasoning"])
    pdf.ln(1)
    kv("Expected benefit:", top["expected_benefit"])
    rule()

    # ── Market Environment ─────────────────────────────────────────────────────
    h2("2. Market Environment")
    ms = report["market_environment"]
    assm = report["assumptions_used"]
    pdf.ln(1)
    body(f"Data source: {assm.get('data_source', 'N/A')}")
    pdf.ln(2)
    sp500 = ms.get("sp500_ytd_return")
    ys    = ms.get("yield_spread")
    table_header(
        ("Indicator", 80), ("Value", W - 80)
    )
    rows_env = [
        ("Fed Funds Rate",    f"{_fmtf(ms.get('current_fed_rate'))}%"),
        ("CPI Inflation",     f"{_fmtf(ms.get('current_inflation'))}%"),
        ("Unemployment",      f"{_fmtf(ms.get('current_unemployment'))}%"),
        ("Yield Spread",      f"{ys:+.2f}%" if isinstance(ys, (int, float)) else "N/A"),
        ("S&P 500 YTD",       f"{_fmtf(sp500)}%" if sp500 is not None else "N/A"),
        ("Macro Regime",      reg),
    ]
    for i, (lbl, val) in enumerate(rows_env):
        table_row((lbl, 80), (val, W - 80), alt=bool(i % 2))
    rule()

    # ── Financial Health ───────────────────────────────────────────────────────
    h2("3. Financial Health")
    fh = report["financial_health_summary"]
    pdf.ln(2)
    table_header(("Metric", 90), ("Value", W - 90))
    if report["mode"] == "personal":
        net = fh.get("monthly_income", 0) - fh.get("monthly_expenses", 0)
        rows_fh = [
            ("Monthly Income",    _fmtc(fh.get("monthly_income"))),
            ("Monthly Expenses",  _fmtc(fh.get("monthly_expenses"))),
            ("Monthly Net",       _fmtc(net)),
            ("Savings Rate",      _fmtp(fh.get("savings_rate"))),
            ("Emergency Fund",    f"{_fmtf(fh.get('emergency_fund_months'))} months"),
            ("Net Savings",       _fmtc(fh.get("net_cash"))),
            ("Debt Balance",      f"{_fmtc(fh.get('debt_balance'))} @ {_fmtp(fh.get('debt_rate'))} APR"),
            ("Portfolio Value",   _fmtc(fh.get("portfolio_value"))),
        ]
    else:
        net = fh.get("monthly_revenue", 0) - fh.get("monthly_expenses", 0)
        rwy = fh.get("runway_months")
        rows_fh = [
            ("Monthly Revenue",  _fmtc(fh.get("monthly_revenue"))),
            ("Monthly Expenses", _fmtc(fh.get("monthly_expenses"))),
            ("Monthly Net",      _fmtc(net)),
            ("Cash Balance",     _fmtc(fh.get("cash_balance"))),
            ("Cash Runway",      f"{_fmtf(rwy)} months" if rwy else "Profitable"),
            ("Debt Balance",     f"{_fmtc(fh.get('debt_balance'))} @ {_fmtp(fh.get('debt_rate'))} APR"),
            ("Marketing Budget", f"{_fmtc(fh.get('marketing_budget'))}/mo"),
        ]
    for i, (lbl, val) in enumerate(rows_fh):
        table_row((lbl, 90), (val, W - 90), alt=bool(i % 2))
    rule()

    # ── Scenario Projections ───────────────────────────────────────────────────
    h2("4. 12-Month Scenario Projections")
    sc = report["scenario_results"]
    pdf.ln(2)
    if sc:
        cw = [45, 38, 38, 38, W - 159]
        table_header(
            ("Scenario", cw[0]), ("Median", cw[1]),
            ("Bear P5", cw[2]), ("Bull P95", cw[3]), ("P(Neg)", cw[4])
        )
        sc_rows = [("Base Case", "base"), ("Upside", "upside"), ("Downside", "downside")]
        for i, (lbl, key) in enumerate(sc_rows):
            s = sc.get(key)
            if s:
                table_row(
                    (lbl, cw[0]),
                    (_fmtc(s.get("median_outcome")), cw[1]),
                    (_fmtc(s.get("p5_outcome")), cw[2]),
                    (_fmtc(s.get("p95_outcome")), cw[3]),
                    (_fmtp(s.get("probability_of_negative")), cw[4]),
                    alt=bool(i % 2),
                )
    else:
        body("Run the Scenario Lab (Step 4) to generate projections.")
    rule()

    # ── Stress Test Results ────────────────────────────────────────────────────
    h2("5. Stress Test Results")
    resil   = report["resilience_score"]
    str_r   = report["stress_test_results"]
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*GREEN if resil["score"] >= 70 else (RED if resil["score"] < 40 else GOLD))
    pdf.multi_cell(W, 7,
        _safe(f"Resilience Score: {resil['score']}/100 — {resil['label']} "
              f"({resil['survived']}/{resil['total']} scenarios survived)"),
        ln=True)
    pdf.ln(2)
    if str_r:
        cw2 = [52, 26, 34, 34, W - 146]
        table_header(
            ("Scenario", cw2[0]), ("Severity", cw2[1]),
            ("Port. Impact", cw2[2]), ("New Net/mo", cw2[3]), ("Recovery", cw2[4])
        )
        for i, r in enumerate(str_r):
            sev   = r.get("severity_score", 0)
            sev_l = "Severe" if sev >= 50 else ("Moderate" if sev >= 25 else "Mild")
            recov = r.get("recovery_months")
            table_row(
                (r.get("label", r.get("scenario_name", "")), cw2[0]),
                (f"{sev_l}", cw2[1]),
                (_fmtp(r.get("portfolio_impact_pct")), cw2[2]),
                (_fmtc(r.get("new_monthly_net")), cw2[3]),
                (f"{recov} mo" if recov else "N/A", cw2[4]),
                alt=bool(i % 2),
            )
    rule()

    # ── Full Allocation Rankings ───────────────────────────────────────────────
    h2("6. Allocation Rankings")
    rnkd = report["ranked_allocations"]
    pdf.ln(2)
    cw3 = [10, 52, 22, 22, W - 106]
    table_header(
        ("#", cw3[0]), ("Option", cw3[1]),
        ("Score", cw3[2]), ("Risk", cw3[3]), ("Expected Benefit", cw3[4])
    )
    for i, r in enumerate(rnkd, 1):
        table_row(
            (f"#{i}", cw3[0]),
            (r.get("label", r.get("option", "")), cw3[1]),
            (f"{r.get('score', 0):.0f}/100", cw3[2]),
            (r.get("risk_level", "").title(), cw3[3]),
            (r.get("expected_benefit", ""), cw3[4]),
            alt=bool(i % 2),
        )
    rule()

    # ── Why This Recommendation ────────────────────────────────────────────────
    expln = report.get("allocation_explanation", "")
    if expln:
        h2("7. Why This Recommendation?")
        # Strip markdown bold/italic markers for cleaner PDF text
        plain = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", expln)
        plain = re.sub(r"#+\s+", "", plain)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        for para in plain.split("\n\n"):
            pdf.ln(1)
            body(para.strip(), color=TEXT)
        rule()

    # ── Assumptions ───────────────────────────────────────────────────────────
    h2("8. Assumptions Used")
    assm = report["assumptions_used"]
    pdf.ln(2)
    _LABELS = {
        "data_source":          "Data Source",
        "fed_rate_pct":         "Fed Funds Rate (%)",
        "inflation_pct":        "CPI Inflation (%)",
        "unemployment_pct":     "Unemployment (%)",
        "yield_spread":         "Yield Spread (pp)",
        "sp500_ytd_return":     "S&P 500 YTD (%)",
        "monthly_income":       "Monthly Income",
        "monthly_expenses":     "Monthly Expenses",
        "savings":              "Savings",
        "debt_rate_pct":        "Debt APR (%)",
        "debt_balance":         "Debt Balance",
        "portfolio_value":      "Portfolio Value",
        "expected_return_pct":  "Expected Return (%)",
        "monthly_revenue":      "Monthly Revenue",
        "cash_balance":         "Cash Balance",
        "marketing_budget":     "Marketing Budget /mo",
        "growth_rate_pct":      "Monthly Growth Rate (%)",
    }
    cwa = [90, W - 90]
    table_header(("Parameter", cwa[0]), ("Value", cwa[1]))
    for i, (key, val) in enumerate(assm.items()):
        lbl = _LABELS.get(key, key.replace("_", " ").title())
        val_str = f"{val:,.2f}" if isinstance(val, float) else (str(val) if val is not None else "N/A")
        table_row((lbl, cwa[0]), (val_str, cwa[1]), alt=bool(i % 2))
    rule()

    # ── Disclaimer ────────────────────────────────────────────────────────────
    h2("Disclaimer")
    pdf.ln(1)
    body(
        "This report is for educational and informational purposes only. "
        "MoneyMap AI does not provide investment, tax, or legal advice. "
        "All projections are based on user-supplied inputs and historical market data; "
        "past performance is not indicative of future results. Monte Carlo simulations "
        "involve inherent uncertainty -- actual outcomes may differ materially. "
        "Consult a licensed financial advisor before making any financial decisions.",
        color=MUTED,
    )

    return bytes(pdf.output())

"""
Reusable Streamlit guards: friendly redirects when session_state is incomplete.
"""
from __future__ import annotations

import streamlit as st


def require_mode(home_path: str = "Home.py") -> None:
    """Stop with a CTA if the user has not chosen personal vs business on Home."""
    if st.session_state.get("mode") not in ("personal", "business"):
        st.markdown(
            "<h3 style='color:#e6edf3;margin-bottom:0.5rem'>Choose how we should help</h3>"
            "<p style='color:#8b949e'>Select <b>I'm a Person</b> or <b>I'm a Business</b> on the "
            "home page so MoneyMap can tailor the workflow.</p>",
            unsafe_allow_html=True,
        )
        if st.button("Back to home", type="primary", width='stretch'):
            st.switch_page(home_path)
        st.stop()


def require_raw_data(
    connect_path: str = "pages/1_Connect_Data.py",
    *,
    body: str = "Upload a CSV or XLSX on **Connect Data** (or load a sample) so we can analyse your finances.",
) -> None:
    """Stop with a CTA if ``raw_df`` is missing from session_state."""
    if st.session_state.get("raw_df") is None:
        st.warning(body, icon="📂")
        if st.button("Go to Connect Data", type="primary", width='stretch'):
            st.switch_page(connect_path)
        st.stop()


def require_scenarios(
    scenario_path: str = "pages/4_Scenario_Lab.py",
    *,
    body: str = "Run **Scenario Lab** once so projections and allocation use the same assumptions.",
) -> None:
    """Stop with a CTA if scenario outputs are not in session_state."""
    if not st.session_state.get("scenarios"):
        st.info(body, icon="🔬")
        if st.button("Open Scenario Lab", type="primary", width='stretch'):
            st.switch_page(scenario_path)
        st.stop()


def require_allocation(
    allocation_path: str = "pages/5_Allocation_Engine.py",
    *,
    body: str = "Open **Allocation Engine** once so the report can include ranked recommendations.",
) -> None:
    """Stop with a CTA if allocation results are not in session_state."""
    if not st.session_state.get("allocation"):
        st.info(body, icon="⚡")
        if st.button("Open Allocation Engine", type="primary", width='stretch'):
            st.switch_page(allocation_path)
        st.stop()

"""
MoneyMap AI — Streamlit home page and multi-page app entry point.

Renders the landing experience and navigation into numbered workflow pages.
"""
import streamlit as st

st.set_page_config(
    page_title="MoneyMap AI — Next Dollar Allocation Advisor",
    page_icon="🧭",
    layout="centered",
    initial_sidebar_state="expanded",
)

# Additional CSS on top of .streamlit/config.toml base theme
st.markdown(
    """
    <style>
    .hero-headline {
        font-size: 3rem;
        font-weight: 800;
        color: #e6edf3;
        line-height: 1.15;
        margin-bottom: 0.5rem;
    }
    .hero-sub {
        font-size: 1.15rem;
        color: #8b949e;
        margin-bottom: 2.5rem;
    }
    .stButton > button {
        width: 100%;
        padding: 1rem 1.5rem;
        font-size: 1.05rem;
        font-weight: 600;
        border-radius: 10px;
        border: 1px solid #30363d;
        background-color: #161b22;
        color: #e6edf3;
        transition: background 0.2s, border-color 0.2s;
    }
    .stButton > button:hover {
        background-color: #1f6feb;
        border-color: #1f6feb;
        color: #ffffff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown(
    '<p class="hero-headline">Where Should Your Next Dollar Go?</p>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="hero-sub">'
    "MoneyMap AI analyses your income, spending, and the macro environment "
    "to give you a clear, data-driven answer — no guesswork, no generic advice."
    "</p>",
    unsafe_allow_html=True,
)

st.divider()

st.markdown("#### Who are you optimising for?")
col1, col2 = st.columns(2, gap="large")

with col1:
    if st.button("I'm a Person", width='stretch'):
        st.session_state["mode"] = "personal"
        st.switch_page("pages/1_Connect_Data.py")

with col2:
    if st.button("I'm a Business", width='stretch'):
        st.session_state["mode"] = "business"
        st.switch_page("pages/1_Connect_Data.py")

st.markdown(
    "<br><p style='color:#8b949e; font-size:0.85rem; text-align:center;'>"
    "Your data never leaves your machine. All processing happens locally.</p>",
    unsafe_allow_html=True,
)

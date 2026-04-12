"""Global CSS injection for Req-Tracker AI — dark slate navy theme."""
import streamlit as st

# ── Palette ─────────────────────────────────────────────────────────────────
BG           = "#13131f"   # page background
BG2          = "#1c1c2e"   # sidebar / card surface
BG3          = "#22223a"   # elevated surface (tables, inputs)
BORDER       = "#2e2e4a"   # subtle border
PRIMARY      = "#7b6cdb"   # accent (muted indigo)
TEXT         = "#dddaf0"   # primary text
TEXT_DIM     = "#8e8aaa"   # secondary text
TEXT_FAINT   = "#4e4a6a"   # placeholder / disabled

# Node / relation colours — harmonised with dark-slate theme
NODE_REQ     = "#5c84ad"   # steel blue
NODE_ARCH    = "#7b6cdb"   # slate indigo (= theme primary)
NODE_DESIGN  = "#4e8c68"   # sage green
NODE_VERIF   = "#9e7848"   # warm sienna
NODE_ISSUE   = "#9e5555"   # dusty rose-red

GRAPH_BG     = "#13131f"   # matches page bg


def inject_global_css() -> None:
    """Call once at the top of every page (after set_page_config)."""
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = f"""
<style>
/* ── Root & scrollbar ─────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {{
    background-color: {BG} !important;
    color: {TEXT} !important;
}}
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {BG2}; }}
::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 3px; }}

/* ── Sidebar ─────────────────────────────────────────────── */
[data-testid="stSidebar"] > div:first-child {{
    background-color: {BG2} !important;
    border-right: 1px solid {BORDER} !important;
}}
[data-testid="stSidebar"] * {{ color: {TEXT} !important; }}
[data-testid="stSidebar"] hr {{ border-color: {BORDER} !important; }}

/* ── Main content padding ────────────────────────────────── */
.main .block-container {{
    padding-top: 1.8rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}}

/* ── Headings ────────────────────────────────────────────── */
h1, h2, h3, h4 {{ color: {TEXT} !important; letter-spacing: -0.3px; }}
h1 {{ font-size: 1.7rem !important; }}
h2 {{ font-size: 1.3rem !important; }}
h3 {{ font-size: 1.1rem !important; }}

/* ── Paragraphs & captions ───────────────────────────────── */
p, label, .stCaption, [data-testid="stCaptionContainer"] {{
    color: {TEXT_DIM} !important;
}}

/* ── Metric widgets ──────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: {BG2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 12px 16px;
}}
[data-testid="stMetricLabel"] {{ color: {TEXT_DIM} !important; font-size: 12px !important; }}
[data-testid="stMetricValue"] {{ color: {TEXT}    !important; font-size: 1.4rem !important; }}
[data-testid="stMetricDelta"] {{ font-size: 11px  !important; }}

/* ── Buttons ─────────────────────────────────────────────── */
button[kind="primary"], [data-testid="baseButton-primary"] {{
    background: {PRIMARY} !important;
    border: none !important;
    border-radius: 6px !important;
    color: #fff !important;
    font-weight: 600 !important;
}}
button[kind="secondary"], [data-testid="baseButton-secondary"] {{
    background: {BG3} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT} !important;
    border-radius: 6px !important;
}}
button:hover {{ opacity: 0.88; }}

/* ── Page link buttons ───────────────────────────────────── */
[data-testid="stPageLink"] a {{
    background: {BG3} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 6px !important;
    color: {TEXT} !important;
    text-decoration: none !important;
    padding: 6px 10px !important;
    font-size: 12px !important;
    display: block;
    text-align: center;
    margin-top: 4px;
    transition: background 0.15s;
}}
[data-testid="stPageLink"] a:hover {{
    background: {PRIMARY}33 !important;
    border-color: {PRIMARY}88 !important;
    color: #fff !important;
}}

/* ── Info / Warning / Error / Success boxes ──────────────── */
[data-testid="stAlert"] {{
    border-radius: 8px !important;
    border-width: 1px !important;
}}
div[data-baseweb="notification"] {{
    background-color: {BG2} !important;
}}

/* ── Dataframe / table ───────────────────────────────────── */
[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    overflow: hidden;
}}
[data-testid="stDataFrame"] * {{
    font-size: 12px !important;
}}

/* ── Divider ─────────────────────────────────────────────── */
hr {{ border-color: {BORDER} !important; margin: 0.8rem 0 !important; }}

/* ── Expander ────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    background: {BG2} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
}}
[data-testid="stExpander"] summary {{
    color: {TEXT} !important;
    font-size: 13px !important;
}}

/* ── Selectbox / multiselect / text_input ────────────────── */
[data-baseweb="select"] > div,
[data-baseweb="input"]  > div,
[data-baseweb="textarea"] {{
    background: {BG3} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
    border-radius: 6px !important;
}}
[data-baseweb="option"] {{
    background: {BG2} !important;
    color: {TEXT} !important;
}}
[data-baseweb="option"]:hover {{ background: {BG3} !important; }}

/* ── Checkbox & toggle ───────────────────────────────────── */
[data-testid="stCheckbox"] span,
[data-testid="stToggle"]   span {{
    color: {TEXT} !important;
    font-size: 12px !important;
}}

/* ── Number input ────────────────────────────────────────── */
[data-testid="stNumberInput"] input {{
    background: {BG3} !important;
    color: {TEXT} !important;
    border-color: {BORDER} !important;
}}

/* ── Slider ──────────────────────────────────────────────── */
[data-testid="stSlider"] [role="slider"] {{
    background: {PRIMARY} !important;
}}

/* ── Columns gap ─────────────────────────────────────────── */
[data-testid="column"] {{ padding: 0 6px !important; }}

/* ── pyvis iframe background ─────────────────────────────── */
iframe {{ border: none !important; border-radius: 8px; }}

/* ── Spinner ─────────────────────────────────────────────── */
[data-testid="stSpinner"] {{ color: {PRIMARY} !important; }}

/* ── Tab bar (multipage top nav) ──────────────────────────── */
[data-testid="stHeader"] {{
    background: {BG} !important;
    border-bottom: 1px solid {BORDER} !important;
}}
</style>
"""

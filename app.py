"""
OptionChainPro — Nifty 50 Option Chain Terminal
Institutional dark terminal UI, built on optionchain/core.py (unit-tested).
"""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from optionchain import core

st.set_page_config(
    page_title="OptionChainPro | NIFTY Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Design tokens (mirrored in .streamlit/config.toml for native widgets)
# --------------------------------------------------------------------------- #
BG = "#020617"
CARD = "#0E1223"
CARD_ALT = "#111726"
BORDER = "#243044"
FG = "#F8FAFC"
MUTED = "#8B99B0"
POS = "#22C55E"
NEG = "#EF4444"
ACCENT = "#3B82F6"
AMBER = "#F59E0B"
ITM_TINT = "rgba(59, 130, 246, 0.07)"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');

    :root {{
        --bg: {BG}; --card: {CARD}; --card-alt: {CARD_ALT}; --border: {BORDER};
        --fg: {FG}; --muted: {MUTED}; --pos: {POS}; --neg: {NEG}; --accent: {ACCENT}; --amber: {AMBER};
    }}

    .stApp {{ background: var(--bg); color: var(--fg); }}
    .stApp, .stApp p, .stApp label, .stApp li, .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stCaptionContainer"], .stApp [role="tab"] p, .stApp [data-baseweb="select"] {{
        font-family: 'IBM Plex Sans', sans-serif;
    }}
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ font-family: 'IBM Plex Sans', sans-serif; color: var(--fg); }}
    .mono, .stApp [data-testid="stDataFrame"] * {{ font-family: 'IBM Plex Mono', monospace !important; }}
    header[data-testid="stHeader"] {{ background: var(--bg); border-bottom: 1px solid var(--border); }}
    .block-container {{ padding-top: 2.75rem; max-width: 1500px; }}

    .stApp button:focus-visible, .stApp [role="tab"]:focus-visible,
    .stApp input:focus-visible, .stApp a:focus-visible {{
        outline: 2px solid var(--accent) !important; outline-offset: 2px;
    }}

    /* ---------- Ticker bar ---------- */
    .oc-ticker {{
        overflow: hidden; white-space: nowrap;
        padding: 0.55rem 0; margin-bottom: 1rem;
        background: var(--card); border: 1px solid var(--border); border-radius: 6px;
        font-family: 'IBM Plex Mono', monospace; font-size: 0.86rem;
    }}
    .oc-ticker-track {{
        display: inline-flex; align-items: center; gap: 0.9rem;
        padding-left: 100%;
        animation: oc-marquee 28s linear infinite;
    }}
    .oc-ticker .brand {{ font-weight: 700; letter-spacing: 0.06em; color: var(--accent); text-transform: uppercase; }}
    .oc-ticker .sym {{ font-weight: 700; letter-spacing: 0.03em; color: var(--fg); }}
    .oc-ticker .px {{ font-weight: 600; font-size: 1rem; }}
    .oc-ticker .sep {{ color: var(--border); }}
    .oc-tag {{
        display: inline-flex; align-items: center; gap: 0.35rem;
        padding: 0.15rem 0.55rem; border-radius: 4px; border: 1px solid var(--border);
        color: var(--muted); font-size: 0.78rem;
    }}
    .oc-tag svg {{ width: 13px; height: 13px; stroke: var(--muted); fill: none; stroke-width: 2; }}
    .oc-dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--pos); display: inline-block; flex-shrink: 0; }}
    .oc-dot.off {{ background: var(--muted); }}
    @media (prefers-reduced-motion: no-preference) {{
        .oc-dot.live {{ animation: oc-pulse 1.8s ease-in-out infinite; }}
        @keyframes oc-pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
        @keyframes oc-marquee {{
            0% {{ transform: translateX(0); }}
            100% {{ transform: translateX(-100%); }}
        }}
    }}
    @media (prefers-reduced-motion: reduce) {{
        .oc-ticker-track {{ animation: none; padding-left: 1rem; }}
    }}

    /* ---------- KPI strip ---------- */
    .oc-grid {{
        display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 0.6rem; margin-bottom: 1rem;
    }}
    .oc-card {{
        background: var(--card); border: 1px solid var(--border); border-radius: 6px;
        padding: 0.7rem 0.85rem; border-left: 3px solid var(--border);
    }}
    .oc-card.pos {{ border-left-color: var(--pos); }}
    .oc-card.neg {{ border-left-color: var(--neg); }}
    .oc-card.accent {{ border-left-color: var(--accent); }}
    .oc-card.amber {{ border-left-color: var(--amber); }}
    .oc-k-label {{
        font-size: 0.68rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase;
        color: var(--muted); display: flex; align-items: center; gap: 0.35rem;
    }}
    .oc-k-label svg {{ width: 13px; height: 13px; stroke: var(--muted); fill: none; stroke-width: 2; }}
    .oc-k-value {{
        font-family: 'IBM Plex Mono', monospace; font-size: 1.35rem; font-weight: 600;
        margin-top: 0.25rem; font-variant-numeric: tabular-nums; white-space: nowrap;
    }}
    .oc-k-value.pos {{ color: var(--pos); }} .oc-k-value.neg {{ color: var(--neg); }}
    .oc-k-sub {{ font-size: 0.74rem; color: var(--muted); margin-top: 0.15rem; font-family: 'IBM Plex Mono', monospace; }}

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] {{ background: var(--card); border-right: 1px solid var(--border); }}
    section[data-testid="stSidebar"] * {{ color: var(--fg); }}
    section[data-testid="stSidebar"] hr {{ border-color: var(--border); }}
    .oc-side-title {{
        font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; font-weight: 700;
        letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted);
        margin: 0.4rem 0 0.5rem 0; display: flex; align-items: center; gap: 0.4rem;
    }}
    .oc-side-title svg {{ width: 14px; height: 14px; stroke: var(--muted); fill: none; stroke-width: 2; }}

    div[data-baseweb="select"] > div, div[data-baseweb="input"], div[data-baseweb="base-input"] {{
        background: var(--card-alt) !important; border: 1px solid var(--border) !important;
        border-radius: 4px !important; color: var(--fg) !important;
    }}
    div[data-baseweb="input"] input {{ min-height: 44px; color: var(--fg) !important; }}
    div[data-testid="stNumberInput"] input {{ font-family: 'IBM Plex Mono', monospace; }}

    /* ---------- Tabs ---------- */
    .stTabs [role="tablist"] {{
        gap: 0; border-bottom: 1px solid var(--border); background: transparent;
        padding: 0; margin-bottom: 0.9rem;
    }}
    .stTabs [role="tab"] {{
        min-height: 44px; padding: 0 1.1rem; background: transparent; color: var(--muted);
        border-bottom: 2px solid transparent; border-radius: 0;
    }}
    .stTabs [role="tab"] p {{ font-size: 0.88rem; font-weight: 500; }}
    .stTabs [role="tab"][aria-selected="true"] {{
        color: var(--fg); border-bottom: 2px solid var(--accent); background: transparent;
    }}
    .stTabs [role="tab"][aria-selected="true"] p {{ font-weight: 600; }}
    .stTabs .react-aria-SelectionIndicator, .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

    /* ---------- Table / chart shells ---------- */
    div[data-testid="stDataFrame"] {{
        border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
    }}
    div[data-testid="stPlotlyChart"] {{
        border: 1px solid var(--border); border-radius: 6px; background: var(--card); padding: 0.4rem;
    }}
    div[data-testid="stCaptionContainer"] {{ color: var(--muted); font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; }}

    /* ---------- Levels list (S/R) ---------- */
    .oc-levels {{ display: flex; flex-direction: column; gap: 0.4rem; }}
    .oc-level {{
        display: flex; justify-content: space-between; align-items: center;
        padding: 0.45rem 0.7rem; background: var(--card-alt); border: 1px solid var(--border);
        border-radius: 4px; font-family: 'IBM Plex Mono', monospace; font-size: 0.86rem;
    }}
    .oc-level .strike {{ font-weight: 600; }}
    .oc-level .oi {{ color: var(--muted); }}
    .oc-badge {{
        font-size: 0.68rem; font-weight: 700; letter-spacing: 0.04em; padding: 0.1rem 0.45rem;
        border-radius: 3px; text-transform: uppercase;
    }}
    .oc-badge.sup {{ background: rgba(34,197,94,0.15); color: var(--pos); border: 1px solid rgba(34,197,94,0.35); }}
    .oc-badge.res {{ background: rgba(239,68,68,0.15); color: var(--neg); border: 1px solid rgba(239,68,68,0.35); }}

    .oc-footer {{
        text-align: center; color: var(--muted); font-family: 'IBM Plex Mono', monospace;
        font-size: 0.78rem; margin-top: 1.75rem; padding: 0.9rem; border-top: 1px solid var(--border);
    }}

    @media (max-width: 640px) {{
        .block-container {{ padding-left: 0.85rem; padding-right: 0.85rem; }}
        .oc-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .oc-k-value {{ font-size: 1.1rem; }}
    }}
</style>
""", unsafe_allow_html=True)

_ICONS = {
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "trend-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "trend-down": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "sliders": '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
    "bar-chart": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "gauge": '<path d="M15.6 2.7a10 10 0 1 0 5.7 5.7"/><circle cx="12" cy="12" r="2"/><path d="M13.4 10.6 19 5"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
}


def ic(name: str) -> str:
    return f'<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">{_ICONS[name]}</svg>'


def _html(s: str) -> str:
    return " ".join(s.split())


def kpi(tone, icon_name, label, value, sub="", value_class=""):
    sub_html = f'<div class="oc-k-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="oc-card {tone}"><div class="oc-k-label">{ic(icon_name)}{label}</div>'
        f'<div class="oc-k-value {value_class}">{value}</div>{sub_html}</div>'
    )


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown(_html(f'<div class="oc-side-title">{ic("sliders")}Controls</div>'), unsafe_allow_html=True)

    expiries = core.fetch_expiries()
    expiry = st.selectbox("Expiry", options=expiries, index=0, help="Weekly / monthly expiry (DD-MM-YYYY)")
    custom_exp = st.text_input("Custom expiry (DD-MM-YYYY)", placeholder="e.g. 22-09-2026")
    if custom_exp.strip():
        expiry = custom_exp.strip()

    manual_spot = st.number_input(
        "Manual spot override (optional)", min_value=0.0, value=0.0, step=1.0,
        help="If set, this overrides the automatic spot estimate.",
    )

    auto_refresh = st.checkbox("Auto-refresh every 30s", value=True)

    st.markdown("---")
    st.markdown(_html(f'<div class="oc-side-title">{ic("bar-chart")}Display</div>'), unsafe_allow_html=True)
    show_greeks = st.checkbox("Show Greeks (Δ Γ Θ Vega)", value=True)
    show_iv = st.checkbox("Show IV & PoP", value=True)
    strikes_around_atm = st.slider("Strikes around ATM", 10, 50, 25, 5)

    st.markdown("---")
    st.caption(f"Lot size: {core.NIFTY_LOT_SIZE} (NSE, effective Jan-2026 series)")
    st.caption("Data: Upstox public endpoints (delayed)")

# --------------------------------------------------------------------------- #
# Fetch & compute
# --------------------------------------------------------------------------- #
ticker_slot = st.empty()
ticker_slot.markdown(_html(f'''
<div class="oc-ticker"><div class="oc-ticker-track">
<span class="brand">Option Chain Pro</span><span class="sep">|</span>
<span class="oc-dot off"></span><span class="sym">NIFTY 50</span>
<span class="sep">|</span><span class="px">Loading…</span>
<span class="sep">|</span><span class="brand">Option Chain Pro</span><span class="sep">|</span>
<span class="oc-dot off"></span><span class="sym">NIFTY 50</span>
<span class="sep">|</span><span class="px">Loading…</span>
</div></div>
'''), unsafe_allow_html=True)

with st.spinner("Fetching option chain..."):
    chain_data, err = core.fetch_option_chain(expiry)

if err or not chain_data:
    st.error(f"Could not fetch the option chain: {err or 'empty response'}")
    st.info("Try a different expiry, or check the connection to Upstox's public endpoint.")
    st.stop()

df = core.parse_chain(chain_data)
if df.empty:
    st.warning("No strikes returned for this expiry.")
    st.stop()

expiry_label = chain_data.get("expiry", expiry)
years = core.years_to_expiry(expiry_label)
spot_est = core.estimate_spot(chain_data, df, years=years, manual=manual_spot)
atm = core.nearest_strike(df, spot_est.value)
pcr_val = core.pcr(df)
mp_strike, mp_table = core.max_pain(df)
support, resistance = core.support_resistance(df, n=3)
straddle = core.atm_straddle(df, atm, spot_est.value)
iv_atm = core.atm_iv(df, atm)

dte_days = (years or 0) * 365

# ---- Ticker bar ----
mood_tone = "pos" if pcr_val >= 1.1 else ("neg" if pcr_val <= 0.9 else "accent")
mood_label = "BULLISH BIAS" if pcr_val >= 1.1 else ("BEARISH BIAS" if pcr_val <= 0.9 else "NEUTRAL")
mood_color = POS if mood_tone == "pos" else (NEG if mood_tone == "neg" else ACCENT)

_ticker_inner = f'''
    <span class="brand">Option Chain Pro</span><span class="sep">|</span>
    <span class="oc-dot live"></span><span class="sym">NIFTY 50</span>
    <span class="px">₹{core.fmt_price(spot_est.value, 2)}</span>
    <span class="sep">|</span>
    <span style="color:{mood_color};font-weight:600">{mood_label}</span>
    <span class="sep">|</span>
    <span class="oc-tag">{ic("database")}spot: {spot_est.source}</span>
    <span class="oc-tag">{ic("calendar")}{expiry_label} · {dte_days:.1f}d</span>
    <span class="oc-tag">{ic("clock")}Auto-refresh {"30s" if auto_refresh else "off"}</span>
'''
ticker_slot.markdown(_html(f'''
<div class="oc-ticker"><div class="oc-ticker-track">
{_ticker_inner}
<span class="sep">|</span>
{_ticker_inner}
</div></div>
'''), unsafe_allow_html=True)

if spot_est.source == "max-OI guess":
    st.warning(
        "Spot could not be derived from an API field or from put-call parity (missing LTPs), "
        "so it falls back to the highest-OI strike — this can be a round number, not the real price. "
        "Enter a manual spot in the sidebar for accuracy.",
        icon="⚠️",
    )

# ---- KPI grid ----
cards = [
    kpi("accent", "target", "Spot (est.)", f"₹{core.fmt_price(spot_est.value)}", spot_est.source),
    kpi("", "layers", "ATM Strike", f"{atm:,.0f}", f"IV {core.fmt_num(iv_atm, 1)}%" if iv_atm else ""),
    kpi("amber", "gauge", "Max Pain", f"{mp_strike:,.0f}", f"{'above' if mp_strike > spot_est.value else 'below'} spot"),
    kpi(mood_tone, "activity", "PCR (OI)", core.fmt_num(pcr_val, 2), mood_label),
    kpi("pos" if straddle else "", "trend-up", "Expected Move",
        f"±₹{core.fmt_price(straddle['straddle'], 0)}" if straddle else "—",
        f"{straddle['lower']:,.0f} – {straddle['upper']:,.0f}" if straddle else "n/a"),
]
st.markdown(_html('<div class="oc-grid">' + "".join(cards) + "</div>"), unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Option Chain", "OI & Volume", "Max Pain", "Levels", "About"]
)

# Windowed view around ATM
mid_idx = df.index[df["Strike"] == atm][0] if atm in df["Strike"].values else len(df) // 2
lo = max(0, mid_idx - strikes_around_atm)
hi = min(len(df), mid_idx + strikes_around_atm + 1)
view_df = df.iloc[lo:hi].copy()

with tab1:
    display = pd.DataFrame()
    if show_greeks:
        display["CE Vega"] = view_df["CE_Vega"].map(core.fmt_num)
        display["CE Theta"] = view_df["CE_Theta"].map(core.fmt_num)
        display["CE Gamma"] = view_df["CE_Gamma"].map(lambda x: core.fmt_num(x, 4))
        display["CE Delta"] = view_df["CE_Delta"].map(lambda x: core.fmt_num(x, 3))
    if show_iv:
        display["CE IV%"] = view_df["CE_IV"].map(lambda x: core.fmt_num(x, 1))
        display["CE PoP%"] = view_df["CE_PoP"].map(lambda x: core.fmt_num(x, 1))
    display["CE Vol"] = view_df["CE_Vol"].map(core.fmt_compact)
    display["CE OI"] = view_df["CE_OI"].map(core.fmt_compact)
    display["CE LTP"] = view_df["CE_LTP"].map(core.fmt_price)
    display["Strike"] = view_df["Strike"].map(lambda x: f"* {x:,.0f}" if x == atm else f"{x:,.0f}")
    display["PE LTP"] = view_df["PE_LTP"].map(core.fmt_price)
    display["PE OI"] = view_df["PE_OI"].map(core.fmt_compact)
    display["PE Vol"] = view_df["PE_Vol"].map(core.fmt_compact)
    if show_iv:
        display["PE IV%"] = view_df["PE_IV"].map(lambda x: core.fmt_num(x, 1))
        display["PE PoP%"] = view_df["PE_PoP"].map(lambda x: core.fmt_num(x, 1))
    if show_greeks:
        display["PE Delta"] = view_df["PE_Delta"].map(lambda x: core.fmt_num(x, 3))
        display["PE Gamma"] = view_df["PE_Gamma"].map(lambda x: core.fmt_num(x, 4))
        display["PE Theta"] = view_df["PE_Theta"].map(core.fmt_num)
        display["PE Vega"] = view_df["PE_Vega"].map(core.fmt_num)
    display = display.dropna(axis=1, how="all")

    def style_rows(row):
        strike_val = float(str(row["Strike"]).replace("*", "").strip().replace(",", ""))
        if "*" in str(row["Strike"]):
            return [f"background-color: rgba(59,130,246,0.16); color: {FG}; font-weight: 700"] * len(row)
        out = []
        for col in row.index:
            if col == "Strike":
                out.append(f"background-color: {CARD_ALT}; color: {FG}; font-weight: 700")
            elif col.startswith("CE") and strike_val < atm:
                out.append(f"background-color: {ITM_TINT}")
            elif col.startswith("PE") and strike_val > atm:
                out.append(f"background-color: {ITM_TINT}")
            else:
                out.append("")
        return out

    st.dataframe(
        display.style.apply(style_rows, axis=1),
        width="stretch",
        height=min(720, 42 + 35 * len(display)),
        hide_index=True,
    )
    st.caption(
        f"{len(view_df)} strikes around ATM {atm:,.0f}  •  * = ATM  •  "
        f"shaded = in-the-money  •  lot size {core.NIFTY_LOT_SIZE}  •  data delayed"
    )

    csv = view_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        f"{'⬇'} Export chain as CSV", data=csv,
        file_name=f"nifty_option_chain_{expiry_label}.csv", mime="text/csv",
    )

with tab2:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09,
                         subplot_titles=("Open Interest", "Volume"), row_heights=[0.55, 0.45])

    def bar(y, name, color):
        return go.Bar(x=view_df["Strike"], y=y, name=name,
                       marker=dict(color=color, line=dict(width=0)))

    fig.add_trace(bar(view_df["CE_OI"], "CE OI", POS), row=1, col=1)
    fig.add_trace(bar(view_df["PE_OI"], "PE OI", NEG), row=1, col=1)
    fig.add_trace(bar(view_df["CE_Vol"], "CE Vol", POS), row=2, col=1)
    fig.add_trace(bar(view_df["PE_Vol"], "PE Vol", NEG), row=2, col=1)
    fig.update_annotations(font=dict(family="IBM Plex Mono, monospace", size=14, color=FG), x=0, xanchor="left")

    fig.add_vline(x=atm, line_dash="dash", line_color=ACCENT, line_width=1.5,
                  annotation_text="ATM", annotation_position="top",
                  annotation_font=dict(color=ACCENT, size=12, family="IBM Plex Mono, monospace"), row=1, col=1)
    fig.add_vline(x=atm, line_dash="dash", line_color=ACCENT, line_width=1.5, row=2, col=1)

    fig.update_layout(
        barmode="group", bargap=0.25, height=620,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=MUTED, family="IBM Plex Mono, monospace", size=11)),
        plot_bgcolor=CARD, paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, monospace", color=FG, size=12),
        hoverlabel=dict(bgcolor=CARD_ALT, font=dict(family="IBM Plex Mono, monospace", color=FG)),
    )
    fig.update_xaxes(gridcolor=BORDER, linecolor=BORDER, zeroline=False, title_text="Strike", row=2, col=1)
    fig.update_yaxes(gridcolor=BORDER, linecolor=BORDER, zeroline=False, title_text="OI", row=1, col=1)
    fig.update_yaxes(gridcolor=BORDER, linecolor=BORDER, zeroline=False, title_text="Volume", row=2, col=1)
    st.plotly_chart(fig, width="stretch")

with tab3:
    st.markdown(f"**Max Pain: `{mp_strike:,.0f}`** — the strike where option *writers* collectively "
                f"lose the least if NIFTY expires there. Not a prediction, just current OI positioning.")
    mp_view = mp_table[(mp_table["Strike"] >= view_df["Strike"].min()) & (mp_table["Strike"] <= view_df["Strike"].max())]
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=mp_view["Strike"], y=mp_view["Total_Pain"], mode="lines",
                               line=dict(color=ACCENT, width=2), name="Total pain",
                               fill="tozeroy", fillcolor="rgba(59,130,246,0.08)"))
    fig2.add_vline(x=mp_strike, line_dash="dash", line_color=AMBER, line_width=1.5,
                   annotation_text="Max Pain", annotation_position="top",
                   annotation_font=dict(color=AMBER, size=12, family="IBM Plex Mono, monospace"))
    fig2.add_vline(x=spot_est.value, line_dash="dot", line_color=FG, line_width=1.5,
                   annotation_text="Spot", annotation_position="bottom",
                   annotation_font=dict(color=FG, size=12, family="IBM Plex Mono, monospace"))
    fig2.update_layout(
        height=440, margin=dict(l=40, r=20, t=30, b=40), plot_bgcolor=CARD, paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, monospace", color=FG, size=12), showlegend=False,
        xaxis_title="Strike", yaxis_title="Aggregate option-buyer payout (₹, OI-weighted)",
    )
    fig2.update_xaxes(gridcolor=BORDER, linecolor=BORDER, zeroline=False)
    fig2.update_yaxes(gridcolor=BORDER, linecolor=BORDER, zeroline=False)
    st.plotly_chart(fig2, width="stretch")

with tab4:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Support (highest PE OI)**")
        rows = "".join(
            f'<div class="oc-level"><span class="strike">{k:,.0f}</span>'
            f'<span class="oc-badge sup">Support</span><span class="oi">{core.fmt_compact(oi)} OI</span></div>'
            for k, oi in support
        )
        st.markdown(_html(f'<div class="oc-levels">{rows}</div>'), unsafe_allow_html=True)
    with c2:
        st.markdown("**Resistance (highest CE OI)**")
        rows = "".join(
            f'<div class="oc-level"><span class="strike">{k:,.0f}</span>'
            f'<span class="oc-badge res">Resistance</span><span class="oi">{core.fmt_compact(oi)} OI</span></div>'
            for k, oi in resistance
        )
        st.markdown(_html(f'<div class="oc-levels">{rows}</div>'), unsafe_allow_html=True)

    st.markdown("---")
    if straddle:
        st.markdown(
            f"**ATM straddle ({atm:,.0f}):** CE `{core.fmt_price(straddle['call'])}` + "
            f"PE `{core.fmt_price(straddle['put'])}` = `{core.fmt_price(straddle['straddle'])}` "
            f"({core.fmt_num(straddle['pct'], 2)}% of spot) — implies a range of "
            f"**{straddle['lower']:,.0f} – {straddle['upper']:,.0f}** by expiry if the market is priced fairly."
        )
    skew = core.iv_skew(df, atm)
    if skew is not None:
        lean = "puts richer (downside hedging demand)" if skew > 0 else "calls richer (upside demand)"
        st.markdown(f"**IV skew (5-strike):** `{skew:+.2f}` pts — {lean}.")

with tab5:
    st.markdown(f"""
### About OptionChainPro

Fetches the **NIFTY 50 option chain** from Upstox's public (no-login) endpoint and adds
the analytics a discretionary options trader actually checks first.

**Spot estimate** — shown in the ticker bar with its source:
1. A `spot`-like field in the API response, if present
2. **Put-call parity**: at the strikes where call and put premiums are closest,
   spot ≈ (strike + call − put), discounted for time to expiry
3. Manual override (sidebar)
4. Last resort: the strike with the highest total OI — this is only a rough guess
   and can sit far from the real price, which is flagged in the app when it's used

**Analytics**
- Max Pain (OI-weighted option-writer payout, not a prediction)
- Support / resistance from OI concentration
- ATM straddle → implied expected move by expiry
- 5-strike IV skew
- CSV export of the visible chain

**Contract specs:** NIFTY lot size = **{core.NIFTY_LOT_SIZE}** (NSE revision effective the Jan-2026 series).

**Disclaimer:** educational tool, delayed public data, not investment advice.
""")

st.markdown(_html(f'''
<div class="oc-footer">OptionChainPro · Last updated {datetime.now().strftime("%d %b %Y, %H:%M:%S IST")}</div>
'''), unsafe_allow_html=True)

if auto_refresh:
    time.sleep(30)
    st.rerun()

"""
FVM Cockpit — research / manual-investing UI (Streamlit).

    source .venv/bin/activate
    streamlit run scripts/fvm_ui.py

Opens at http://localhost:8501. Reads fvm.db + market.db cache-only — run
scripts/fvm_ingest.py + scripts/fvm_prices.py first.

This is the manual-investing core (U1): Today's Shortlist + Stock Detail. Coverage,
Milestone-A viewer, Scoring Lab, Portfolio follow (see docs/FVM_Forward_Plan.md §6b).
The UI never reimplements engine logic — it calls trader.fvm.ui.data, which calls the
tested scoring/vetoes/technical/handoff functions.
"""

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from trader.fvm.technical import (
    EXT_HI_ATR, MA_DAILY, MA_LONG_W, MA_SHORT_W,
)
from trader.fvm.ui import data as fvm_data

DB = str(ROOT / "data" / "fvm.db")
MARKET_DB = str(ROOT / "data" / "market.db")

DECISION_COLORS = {
    "CANDIDATE": "#1a9850", "NO_TIMING": "#66bd63", "NO_TREND": "#fdae61",
    "WEAK_FUND": "#d9d9d9", "VETOED": "#d73027",
}

st.set_page_config(page_title="FVM Cockpit", page_icon="📈", layout="wide")


# ------------------------------------------------------------------ #
# Cached data layer                                                  #
# ------------------------------------------------------------------ #
@st.cache_data(show_spinner="Scoring the universe…")
def board(asof: str) -> dict:
    return fvm_data.build_board(DB, MARKET_DB, asof)


@st.cache_data(show_spinner="Loading stock…")
def stock(symbol: str, asof: str) -> dict:
    return fvm_data.load_stock(DB, MARKET_DB, symbol, asof)


@st.cache_data(show_spinner="Reading coverage…")
def coverage(asof: str) -> dict:
    return fvm_data.coverage(DB, MARKET_DB, asof)


# ------------------------------------------------------------------ #
# Helpers                                                            #
# ------------------------------------------------------------------ #
def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def _decision_badge(dec: str) -> str:
    color = DECISION_COLORS.get(dec, "#888")
    return f"<span style='background:{color};color:#fff;padding:2px 10px;border-radius:10px;font-weight:600'>{dec}</span>"


# ------------------------------------------------------------------ #
# Page: Today's Shortlist                                            #
# ------------------------------------------------------------------ #
def page_shortlist(asof: str):
    st.header("Today's Shortlist")
    b = board(asof)
    st.caption(f"As of **{asof}** · {b['priced']}/{b['total']} ingested names priced")

    if b["priced"] == 0:
        st.warning("No priced names. Run `scripts/fvm_prices.py` first.")
        return

    board_df = b["board"]

    # --- view 1: candidates ---
    st.subheader("FVM candidates — clears fundamentals + trend + timing")
    cands = b["candidates"]
    if not cands:
        st.info("No name clears the full pipeline today. Watch NO_TIMING names below — "
                "they pass fundamentals + trend and only need an entry trigger.")
    else:
        cdf = pd.DataFrame(cands)[
            ["symbol", "final_rank", "composite", "pool_pctile", "trend_score", "timing_score"]]
        cdf["pool_pctile"] = (100 * cdf["pool_pctile"]).round(0)
        cdf = cdf.rename(columns={"final_rank": "rank", "pool_pctile": "pool%",
                                  "trend_score": "trend", "timing_score": "timing"})
        st.dataframe(cdf.round({"rank": 3, "composite": 1, "trend": 2, "timing": 2}),
                     use_container_width=True, hide_index=True)

    # --- view 2: full board ---
    st.subheader("Full board")
    c1, c2, c3 = st.columns([2, 2, 3])
    decisions = sorted(board_df["decision"].unique(),
                       key=lambda d: list(DECISION_COLORS).index(d) if d in DECISION_COLORS else 9)
    pick = c1.multiselect("Decision", decisions, default=decisions)
    sectors = ["(all)"] + sorted(board_df["sector"].unique())
    sec = c2.selectbox("Sector", sectors)
    search = c3.text_input("Search symbol")

    view = board_df[board_df["decision"].isin(pick)]
    if sec != "(all)":
        view = view[view["sector"] == sec]
    if search:
        view = view[view["symbol"].str.contains(search.upper())]

    cols = ["symbol", "sector", "composite", "earnings", "valuation", "forward",
            "ownership", "balance_sheet", "trend", "timing", "decision", "note"]
    styled = view[cols].style.map(
        lambda d: f"background-color:{DECISION_COLORS.get(d, '')};color:#222"
        if d in DECISION_COLORS else "", subset=["decision"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=520)
    st.caption("CANDIDATE=acts today · NO_TIMING=trend ok, no trigger · "
               "NO_TREND=fund ok, not an uptrend · WEAK_FUND=below fundamental cut · VETOED=red flag")

    st.divider()
    pickname = st.selectbox("Open Stock Detail for", ["(none)"] + view["symbol"].tolist())
    if pickname != "(none)":
        st.session_state["detail_symbol"] = pickname
        st.session_state["nav"] = "Stock Detail"
        st.rerun()


# ------------------------------------------------------------------ #
# Page: Stock Detail                                                 #
# ------------------------------------------------------------------ #
def _trend_chart(weekly: pd.DataFrame):
    w = weekly.copy()
    w["ts"] = pd.to_datetime(w["timestamp"])
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=w["ts"], open=w["open"], high=w["high"], low=w["low"],
                                 close=w["close"], name="weekly", showlegend=False))
    fig.add_trace(go.Scatter(x=w["ts"], y=_sma(w["close"], MA_LONG_W),
                             name=f"{MA_LONG_W}w MA", line=dict(color="#d62728", width=1.5)))
    fig.add_trace(go.Scatter(x=w["ts"], y=_sma(w["close"], MA_SHORT_W),
                             name=f"{MA_SHORT_W}w MA", line=dict(color="#1f77b4", width=1.5)))
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.05))
    return fig


def _timing_chart(daily: pd.DataFrame, initial_stop, last_price):
    d = daily.copy().tail(260)
    d["ts"] = pd.to_datetime(d["timestamp"])
    ma50 = _sma(daily["close"], MA_DAILY).tail(260)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25],
                        vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=d["ts"], open=d["open"], high=d["high"], low=d["low"],
                                 close=d["close"], name="daily", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=d["ts"], y=ma50, name=f"{MA_DAILY}d MA",
                             line=dict(color="#ff7f0e", width=1.5)), row=1, col=1)
    if initial_stop:
        fig.add_hline(y=initial_stop, line=dict(color="#d73027", width=1, dash="dash"),
                      annotation_text=f"stop {initial_stop:.1f}", row=1, col=1)
    fig.add_trace(go.Bar(x=d["ts"], y=d["volume"], name="vol",
                         marker_color="#bbb", showlegend=False), row=2, col=1)
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.08))
    return fig


def page_detail(asof: str):
    b = board(asof)
    names = b["board"]["symbol"].tolist() if not b["board"].empty else fvm_data.scored_symbols(DB)
    default = st.session_state.get("detail_symbol", names[0] if names else None)
    if not names:
        st.warning("No scored names available.")
        return
    idx = names.index(default) if default in names else 0
    sym = st.selectbox("Symbol", names, index=idx)
    st.session_state["detail_symbol"] = sym

    s = stock(sym, asof)
    if not s["priced"]:
        st.warning(f"{sym}: no price coverage on/before {asof}.")
        return

    diag = b["diag"].get(sym, {})
    dec = fvm_data._decision(diag)
    st.markdown(f"## {sym} &nbsp; {_decision_badge(dec)}", unsafe_allow_html=True)
    st.caption(f"{s['sector']} · as of {asof} · last close "
               f"{s['last_price']:.1f}" if s["last_price"] else s["sector"])

    sc = s["scores"]
    tech = s["technical"]
    m = st.columns(5)
    m[0].metric("Composite", f"{sc['composite']:.1f}")
    m[1].metric("Trend", f"{tech['trend_score']:.2f}")
    m[2].metric("Timing", f"{tech['timing_score']:.2f}")
    m[3].metric("Technical", f"{tech['technical_score']:.3f}")
    m[4].metric("Veto", "PASS" if s["veto"]["passed"] else "FAIL",
                delta=None if s["veto"]["passed"] else ",".join(s["veto"]["reasons"]),
                delta_color="inverse")
    if tech["extension_vetoed"]:
        st.warning("Parabolic-extension veto active — price > "
                   f"{MA_DAILY}d MA + {EXT_HI_ATR}×ATR. Entry blocked even if other gates pass.")

    # pillars
    st.subheader("Fundamental pillars")
    pillars = sc["pillars"]
    pfig = go.Figure(go.Bar(
        x=[pillars[p] for p in fvm_data.PILLARS], y=fvm_data.PILLARS, orientation="h",
        marker_color="#1f77b4", text=[f"{pillars[p]:.2f}" for p in fvm_data.PILLARS]))
    pfig.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0), xaxis_range=[0, 1])
    st.plotly_chart(pfig, use_container_width=True)

    # technical charts
    st.subheader("Technical")
    tc1, tc2 = st.columns(2)
    with tc1:
        st.caption(f"Weekly + {MA_LONG_W}w/{MA_SHORT_W}w MA — Stage-2 trend")
        st.plotly_chart(_trend_chart(s["weekly"]), use_container_width=True)
    with tc2:
        st.caption(f"Daily + {MA_DAILY}d MA + catastrophe stop — timing")
        st.plotly_chart(_timing_chart(s["daily"], tech["initial_stop"], s["last_price"]),
                        use_container_width=True)

    # factor + fundamentals + ownership tabs
    t1, t2, t3 = st.tabs(["Factor table", "Fundamentals history", "Shareholding"])
    with t1:
        fdf = s["factors"]
        st.dataframe(fdf.style.background_gradient(subset=["normalized"], cmap="RdYlGn",
                                                   vmin=0, vmax=1),
                     use_container_width=True, hide_index=True, height=560)
        st.caption("normalized = cross-sectional score (0–1, higher better after direction). "
                   "raw = underlying value before normalization.")
    with t2:
        if not s["fundamentals"]:
            st.info("No PIT fundamentals recorded for this name.")
        else:
            fh = pd.DataFrame(s["fundamentals"]).sort_index()
            st.dataframe(fh, use_container_width=True, height=420)
            st.caption("Point-in-time: only vintages knowable on/before the as-of date.")
    with t3:
        if not s["shareholding"]:
            st.info("No shareholding history recorded for this name.")
        else:
            sh = pd.DataFrame(s["shareholding"]).sort_index()
            st.line_chart(sh)
            st.dataframe(sh, use_container_width=True)


# ------------------------------------------------------------------ #
# Page: Universe & Coverage (ops — steer the daily ingest)           #
# ------------------------------------------------------------------ #
def page_coverage(asof: str):
    st.header("Universe & Coverage")
    c = coverage(asof)
    st.caption(f"NIFTY500 non-financial universe as of **{asof}** · "
               f"last fundamentals ingest {c['last_ingest'][:10] or '—'}")

    m = st.columns(4)
    pct = 100 * c["ingested"] / c["target"] if c["target"] else 0
    m[0].metric("Ingested / target", f"{c['ingested']} / {c['target']}", f"{pct:.0f}%")
    m[1].metric("Priced", f"{c['priced']} / {c['ingested']}")
    m[2].metric("Missing (to ingest)", len(c["missing"]))
    m[3].metric("Quarter depth", f"{c['min_q_depth']}–{c['max_q_depth']}")
    st.progress(min(1.0, c["ingested"] / c["target"] if c["target"] else 0),
                text=f"{c['ingested']} of {c['target']} names ingested "
                     f"({c['target'] - c['ingested']} to go)")

    df = c["df"]
    t1, t2, t3 = st.tabs([f"Ingested ({c['ingested']})",
                          f"Missing ({len(c['missing'])})", "By sector"])
    with t1:
        ing = df[df["ingested"]].copy()
        flag = ing[(ing["price_bars"] == 0) | (~ing["shareholding"]) | (ing["q_depth"] < 8)]
        if not flag.empty:
            st.warning(f"{len(flag)} ingested name(s) have gaps (no price / no shareholding / "
                       f"shallow quarters): {', '.join(flag['symbol'])}")
        cols = ["symbol", "sector", "q_depth", "a_depth", "last_q", "shareholding",
                "price_bars", "price_last", "last_ingest"]
        st.dataframe(ing[cols].sort_values("symbol"),
                     use_container_width=True, hide_index=True, height=480)
        st.caption("q_depth = distinct quarterly periods (drives min-scoreability; "
                   "Trendlyne caps ~13). shallow / no-price rows weaken scoring for that name.")
    with t2:
        miss = df[~df["ingested"]][["symbol", "sector"]].sort_values(["sector", "symbol"])
        st.caption("Targets not yet ingested — feed these to the daily `fvm_ingest` quota "
                   "(mid-caps first, per the forward plan).")
        st.dataframe(miss, use_container_width=True, hide_index=True, height=480)
        st.download_button("Download missing symbols (CSV)",
                           miss.to_csv(index=False), "fvm_missing_symbols.csv", "text/csv")
    with t3:
        by_sec = df.groupby("sector").agg(
            target=("symbol", "size"),
            ingested=("ingested", "sum")).reset_index()
        by_sec["pct"] = (100 * by_sec["ingested"] / by_sec["target"]).round(0)
        by_sec = by_sec.sort_values("target", ascending=False)
        st.dataframe(by_sec, use_container_width=True, hide_index=True, height=480)
        st.caption("Coverage per sector — spot lopsided ingest (a fundamental overlay needs "
                   "breadth within each sector for the sector-relative valuation factors).")


# ------------------------------------------------------------------ #
# Shell                                                              #
# ------------------------------------------------------------------ #
def main():
    st.sidebar.title("📈 FVM Cockpit")
    asof = st.sidebar.date_input("As of", value=datetime.date.today(),
                                 max_value=datetime.date.today()).isoformat()

    pages = ["Today's Shortlist", "Stock Detail", "Universe & Coverage"]
    nav = st.session_state.get("nav", pages[0])
    nav = st.sidebar.radio("Page", pages, index=pages.index(nav) if nav in pages else 0)
    st.session_state["nav"] = nav

    st.sidebar.divider()
    if st.sidebar.button("Clear cache / refresh"):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.caption("Cache-only. Run fvm_ingest + fvm_prices to refresh data.\n\n"
                       "Milestone-A · Scoring Lab · Portfolio — coming next "
                       "(docs/FVM_Forward_Plan.md §6b).")

    if nav == "Today's Shortlist":
        page_shortlist(asof)
    elif nav == "Stock Detail":
        page_detail(asof)
    else:
        page_coverage(asof)


if __name__ == "__main__":
    main()

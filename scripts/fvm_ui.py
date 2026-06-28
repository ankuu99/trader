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


@st.cache_data(show_spinner="Running the walk-forward gate (~minutes, first run only)…")
def milestone(test_len_w: int, step_w: int, capital: float) -> dict:
    return fvm_data.milestone_a(DB, MARKET_DB, test_len_w=test_len_w, step_w=step_w,
                                capital=capital)


@st.cache_data(show_spinner="Scoring the universe…")
def lab(asof: str) -> dict:
    return fvm_data.scoring_lab(DB, MARKET_DB, asof)


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
# Page: Milestone-A / Validation                                     #
# ------------------------------------------------------------------ #
def _equity_chart(eq: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq["week"], y=eq["FVM"], name="FVM",
                             line=dict(color="#1a9850", width=2)))
    fig.add_trace(go.Scatter(x=eq["week"], y=eq["Benchmark"], name="Naive momentum",
                             line=dict(color="#888", width=2, dash="dot")))
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", y=1.06), yaxis_title="sleeve equity (₹)")
    return fig


def page_milestone():
    st.header("Milestone-A — Validation Gate")
    st.caption("Rules-only FVM vs a naive-momentum benchmark (same universe + cost model), "
               "rolling walk-forward folds. Gate (§12c): **beat the benchmark AND be profitable "
               "in the majority of folds.** First run is slow (~minutes); cached after.")

    c1, c2, c3 = st.columns(3)
    test_len_w = c1.slider("Fold length (weeks)", 26, 78, 39, step=13)
    step_w = c2.slider("Fold stride (weeks)", 4, 39, 13, step=1)
    capital = c3.number_input("Sleeve capital (₹)", 100_000, 5_000_000, 500_000, step=50_000)

    if not st.session_state.get("ms_run"):
        st.info("Heavy compute. Click to run the gate with the settings above.")
        if st.button("▶ Run walk-forward gate", type="primary"):
            st.session_state["ms_run"] = True
            st.rerun()
        return

    m = milestone(test_len_w, step_w, capital)
    if not m["ok"]:
        st.error(m["reason"])
        return

    s = m["summary"]
    passed = s["gate_pass"]
    (st.success if passed else st.error)(
        f"### GATE {'PASS' if passed else 'FAIL'} — "
        f"beats benchmark {s['fvm_beats_bench']}/{s['folds']}, "
        f"profitable {s['fvm_profitable']}/{s['folds']}")
    if m["priced"] < 30:
        st.warning(f"Thin universe ({m['priced']}/{m['total']} names) — **indicative, not "
                   f"decisive.** Re-run as fundamentals coverage grows toward 399 "
                   f"(see Universe & Coverage). Do not tune params to flip this.")

    mc = st.columns(5)
    mc[0].metric("Folds", s["folds"])
    mc[1].metric("Beats benchmark", f"{s['fvm_beats_bench']}/{s['folds']}",
                 f"{s['fvm_beats_bench_pct']:.0f}%")
    mc[2].metric("Profitable", f"{s['fvm_profitable']}/{s['folds']}",
                 f"{s['fvm_profitable_pct']:.0f}%")
    mc[3].metric("Mean edge", f"{s['mean_edge_pct']:+.1f}pp",
                 f"FVM {s['mean_fvm_return_pct']:+.1f}% vs bench {s['mean_bench_return_pct']:+.1f}%")
    mc[4].metric("Worst fold maxDD", f"{s['worst_fvm_maxdd_pct']:.1f}%")

    st.subheader("Equity — FVM vs benchmark (continuous, full data-valid window)")
    st.caption(f"Data-valid window starts {m['start_week']} "
               f"(first week with ≥{m['params']['min_scoreable']} scoreable names). "
               f"{m['priced']}/{m['total']} priced · {m['n_folds']} folds.")
    st.plotly_chart(_equity_chart(m["equity"]), use_container_width=True)

    st.subheader("Per-fold results")
    fdf = m["folds"][["fold", "fvm_return_pct", "bench_return_pct", "edge_pct",
                      "fvm_trades", "fvm_win_rate", "fvm_maxdd_pct"]].copy()
    fdf = fdf.rename(columns={"fvm_return_pct": "FVM %", "bench_return_pct": "bench %",
                              "edge_pct": "edge pp", "fvm_trades": "trades",
                              "fvm_win_rate": "win %", "fvm_maxdd_pct": "maxDD %"})
    styled = fdf.style.format({"FVM %": "{:+.1f}", "bench %": "{:+.1f}", "edge pp": "{:+.1f}",
                               "win %": "{:.0f}", "maxDD %": "{:.1f}"}).map(
        lambda v: f"color:{'#1a9850' if v > 0 else '#d73027'}", subset=["edge pp"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.subheader("Regime split — does the edge come from defence?")
    r = m["regime"]
    rc = st.columns(2)
    rc[0].metric(f"Down/choppy folds (bench ≤ 0) · n={r['down_n']}",
                 f"{r['down_edge']:+.1f}pp edge" if r["down_edge"] is not None else "—",
                 f"FVM {r['down_fvm']:+.1f}%" if r["down_fvm"] is not None else None)
    rc[1].metric(f"Up folds (bench > 0) · n={r['up_n']}",
                 f"{r['up_edge']:+.1f}pp edge" if r["up_edge"] is not None else "—",
                 f"FVM {r['up_fvm']:+.1f}%" if r["up_fvm"] is not None else None,
                 delta_color="inverse")
    st.caption("A large positive edge in down folds with a negative edge in up folds = "
               "defensive quality overlay (wins drawdowns, lags momentum rallies) — not a "
               "momentum-beating return engine. That's the honest read of the current result.")


# ------------------------------------------------------------------ #
# Page: Scoring Lab                                                   #
# ------------------------------------------------------------------ #
def page_scoring_lab(asof: str):
    st.header("Scoring Lab")
    L = lab(asof)
    if L.get("priced", 0) == 0:
        st.warning("No priced names. Run `scripts/fvm_prices.py` first.")
        return
    st.caption(f"Cross-sectional score anatomy as of **{asof}** · {L['priced']} scored names. "
               "The composite is relative — every factor is normalized across this population, "
               "so coverage and breadth shape the scores.")

    comp = pd.Series(L["composite"])
    cut0 = comp.quantile(0.70)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader("Composite distribution")
        fig = go.Figure(go.Histogram(x=comp, nbinsx=20, marker_color="#1f77b4"))
        fig.add_vline(x=cut0, line=dict(color="#1a9850", dash="dash"),
                      annotation_text="70th pctile (Gate-A cut)")
        fig.add_vline(x=50.0, line=dict(color="#d73027", dash="dot"),
                      annotation_text="floor 50")
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis_title="composite", yaxis_title="names")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Pillar contributions")
        pt = L["pillar_table"]
        pfig = go.Figure(go.Bar(x=pt["mean_contribution"], y=pt["pillar"], orientation="h",
                                marker_color="#1f77b4",
                                text=[f"{v:.1f}" for v in pt["mean_contribution"]]))
        pfig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0),
                           xaxis_title="mean contribution to composite")
        st.plotly_chart(pfig, use_container_width=True)
        st.caption("A pillar pinned at its weight×0.5 = no cross-sectional signal "
                   "(all names neutral — usually missing data).")

    st.subheader("Factor coverage & signal")
    ft = L["factor_table"]
    thin = ft[ft["coverage_pct"] < 50]
    if not thin.empty:
        st.warning(f"{len(thin)} factor(s) below 50% coverage — they sit at neutral 0.5 for most "
                   f"names and add no signal: {', '.join(thin['factor'])}. Fix via the ingest "
                   f"(shareholding/quarterly depth) before reading too much into the pillars.")
    st.dataframe(
        ft.sort_values(["pillar", "coverage_pct"]).style
          .background_gradient(subset=["coverage_pct"], cmap="RdYlGn", vmin=0, vmax=100)
          .background_gradient(subset=["mean_normalized"], cmap="RdYlGn", vmin=0, vmax=1),
        use_container_width=True, hide_index=True, height=440)
    st.caption("coverage_pct = names with a non-null raw value (rest fall back to neutral 0.5). "
               "mean_normalized far from 0.5 = the factor is actually discriminating.")

    st.subheader("Gate sensitivity")
    st.caption("Move the gates and watch the funnel. Shows how many names survive each stage — "
               "**use to understand the gates, not to tune them to a desired candidate count "
               "(overfit risk on a thin universe).**")
    g1, g2, g3 = st.columns(3)
    pctile_cut = g1.slider("Gate-A composite pctile cut", 0.0, 1.0, 0.70, 0.05)
    floor = g2.slider("Gate-A composite floor", 0.0, 100.0, 50.0, 5.0)
    trend_floor = g3.slider("Gate-B trend floor", 0.0, 1.0, 0.40, 0.05)

    gc = fvm_data.gate_counts(L, pctile_cut, floor, trend_floor)
    funnel = [("Universe", gc["universe"]), ("Pass veto", gc["veto_ok"]),
              ("Gate A (fund)", gc["gate_a"]), ("Gate B (trend)", gc["gate_b"]),
              ("Trigger (timing)", gc["trigger"]), ("Candidates", gc["candidates"])]
    fc = st.columns(len(funnel))
    for col, (label, v) in zip(fc, funnel):
        col.metric(label, v)
    ffig = go.Figure(go.Funnel(y=[f[0] for f in funnel], x=[f[1] for f in funnel],
                               marker=dict(color="#1f77b4")))
    ffig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(ffig, use_container_width=True)
    if gc["trigger"] == 0:
        st.info("Zero triggers today is common — Gate-B names just have no fresh pullback/breakout "
                "(timing_score 0). The funnel narrows at the timing stage, not the fundamentals.")


# ------------------------------------------------------------------ #
# Shell                                                              #
# ------------------------------------------------------------------ #
def main():
    st.sidebar.title("📈 FVM Cockpit")
    asof = st.sidebar.date_input("As of", value=datetime.date.today(),
                                 max_value=datetime.date.today()).isoformat()

    pages = ["Today's Shortlist", "Stock Detail", "Universe & Coverage",
             "Milestone-A", "Scoring Lab"]
    nav = st.session_state.get("nav", pages[0])
    nav = st.sidebar.radio("Page", pages, index=pages.index(nav) if nav in pages else 0)
    st.session_state["nav"] = nav

    st.sidebar.divider()
    if st.sidebar.button("Clear cache / refresh"):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.caption("Cache-only. Run fvm_ingest + fvm_prices to refresh data.\n\n"
                       "Portfolio / Live — coming after Phase 5 "
                       "(docs/FVM_Forward_Plan.md §6b).")

    if nav == "Today's Shortlist":
        page_shortlist(asof)
    elif nav == "Stock Detail":
        page_detail(asof)
    elif nav == "Universe & Coverage":
        page_coverage(asof)
    elif nav == "Milestone-A":
        page_milestone()
    else:
        page_scoring_lab(asof)


if __name__ == "__main__":
    main()

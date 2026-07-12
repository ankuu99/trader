"""
Extrema Lab — synthetic dip/peak detection testbed (Streamlit).

    streamlit run scripts/extrema_lab.py

Answers one question before any backtesting: can the detection mechanism
(labeler -> features -> model) actually find dips and peaks on data where we
KNOW the answer? Ground truth is hand-labeled on the chart; the generator's
noise-free extrema are only an optional pre-seed.

Tabs: Generate | Label | Run & Inspect | Training view | Metrics.
Isolated from the trading path: imports FROM trader/ read-only, writes only
under lab_data/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st

from scripts.lab.generator import (
    SCENARIOS,
    load_scenario,
    save_scenario,
    scenario_dir,
    scenario_exists,
)
from scripts.lab.harness import HarnessResult, run_mechanism
from scripts.lab.labelstore import LabelStore
from scripts.lab.metrics import (
    as_trained_label_quality,
    comparison_table,
    evaluate_mechanism,
    label_quality,
    truth_positions,
)

st.set_page_config(page_title="Extrema Lab", layout="wide")

# Semantic colors (dip/buy = green, peak/sell = red — repo convention). Every
# detection class also carries a distinct marker SHAPE, so identity never rides
# on color alone.
C_DIP = "#2e7d32"
C_PEAK = "#c62828"
C_FP = "#e65100"
C_FN = "#757575"
C_PRICE = "#1565c0"
C_SIGNAL = "rgba(21, 101, 192, 0.35)"

MECH_LABELS = {"logistic": "Logistic (live)", "mlp": "MLP",
               "gbdt": "GBDT (benchmark winner)", "rsi_rule": "RSI rule"}


# ---------------------------------------------------------------------------
# Cached loaders / runners
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_candles(scenario: str, mtime: float) -> pd.DataFrame:
    df, _ = load_scenario(scenario)
    return df


def _meta(scenario: str) -> dict:
    return json.loads((scenario_dir(scenario) / "meta.json").read_text())


@st.cache_data(show_spinner="Running walk-forward…")
def _cached_run(scenario: str, mechanism: str, params_json: str,
                rule_json: str, mtime: float) -> HarnessResult:
    df, _ = load_scenario(scenario)
    return run_mechanism(mechanism, df.to_dict("records"),
                         json.loads(params_json), json.loads(rule_json))


def _candles_mtime(scenario: str) -> float:
    p = scenario_dir(scenario) / "candles.csv"
    return p.stat().st_mtime if p.exists() else 0.0


# ---------------------------------------------------------------------------
# Sidebar — scenario + params
# ---------------------------------------------------------------------------

st.sidebar.title("Extrema Lab")

scenario = st.sidebar.selectbox("Scenario", list(SCENARIOS), index=0)

with st.sidebar.expander("Generate / regenerate"):
    seed = st.number_input("Seed", value=SCENARIOS[scenario].seed, step=1)
    if st.button("Generate scenario", width="stretch"):
        spec = SCENARIOS[scenario]
        spec.seed = int(seed)
        save_scenario(spec)
        st.cache_data.clear()
        st.rerun()

if not scenario_exists(scenario):
    st.info("Scenario not generated yet — use **Generate / regenerate** in the "
            "sidebar, or run `python scripts/lab/generator.py`.")
    st.stop()

candles_df = _load_candles(scenario, _candles_mtime(scenario))
meta = _meta(scenario)
store = LabelStore(scenario_dir(scenario))
N = len(candles_df)

st.sidebar.subheader("Model params")
warmup_bars = st.sidebar.number_input("warmup_bars", 50, 5000, 300, step=50)
lookback_bars = st.sidebar.number_input("lookback_bars", 100, 20000, 1200, step=100)
retrain_every = st.sidebar.number_input("retrain_every", 1, 500, 25)
labeler_type = st.sidebar.selectbox(
    "Labeler", ["extrema", "zigzag", "trend_scan"], index=0,
    help="zigzag = min-%-reversal swing pivots (trend-robust); "
         "pair with a long lookback (clean labels are sparse)")
extrema_order = st.sidebar.number_input("extrema_order", 2, 50, 10,
                                        disabled=labeler_type != "extrema")
zz_reversal = st.sidebar.number_input("zigzag reversal_pct", 0.5, 10.0, 1.5, step=0.5,
                                      disabled=labeler_type != "zigzag")
neutral_enabled = st.sidebar.checkbox(
    "neutral class", value=False,
    help="3rd class for mid-move bars — stops descents leaking into P(min); "
         "use lower thresholds (~0.45-0.65)")
neutral_ratio = st.sidebar.number_input("neutral ratio", 0.5, 5.0, 2.0, step=0.5,
                                        disabled=not neutral_enabled)
regime_features = st.sidebar.checkbox(
    "regime features", value=False,
    help="append ER/VR/slope-tstat at 100/400/1600 bars (extrema_regime pipeline)")
fl_enabled = st.sidebar.checkbox("forward_label filter", value=False)
if fl_enabled:
    fl_bars = st.sidebar.number_input("forward_bars", 10, 500, 150)
    fl_ret = st.sidebar.number_input("min_return_pct", 0.1, 10.0, 1.5, step=0.1)

st.sidebar.subheader("Detection")
mechanisms = st.sidebar.multiselect(
    "Mechanisms", list(MECH_LABELS), default=["logistic"],
    format_func=MECH_LABELS.get,
)
tol_bars = st.sidebar.number_input("Match tolerance (± bars)", 1, 50, 5)
with st.sidebar.expander("Thresholds per mechanism"):
    thr: dict[str, tuple[float, float]] = {}
    defaults = {"logistic": (0.90, 0.85), "mlp": (0.90, 0.85),
                "gbdt": (0.65, 0.60), "rsi_rule": (0.75, 0.75)}
    for m in MECH_LABELS:
        c1, c2 = st.columns(2)
        t_min = c1.number_input(f"{m} dip", 0.0, 1.0, defaults[m][0], step=0.05, key=f"thr_min_{m}")
        t_max = c2.number_input(f"{m} peak", 0.0, 1.0, defaults[m][1], step=0.05, key=f"thr_max_{m}")
        thr[m] = (t_min, t_max)
with st.sidebar.expander("Advanced"):
    mlp_seed = st.number_input("MLP random_state", 0, 9999, 42)
    rsi_period = st.number_input("RSI period", 5, 50, 14)
    rsi_low = st.number_input("RSI low band", 5.0, 50.0, 30.0, step=5.0)
    rsi_high = st.number_input("RSI high band", 50.0, 95.0, 70.0, step=5.0)

params: dict = {
    "warmup_bars": int(warmup_bars),
    "lookback_bars": int(lookback_bars),
    "retrain_every": int(retrain_every),
    "extrema_order": int(extrema_order),
    "mlp_model": {"random_state": int(mlp_seed)},
}
labels_cfg: dict = {"type": labeler_type}
if labeler_type == "zigzag":
    labels_cfg["zigzag"] = {"reversal_pct": float(zz_reversal)}
if neutral_enabled:
    labels_cfg["neutral"] = {"enabled": True, "ratio": float(neutral_ratio)}
if labels_cfg != {"type": "extrema"}:
    params["labels"] = labels_cfg
if regime_features:
    params["features"] = {"type": "extrema_regime"}
if fl_enabled:
    params["forward_label"] = {
        "enabled": True, "forward_bars": int(fl_bars), "min_return_pct": float(fl_ret),
    }
rule_params = {"period": int(rsi_period), "low": float(rsi_low), "high": float(rsi_high)}
params_json = json.dumps(params, sort_keys=True)
rule_json = json.dumps(rule_params, sort_keys=True)


# ---------------------------------------------------------------------------
# Shared window navigation
# ---------------------------------------------------------------------------

def window_nav(key_prefix: str) -> tuple[int, int]:
    """Window-size + position controls. Per-tab state: buttons mutate the
    slider's own session key BEFORE the slider is instantiated (legal in
    Streamlit; mutating after instantiation is not)."""
    c1, c2, c3, c4 = st.columns([1, 4, 0.5, 0.5])
    win = c1.selectbox("Window (bars)", [250, 500, 1000], index=1,
                       key=f"{key_prefix}_win_size")
    max_start = max(N - win, 0)
    skey = f"{key_prefix}_slider"
    cur = min(st.session_state.get(skey, 0), max_start)
    if c3.button("◀", key=f"{key_prefix}_prev", width="stretch"):
        cur = max(0, cur - win // 2)
    if c4.button("▶", key=f"{key_prefix}_next", width="stretch"):
        cur = min(max_start, cur + win // 2)
    st.session_state[skey] = cur
    start = c2.slider("Window start (bar)", 0, max(max_start, 1),
                      step=max(win // 4, 1), key=skey)
    return start, min(start + win, N)


def coverage_strip(ws: int, we: int, key: str) -> None:
    """Thin full-series strip: coverage (teal) + current window marker."""
    mask = store.coverage_mask(candles_df["timestamp"]).astype(int)
    fig = go.Figure(go.Heatmap(
        z=[mask], x=candles_df["timestamp"], showscale=False,
        colorscale=[[0, "#eceff1"], [1, "#00897b"]], zmin=0, zmax=1,
        hoverinfo="skip",
    ))
    fig.add_vline(x=candles_df["timestamp"].iloc[ws], line_color="#1565c0", line_width=2)
    fig.add_vline(x=candles_df["timestamp"].iloc[we - 1], line_color="#1565c0", line_width=2)
    fig.update_layout(height=60, margin=dict(l=0, r=0, t=0, b=0),
                      yaxis=dict(visible=False), xaxis=dict(visible=False))
    st.plotly_chart(fig, width="stretch", key=key,
                    config={"displayModeBar": False})


def _labels_in(labels: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    if labels.empty:
        return labels
    lo, hi = w["timestamp"].iloc[0], w["timestamp"].iloc[-1]
    return labels[(labels["timestamp"] >= lo) & (labels["timestamp"] <= hi)]


def add_truth_markers(fig, labels: pd.DataFrame, w: pd.DataFrame,
                      row: int | None = None, col: int | None = None) -> None:
    rc = {"row": row, "col": col} if row is not None else {}
    close_by_ts = dict(zip(w["timestamp"], w["close"]))
    span = max(w["close"].max() - w["close"].min(), 1e-9)
    for kind, color, symbol, dy in (("dip", C_DIP, "triangle-up", -0.04),
                                    ("peak", C_PEAK, "triangle-down", 0.04)):
        pts = labels[labels["kind"] == kind]
        xs = [t for t in pts["timestamp"] if t in close_by_ts]
        if not xs:
            continue
        fig.add_trace(go.Scatter(
            x=xs, y=[close_by_ts[t] + dy * span for t in xs],
            mode="markers", name=f"truth {kind}",
            marker=dict(color=color, symbol=symbol, size=11),
            hovertemplate=f"truth {kind}<br>%{{x}}<extra></extra>",
        ), **rc)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_gen, tab_label, tab_run, tab_train, tab_metrics = st.tabs(
    ["Generate", "Label", "Run & Inspect", "Training view", "Metrics"]
)

# --------------------------- Generate ---------------------------------------
with tab_gen:
    rows = []
    for name in SCENARIOS:
        if scenario_exists(name):
            s = LabelStore(scenario_dir(name))
            df_n = _load_candles(name, _candles_mtime(name))
            lbl = s.load()
            rows.append({
                "scenario": name, "bars": len(df_n),
                "coverage %": round(s.coverage_pct(df_n["timestamp"]), 1),
                "dips": int((lbl["kind"] == "dip").sum()),
                "peaks": int((lbl["kind"] == "peak").sum()),
            })
        else:
            rows.append({"scenario": name, "bars": 0, "coverage %": 0.0,
                         "dips": 0, "peaks": 0})
    st.dataframe(pd.DataFrame(rows).set_index("scenario"), width="stretch")

    prev = go.Figure(go.Scatter(
        x=candles_df["timestamp"][::10], y=candles_df["close"][::10],
        mode="lines", line=dict(color=C_PRICE, width=1), name="close",
    ))
    prev.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0),
                       title=f"{scenario} — full series (downsampled)")
    st.plotly_chart(prev, width="stretch")

# --------------------------- Label ------------------------------------------
with tab_label:
    mode = st.radio("Mode", ["Label dips", "Label peaks", "Delete"],
                    horizontal=True, key="label_mode")
    ws, we = window_nav("label")
    w = candles_df.iloc[ws:we]
    labels = store.load()

    st.caption(
        "**Box-select** snaps a label to the lowest close (dip mode) / highest "
        "close (peak mode) inside the box. **Click** labels the exact bar. "
        "Delete removes the nearest label (±2 bars)."
    )

    if "chart_nonce" not in st.session_state:
        st.session_state["chart_nonce"] = 0

    show_candles = st.toggle("Candlestick view", value=False, key="lbl_candles")
    fig = go.Figure()
    if show_candles:
        fig.add_trace(go.Candlestick(
            x=w["timestamp"], open=w["open"], high=w["high"],
            low=w["low"], close=w["close"], name="price",
        ))
        fig.update_layout(xaxis_rangeslider_visible=False)
    fig.add_trace(go.Scatter(
        x=w["timestamp"], y=w["close"], mode="lines+markers", name="close",
        line=dict(color=C_PRICE, width=1.5), marker=dict(size=3),
    ))
    add_truth_markers(fig, _labels_in(labels, w), w)
    fig.update_layout(height=480, margin=dict(l=0, r=0, t=10, b=0),
                      dragmode="select", showlegend=True)

    event = st.plotly_chart(
        fig, width="stretch", on_select="rerun",
        selection_mode=("points", "box"),
        key=f"label_chart_{scenario}_{ws}_{st.session_state['chart_nonce']}",
    )

    sel_pts = (event or {}).get("selection", {}).get("points", [])
    # only points from the close-line trace (curve carrying full window data)
    sel_ts = [pd.Timestamp(p["x"]) for p in sel_pts if p.get("x") is not None]
    if sel_ts:
        sub = w[w["timestamp"].isin(sel_ts)]
        if not sub.empty:
            if mode == "Label dips":
                store.add(sub.loc[sub["close"].idxmin(), "timestamp"], "dip")
            elif mode == "Label peaks":
                store.add(sub.loc[sub["close"].idxmax(), "timestamp"], "peak")
            else:
                for t in sub["timestamp"]:
                    store.remove_nearest(t, candles_df["timestamp"], tol_bars=2)
        st.session_state["chart_nonce"] += 1
        st.rerun()

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Mark window reviewed", type="primary", width="stretch"):
        store.mark_covered(w["timestamp"].iloc[0], w["timestamp"].iloc[-1])
        st.rerun()
    if b2.button("Un-mark window", width="stretch"):
        store.unmark_covered(w["timestamp"].iloc[0], w["timestamp"].iloc[-1])
        st.rerun()
    if b3.button("Clear window labels", width="stretch"):
        n = store.clear_range(w["timestamp"].iloc[0], w["timestamp"].iloc[-1])
        st.toast(f"Removed {n} labels")
        st.rerun()
    with b4.popover("Pre-seed window"):
        st.write("Seed this window's labels from the generator's noise-free "
                 "extrema, then correct them by hand.")
        if st.button("Seed from generator extrema"):
            n = store.seed_from_true_extrema(
                meta, w["timestamp"].iloc[0], w["timestamp"].iloc[-1])
            st.toast(f"Seeded {n} labels")
            st.rerun()

    coverage_strip(ws, we, key="label_cov_strip")
    lbl_now = store.load()
    st.caption(
        f"Coverage: **{store.coverage_pct(candles_df['timestamp']):.1f}%** of "
        f"{N} bars · labels: **{(lbl_now['kind'] == 'dip').sum()} dips**, "
        f"**{(lbl_now['kind'] == 'peak').sum()} peaks**"
    )

# --------------------------- shared eval helpers -----------------------------

def _run_all() -> dict[str, HarnessResult]:
    mtime = _candles_mtime(scenario)
    return {m: _cached_run(scenario, m, params_json, rule_json, mtime)
            for m in mechanisms}


def _eval_all(results: dict[str, HarnessResult], labels: pd.DataFrame,
              mask: np.ndarray):
    return {m: evaluate_mechanism(r.scores, labels, mask, int(tol_bars),
                                  thr[m][0], thr[m][1])
            for m, r in results.items()}

# --------------------------- Run & Inspect ----------------------------------
def render_run_tab() -> None:
    labels = store.load()
    mask = store.coverage_mask(candles_df["timestamp"])
    results = _run_all()
    evals = _eval_all(results, labels, mask) if not labels.empty else {}

    mech = st.radio("Mechanism", mechanisms, horizontal=True,
                    format_func=MECH_LABELS.get, key="run_mech")
    ws, we = window_nav("run")
    w = candles_df.iloc[ws:we]
    scores = results[mech].scores
    sw = scores.iloc[ws:we]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.65, 0.35], vertical_spacing=0.04)
    fig.add_trace(go.Scatter(
        x=w["timestamp"], y=w["close"], mode="lines", name="close",
        line=dict(color=C_PRICE, width=1.5),
    ), row=1, col=1)
    add_truth_markers(fig, _labels_in(labels, w), w, row=1, col=1)

    # Detection markers coded TP / FP / FN (color + shape)
    if mech in evals:
        ev = evals[mech]
        ts_all = candles_df["timestamp"]
        for side, mr, color in (("dip", ev["dips"], C_DIP), ("peak", ev["peaks"], C_PEAK)):
            tp_i = [p for (_, p) in mr.matched if ws <= p < we]
            fp_i = [p for p in mr.fp_idx if ws <= p < we]
            fn_i = [t for t in mr.fn_idx if ws <= t < we]
            if tp_i:
                fig.add_trace(go.Scatter(
                    x=ts_all.iloc[tp_i], y=candles_df["close"].iloc[tp_i],
                    mode="markers", name=f"TP {side}",
                    marker=dict(color=color, symbol="circle", size=10,
                                line=dict(color="white", width=1)),
                ), row=1, col=1)
            if fp_i:
                fig.add_trace(go.Scatter(
                    x=ts_all.iloc[fp_i], y=candles_df["close"].iloc[fp_i],
                    mode="markers", name=f"FP {side}",
                    marker=dict(color=C_FP, symbol="x", size=10),
                ), row=1, col=1)
            if fn_i:
                fig.add_trace(go.Scatter(
                    x=ts_all.iloc[fn_i], y=candles_df["close"].iloc[fn_i],
                    mode="markers", name=f"missed {side} (FN)",
                    marker=dict(color=C_FN, symbol="circle-open", size=13,
                                line=dict(width=2)),
                ), row=1, col=1)

    # Probability pane — fixed 0..1
    fig.add_trace(go.Scatter(
        x=sw["timestamp"], y=sw["p_min"], mode="lines", name="P(dip)",
        line=dict(color=C_DIP, width=1.5),
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=sw["timestamp"], y=sw["p_max"], mode="lines", name="P(peak)",
        line=dict(color=C_PEAK, width=1.5),
    ), row=2, col=1)
    fig.add_hline(y=thr[mech][0], line_dash="dash", line_color=C_DIP,
                  line_width=1, row=2, col=1,
                  annotation_text=f"dip thr {thr[mech][0]:.2f}")
    fig.add_hline(y=thr[mech][1], line_dash="dash", line_color=C_PEAK,
                  line_width=1, row=2, col=1,
                  annotation_text=f"peak thr {thr[mech][1]:.2f}")
    fig.update_yaxes(range=[0, 1], row=2, col=1, title_text="P")
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", y=1.06))
    st.plotly_chart(fig, width="stretch", key="run_chart")

    if labels.empty:
        st.info("No hand labels yet — detections are shown uncoded. "
                "Label some windows in the **Label** tab to get TP/FP/FN coding.")
    elif not mask.any():
        st.info("Labels exist but no window is marked reviewed — mark coverage "
                "in the Label tab so metrics know which regions are complete.")
    coverage_strip(ws, we, key="run_cov_strip")


with tab_run:
    if not mechanisms:
        st.info("Pick at least one mechanism in the sidebar.")
    else:
        render_run_tab()

# --------------------------- Training view ----------------------------------
with tab_train:
    ml_mechs = [m for m in mechanisms if m != "rsi_rule"]
    if not ml_mechs:
        st.info("Training view needs an ML mechanism (logistic or MLP).")
    else:
        mech = st.radio("Mechanism", ml_mechs, horizontal=True,
                        format_func=MECH_LABELS.get, key="train_mech")
        res = _run_all()[mech]
        if not res.retrains:
            st.warning("No retrains recorded — not enough data past warmup?")
        else:
            k = st.slider("Retrain #", 0, len(res.retrains) - 1,
                          len(res.retrains) - 1, key="retrain_slider")
            snap = res.retrains[k]
            wb = candles_df.iloc[snap.window_start:snap.at_bar + 1]
            at_ts = candles_df["timestamp"].iloc[snap.at_bar]

            st.caption(
                f"Retrain **#{snap.retrain_no}** at bar {snap.at_bar} "
                f"({at_ts}) — training window {snap.window_start}..{snap.at_bar} "
                f"({len(wb)} bars) · samples: **{snap.n_min} dips / {snap.n_max} peaks**"
            )

            figt = go.Figure()
            figt.add_trace(go.Scatter(
                x=wb["timestamp"], y=wb["close"], mode="lines", name="close",
                line=dict(color=C_PRICE, width=1.5),
            ))
            min_i = [gi for gi, c in zip(snap.sample_indices, snap.sample_classes) if c == 0]
            max_i = [gi for gi, c in zip(snap.sample_indices, snap.sample_classes) if c == 1]
            neu_i = [gi for gi, c in zip(snap.sample_indices, snap.sample_classes) if c == 2]
            for idxs, name, color, symbol in (
                (min_i, "labeler: dip sample", C_DIP, "triangle-up"),
                (max_i, "labeler: peak sample", C_PEAK, "triangle-down"),
                (neu_i, "labeler: neutral", C_FN, "circle"),
            ):
                if idxs:
                    figt.add_trace(go.Scatter(
                        x=candles_df["timestamp"].iloc[idxs],
                        y=candles_df["close"].iloc[idxs],
                        mode="markers", name=name,
                        marker=dict(color=color, symbol=symbol, size=10),
                    ))
            # hand truth overlaid for contrast (open markers)
            labels = store.load()
            lbl_w = labels[(labels["timestamp"] >= wb["timestamp"].iloc[0])
                           & (labels["timestamp"] <= wb["timestamp"].iloc[-1])]
            close_by_ts = dict(zip(wb["timestamp"], wb["close"]))
            for kind, color, symbol in (("dip", C_DIP, "triangle-up-open"),
                                        ("peak", C_PEAK, "triangle-down-open")):
                pts = [t for t in lbl_w[lbl_w["kind"] == kind]["timestamp"]
                       if t in close_by_ts]
                if pts:
                    figt.add_trace(go.Scatter(
                        x=pts, y=[close_by_ts[t] for t in pts],
                        mode="markers", name=f"hand truth {kind}",
                        marker=dict(color=color, symbol=symbol, size=15,
                                    line=dict(width=2)),
                    ))
            # NOTE: no annotation_text — plotly's annotation midpoint math breaks
            # on pandas-3.0 Timestamps; the caption above says where the fit is.
            figt.add_vline(x=at_ts, line_dash="dot", line_color="#455a64")
            figt.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0),
                               legend=dict(orientation="h", y=1.08))
            st.plotly_chart(figt, width="stretch", key="train_chart")

            if snap.feature_contribs:
                names = [n for n, _ in snap.feature_contribs]
                vals = [v for _, v in snap.feature_contribs]
                figc = go.Figure(go.Bar(
                    x=vals, y=names, orientation="h",
                    marker_color=[C_DIP if v >= 0 else C_PEAK for v in vals],
                ))
                figc.update_layout(
                    height=260, margin=dict(l=0, r=0, t=30, b=0),
                    title="Feature push toward DIP at this retrain "
                          "(green = toward dip, red = against)",
                )
                st.plotly_chart(figc, width="stretch", key="contrib_chart")

# --------------------------- Metrics ----------------------------------------
with tab_metrics:
    labels = store.load()
    mask = store.coverage_mask(candles_df["timestamp"])
    cov_pct = store.coverage_pct(candles_df["timestamp"])

    if labels.empty or not mask.any():
        st.info("Metrics need hand labels AND reviewed coverage. Use the "
                "**Label** tab: label dips/peaks, then 'Mark window reviewed'.")
        st.stop()
    if not mechanisms:
        st.info("Pick at least one mechanism in the sidebar.")
        st.stop()

    results = _run_all()
    evals = _eval_all(results, labels, mask)

    tpos = truth_positions(labels, candles_df["timestamp"])
    n_dip_cov = sum(1 for i in tpos["dip"] if mask[i])
    n_peak_cov = sum(1 for i in tpos["peak"] if mask[i])
    st.caption(
        f"Coverage: **{cov_pct:.1f}%** of series · truth in coverage: "
        f"**{n_dip_cov} dips / {n_peak_cov} peaks** · tolerance ±{tol_bars} bars. "
        f"All numbers below count ONLY reviewed ranges."
    )

    st.subheader("Detection quality (model predictions vs hand truth)")
    st.dataframe(comparison_table(evals), width="stretch")

    st.subheader("Timing (bars late; negative = early)")
    hcols = st.columns(max(len(mechanisms), 1))
    for col, m in zip(hcols, mechanisms):
        ev = evals[m]
        figh = go.Figure()
        if ev["dips"].lags:
            figh.add_trace(go.Histogram(x=ev["dips"].lags, name="dips",
                                        marker_color=C_DIP, opacity=0.7))
        if ev["peaks"].lags:
            figh.add_trace(go.Histogram(x=ev["peaks"].lags, name="peaks",
                                        marker_color=C_PEAK, opacity=0.7))
        figh.update_layout(barmode="overlay", height=240,
                           margin=dict(l=0, r=0, t=30, b=0),
                           title=MECH_LABELS[m])
        col.plotly_chart(figh, width="stretch", key=f"lag_{m}")

    st.subheader("Label quality (labeler's training labels vs hand truth)")
    st.caption(
        "Stage 1 of the pipeline — **this bounds the model**: a model trained on "
        "wrong labels cannot detect the right extrema, no matter how good it is. "
        "'Offline' runs the labeler once over the full series; 'as-trained' is "
        "the union of samples the walk-forward retrains actually fed the model."
    )
    lq = label_quality(candles_df.to_dict("records"), params, labels, mask, int(tol_bars))
    lq_rows = {"labeler (offline)": lq}
    for m in mechanisms:
        if m == "rsi_rule":
            continue
        lq_rows[f"as-trained ({m})"] = as_trained_label_quality(
            results[m].retrains, N, labels, candles_df["timestamp"], mask, int(tol_bars))
    st.dataframe(comparison_table(lq_rows), width="stretch")

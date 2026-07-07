"""
Backtest Visualization UI

    source .venv/bin/activate
    streamlit run scripts/ui.py

Opens at http://localhost:8501
"""

import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.store import Store

setup(log_dir=config.log_dir, level="ERROR")  # suppress engine noise in UI
logger = get_logger(__name__)

from trader.notifications import telegram
telegram.disable()

# ── page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Backtest",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── cached resources ─────────────────────────────────────────────────────────

@st.cache_resource
def _get_store() -> Store:
    return Store(config.db_path)


@st.cache_resource
def _connect_kite():
    """Returns (kite, symbol_to_token, error_str|None). Cached for the session."""
    try:
        from trader.auth.session import create_kite
        kite = create_kite()
        instruments = kite.instruments("NSE")
        sym2tok = {
            f"NSE:{i['tradingsymbol']}": i["instrument_token"]
            for i in instruments
        }
        return kite, sym2tok, None
    except Exception as exc:
        return None, {}, str(exc)


def _reconnect_kite():
    """Clear cached Kite connection and reload."""
    _connect_kite.clear()
    _get_store.clear()
    _run_signal_probe.clear()
    _read_candles_cached.clear()
    st.rerun()


@st.cache_data(ttl=600, show_spinner=False)
def _read_candles_cached(instrument: str, timeframe: str,
                         from_dt: datetime, to_dt: datetime) -> pd.DataFrame:
    """SQLite candle read, cached — avoids re-querying on every widget interaction
    (each chart click/row select reruns the script). Cleared after a backtest run
    (which may fetch fresh candles) and on Reconnect Kite."""
    return _get_store().read_candles(instrument, timeframe, from_dt, to_dt)


def _cached_instruments(db_path: Path, timeframe: str) -> list[str]:
    """Symbols that have candles in SQLite for the configured timeframe."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT DISTINCT instrument FROM candles WHERE timeframe = ? ORDER BY instrument",
        (timeframe,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


_LIVE_DB_TMP = "/tmp/trader_live_market.db"
_LIVE_SSH_ALIAS = "trader"
_LIVE_DB_REMOTE = "/opt/trader/data/market.db"


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_live_trades() -> tuple[list[dict], str | None]:
    """
    SCP the remote market.db (read-only copy) and reconstruct filled trade pairs
    from the orders table. Returns (pairs, error_string|None).

    Never modifies the remote file — opens local copy in read-only mode.
    """
    try:
        # The trader service runs as the 'trader' OS user; the SSH user ('ubuntu')
        # can't traverse /opt/trader/ directly (dir is 750). Use sudo cat to read
        # the file as root and stream it locally — no remote files are modified.
        result = subprocess.run(
            ["ssh", _LIVE_SSH_ALIAS, f"sudo cat {_LIVE_DB_REMOTE}"],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace").strip()
            return [], f"SSH fetch failed (exit {result.returncode}): {err}"
        with open(_LIVE_DB_TMP, "wb") as fh:
            fh.write(result.stdout)
    except subprocess.TimeoutExpired:
        return [], "SSH timed out after 30 s — EC2 may be unreachable"
    except Exception as exc:
        return [], str(exc)

    try:
        # uri=True + mode=ro ensures we never accidentally write to the copy
        conn = sqlite3.connect(f"file:{_LIVE_DB_TMP}?mode=ro", uri=True)
        rows = conn.execute(
            """
            SELECT instrument, direction, quantity, price, updated_at
            FROM orders
            WHERE status = 'COMPLETE' AND mode = 'live'
              AND price IS NOT NULL AND price > 0
            ORDER BY updated_at ASC
            """
        ).fetchall()
        conn.close()
    except Exception as exc:
        return [], f"DB read error: {exc}"

    # Reconstruct entry/exit pairs FIFO per instrument
    from collections import defaultdict
    open_buys: dict[str, list[dict]] = defaultdict(list)
    pairs: list[dict] = []
    for inst, direction, qty, price, ts in rows:
        if direction == "BUY":
            open_buys[inst].append({
                "instrument": inst,
                "entry": price,
                "entry_date": pd.Timestamp(ts),
                "qty": qty,
            })
        elif direction == "SELL" and open_buys[inst]:
            buy = open_buys[inst].pop(0)
            pairs.append({
                **buy,
                "exit": price,
                "exit_date": pd.Timestamp(ts),
                "pnl": (price - buy["entry"]) * buy["qty"],
            })

    return pairs, None


@st.cache_data(show_spinner=False)
def _run_signal_probe(_store, instrument: str, strategy_tf: str, params_json: str,
                      from_dt_str: str, to_dt_str: str, warmup_days: int) -> list[dict]:
    """Evaluate model probabilities on every strategy-TF bar without touching
    position state.

    Bypasses on_candle entirely to avoid _entry_price getting stuck after the first
    signal. Directly manages candle accumulation and retraining, then calls the model
    on every bar and logs threshold crossings within [from_dt, to_dt].

    Params and strategy_tf come from config (per-stock merged); base 15m candles
    are aggregated through the same CandleAggregator the engine and live use, so
    a day/4hour stock is probed on the exact bars its model actually sees.
    """
    import json
    from trader.data.aggregator import CandleAggregator
    from trader.strategies.lr_extrema import LRExtremaStrategy

    params = json.loads(params_json)
    from_dt = datetime.fromisoformat(from_dt_str)
    to_dt   = datetime.fromisoformat(to_dt_str)
    probe_from = from_dt - timedelta(days=warmup_days)

    df = _store.read_candles(instrument, config.candle_timeframe, probe_from, to_dt)
    if df.empty:
        return []

    agg = (CandleAggregator(strategy_tf)
           if strategy_tf != config.candle_timeframe else None)
    strategy = LRExtremaStrategy(instrument, params)
    candles_since_train = 0
    results = []

    for _, row in df.iterrows():
        candle = row.to_dict()
        if agg is not None:
            candle = agg.add(candle)
            if candle is None:
                continue
        strategy._candles.append(candle)
        candles_since_train += 1

        if len(strategy._candles) < strategy._warmup_bars:
            continue

        if not strategy._model.is_trained or candles_since_train >= strategy._retrain_every:
            strategy._train()
            candles_since_train = 0

        if not strategy._model.is_trained:
            continue

        ts = candle.get("timestamp")
        if ts is None:
            continue
        try:
            ts_cmp = pd.Timestamp(ts)
            if ts_cmp.tzinfo:
                ts_cmp = ts_cmp.tz_localize(None)
        except Exception:
            continue

        if ts_cmp < from_dt:
            continue
        if ts_cmp > to_dt:
            break

        x = strategy._features.compute(list(strategy._candles))
        if x is None:
            continue

        p_min, p_max = strategy._model.predict_proba(x)

        is_min = p_min >= strategy._threshold
        is_max = p_max >= strategy._sell_threshold

        if not is_min and not is_max:
            continue

        if is_min and p_max >= strategy._veto_threshold:
            sig_type = "VETOED"
        elif is_min:
            sig_type = "ENTRY"
        else:
            sig_type = "PATTERN_TOP"

        results.append({
            "timestamp": ts,
            "close": candle.get("close"),
            "p_min": p_min,
            "p_max": p_max,
            "type": sig_type,
        })

    return results


# ── sidebar ───────────────────────────────────────────────────────────────────

store = _get_store()

with st.sidebar:
    st.title("Backtest")

    today = date.today()
    c1, c2 = st.columns(2)
    from_date = c1.date_input("From", value=today - timedelta(days=90))
    to_date = c2.date_input("To", value=today)

    kite, sym2tok, kite_err = _connect_kite()

    if kite_err:
        st.warning(f"Cache-only mode (Kite auth failed).\n\n`{kite_err}`")
        available = _cached_instruments(config.db_path, config.candle_timeframe)
        # In cache-only mode intersect watchlist with what's actually cached
        default_instruments = [s for s in config.watchlist if s in available]
    else:
        st.success("Kite connected")
        # Filter falsy entries — a dangling "- " in the YAML list yields None
        available = [s for s in config.watchlist if s]
        default_instruments = available

    col_reconnect, _ = st.columns([1, 2])
    if col_reconnect.button("Reconnect Kite", use_container_width=True):
        _reconnect_kite()

    selected_instruments = st.multiselect(
        "Instruments",
        options=available,
        default=default_instruments,
        key="instruments_" + "_".join(sorted(default_instruments)),
    )

    # No param overrides in the UI — config/config.yaml is the source of truth.
    # The run uses global strategies.lr_extrema deep-merged with per_stock_params
    # (incl. per-stock timeframe), exactly like backtest.py.
    with st.expander("Strategy params (read-only, from config)", expanded=False):
        st.caption(
            "Params come from `config/config.yaml` — global `strategies.lr_extrema` "
            "merged with `per_stock_params`. Edit the YAML and rerun to change them."
        )
        _tf_rows = [
            {"Instrument": s, "Timeframe": config.strategy_timeframe(s)}
            for s in config.watchlist if s
        ]
        st.dataframe(pd.DataFrame(_tf_rows), hide_index=True,
                     use_container_width=True, height=240)

    run_clicked = st.button(
        "Run Backtest",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    load_live = st.checkbox("Overlay live trades (EC2)", value=False, key="load_live")
    if load_live:
        col_refresh, _ = st.columns([1, 2])
        if col_refresh.button("Refresh live data", use_container_width=True):
            _fetch_live_trades.clear()
            st.rerun()

# ── run backtest ──────────────────────────────────────────────────────────────

if run_clicked:
    if not selected_instruments:
        st.error("Select at least one instrument.")
        st.stop()

    # Mirror backtest.py exactly: global config params + per-stock deep-merged
    # overrides (incl. aggregated timeframes). No UI-side param mutation.
    params = config.strategy_config("lr_extrema")
    _stock_overrides = (config._data.get("per_stock_params") or {})
    per_symbol_params = {
        sym: config.get_strategy_params(sym, "lr_extrema")
        for sym in selected_instruments
        if _stock_overrides.get(sym, {}).get("lr_extrema")
    } or None
    from_dt = datetime.combine(from_date, datetime.min.time())
    to_dt   = datetime.combine(to_date,   datetime.min.time()).replace(hour=23, minute=59)

    if kite:
        s2t = {s: sym2tok[s] for s in selected_instruments if s in sym2tok}
    else:
        # Dummy tokens — get_candles will serve from cache if candles exist
        s2t = {s: 0 for s in selected_instruments}

    _progress_bar = st.progress(0.0, text="Starting…")

    def _on_progress(current_date, pct):
        _progress_bar.progress(pct, text=f"Processing {current_date}  ({pct*100:.0f}%)")

    with st.spinner("Running backtest…"):
        try:
            trades = run_backtest(kite, store, selected_instruments, s2t, params, from_dt, to_dt,
                                  progress_callback=_on_progress,
                                  per_symbol_params=per_symbol_params)
            _progress_bar.progress(1.0, text="Done")
            _read_candles_cached.clear()  # run may have fetched fresh candles
            st.session_state["trades"]      = trades
            st.session_state["from_dt"]     = from_dt
            st.session_state["to_dt"]       = to_dt
            st.session_state["instruments"] = selected_instruments
        except Exception as exc:
            st.error(f"Backtest failed: {exc}")
        finally:
            _progress_bar.empty()
    st.rerun()

# ── pull state ────────────────────────────────────────────────────────────────

trades: list[dict]      = st.session_state.get("trades", [])
from_dt: datetime       = st.session_state.get("from_dt", datetime(2025, 1, 1))
to_dt: datetime         = st.session_state.get("to_dt",   datetime.now())
bt_instruments: list    = st.session_state.get("instruments", [])

# ── tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["Portfolio", "Stock Chart", "Trade Breakdown"])


# ════════════════════════════════════════════════════════════════════════════
# Tab 1 — Portfolio overview
# ════════════════════════════════════════════════════════════════════════════

with tab1:
    if not trades:
        st.info("Configure dates and instruments in the sidebar, then click **Run Backtest**.")
        st.stop()

    metrics = compute_metrics(trades, config.total_capital)

    # Metric cards
    cols = st.columns(8)
    cols[0].metric("Trades",   metrics["total_trades"])
    cols[1].metric("Wt. Win%", f"{metrics['money_weighted_win_rate']:.1f}%")
    cols[2].metric("Net P&L",  f"₹{metrics['total_pnl']:,.0f}")
    cols[3].metric("Return",   f"{metrics['return_pct']:.2f}%")
    cols[4].metric("Max DD",   f"₹{metrics['max_drawdown']:,.0f}", delta=f"{metrics['max_drawdown_pct']:.2f}%", delta_color="inverse")
    cols[5].metric("Avg Win",  f"₹{metrics['avg_win']:,.0f}")
    cols[6].metric("Avg Loss", f"₹{metrics['avg_loss']:,.0f}")
    cols[7].metric("Sharpe*",  f"{metrics['sharpe_proxy']:.2f}")

    cols2 = st.columns(4)
    cols2[0].metric("Sortino",        f"{metrics['sortino_ratio']:.2f}")
    cols2[1].metric("Calmar",         f"{metrics['calmar_ratio']:.2f}")
    cols2[2].metric("Profit Factor",  f"{metrics['profit_factor']:.2f}")
    cols2[3].metric("Win Rate",       f"{metrics['win_rate']:.1f}%")

    st.divider()

    df_t = pd.DataFrame(trades).sort_values("entry_date").reset_index(drop=True)
    df_t["cum_pnl"] = df_t["pnl"].cumsum()
    # Compute Capital on df_t so Tab 2's df_inst (derived from df_t) also has it
    df_t["Capital"] = config.total_capital + df_t["pnl"].cumsum().shift(1, fill_value=0)


# Fragment: chart box-select / point-click / row-select interactions rerun only
# this block instead of the whole script (a full rerun rebuilds Tab 2's
# candlestick figure — the expensive part). Row selection still calls
# st.rerun() (app scope) so the highlight syncs to the Tab 2 chart.
@st.fragment
def _render_tab1_trades():
    # ── equity curve ──
    # Build a continuous step so the curve shows drawdown between trades too
    xs = df_t["entry_date"].tolist()
    ys = df_t["cum_pnl"].tolist()

    # Identify drops in cumulative P&L (identifying specific loss events)
    point_colors = []
    for i in range(len(ys)):
        if i == 0:
            # First point is green if it's a win, red if it's a loss
            color = "#2ecc71" if ys[i] >= 0 else "#e74c3c"
        else:
            # Red if cumulative sum reduced compared to previous point
            color = "#e74c3c" if ys[i] < ys[i-1] else "#2ecc71"
        point_colors.append(color)

    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="lines+markers",
        line=dict(width=2, color="#3498db"),
        marker=dict(size=6, color=point_colors),
        name="Cum. P&L",
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br><b>₹%{y:,.0f}</b><extra></extra>",
    ))
    fig_eq.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1)

    # Highlight selected trade on equity curve (from table row selection)
    _hl = st.session_state.get("_hl_trade")
    if _hl:
        _hl_rows = df_t[df_t["entry_date"].astype(str).str[:19] == _hl.get("entry", "")]
        if not _hl_rows.empty:
            fig_eq.add_trace(go.Scatter(
                x=[_hl_rows["entry_date"].iloc[0]],
                y=[_hl_rows["cum_pnl"].iloc[0]],
                mode="markers",
                marker=dict(symbol="circle-open", size=20, color="#f1c40f",
                            line=dict(width=3, color="#f1c40f")),
                showlegend=False,
                hoverinfo="skip",
            ))

    fig_eq.update_layout(
        title="Equity Curve — Drag to select range (filters table) · Click dot to highlight row",
        xaxis_title="Date",
        yaxis_title="₹",
        height=340,
        margin=dict(l=10, r=10, t=45, b=10),
        hovermode="x unified",
        dragmode="select",
    )
    eq_event = st.plotly_chart(
        fig_eq, on_select="rerun",
        selection_mode=["points", "box"],
        width="stretch",
    )

    # Box selection → date range filter; lone point click → row highlight
    try:
        _eq_box = eq_event.selection.box or []
        _eq_pts = eq_event.selection.points or []
    except AttributeError:
        _eq_box, _eq_pts = [], []
    eq_date_start = eq_date_end = None
    eq_highlight_ts = None
    if _eq_box:
        _bx = _eq_box[0].get("x", [])
        if len(_bx) >= 2:
            try:
                eq_date_start = pd.Timestamp(min(_bx))
                eq_date_end = pd.Timestamp(max(_bx))
            except Exception:
                pass
    elif _eq_pts:
        try:
            eq_highlight_ts = str(pd.Timestamp(str(_eq_pts[0].get("x", ""))))[:19]
        except Exception:
            pass

    # ── monthly returns chart ──
    _mr = metrics.get("monthly_returns", {})
    if _mr:
        _mr_months = list(_mr.keys())
        _mr_pnls   = [_mr[m]["pnl"] for m in _mr_months]
        _mr_colors = ["#2ecc71" if p >= 0 else "#e74c3c" for p in _mr_pnls]
        fig_monthly = go.Figure(go.Bar(
            x=_mr_months,
            y=_mr_pnls,
            marker_color=_mr_colors,
            hovertemplate="%{x}<br><b>₹%{y:,.0f}</b><extra></extra>",
        ))
        fig_monthly.update_layout(
            title="Monthly P&L",
            xaxis_title="Month",
            yaxis_title="₹",
            height=220,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        fig_monthly.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1)
        st.plotly_chart(fig_monthly, use_container_width=True)

    # ── trade table ──
    st.subheader("Trades")

    def _hold_days(row):
        try:
            return (pd.Timestamp(row["exit_date"]) - pd.Timestamp(row["entry_date"])).days
        except Exception:
            return 0

    def _pnl_pct(row):
        invested = row["entry"] * row["qty"]
        return row["pnl"] / invested * 100 if invested else 0.0

    df_display = df_t.copy()
    df_display["Hold (d)"] = df_t.apply(_hold_days, axis=1)
    df_display["Candles"]  = df_t["held_candles"].fillna(0).astype(int) if "held_candles" in df_t.columns else 0
    df_display["P&L%"] = df_t.apply(_pnl_pct, axis=1)
    df_display["entry_date"] = df_display["entry_date"].astype(str).str[:19]
    df_display["exit_date"]  = df_display["exit_date"].astype(str).str[:19]

    df_display = df_display[[
        "entry_date", "exit_date", "Hold (d)", "Candles", "instrument",
        "entry", "exit", "qty", "cost", "pnl", "P&L%", "Capital", "product", "reason",
    ]].rename(columns={
        "entry_date": "Entry",
        "exit_date":  "Exit",
        "instrument": "Instrument",
        "entry": "Entry ₹",
        "exit":  "Exit ₹",
        "qty":   "Qty",
        "cost":  "Cost",
        "pnl":   "P&L",
        "product": "Product",
        "reason":  "Reason",
    })

    # Apply date filter from box selection
    df_show = df_display
    if eq_date_start and eq_date_end:
        df_show = df_display[
            (pd.to_datetime(df_display["Entry"]) >= eq_date_start) &
            (pd.to_datetime(df_display["Entry"]) <= eq_date_end)
        ]

    # Apply row highlight from point click
    if eq_highlight_ts:
        def _eq_hl(row):
            return (
                ["background-color: rgba(52,152,219,0.25)"] * len(row)
                if row["Entry"] == eq_highlight_ts else [""] * len(row)
            )
        df_show = df_show.style.apply(_eq_hl, axis=1)

    _col_cfg = {
        "Entry ₹": st.column_config.NumberColumn(format="₹%.2f"),
        "Exit ₹":  st.column_config.NumberColumn(format="₹%.2f"),
        "Cost":    st.column_config.NumberColumn(format="₹%.2f"),
        "P&L":     st.column_config.NumberColumn(format="₹%.0f"),
        "P&L%":    st.column_config.NumberColumn(format="%.2f%%"),
        "Capital": st.column_config.NumberColumn(format="₹%.0f"),
    }
    _t1_event = st.dataframe(df_show, use_container_width=True, height=420,
                             column_config=_col_cfg, hide_index=True,
                             on_select="rerun", selection_mode="single-row")
    _t1_rows = getattr(getattr(_t1_event, "selection", None), "rows", []) or []
    if _t1_rows:
        _actual = df_show.data if hasattr(df_show, "data") else df_show
        _sel = _actual.iloc[_t1_rows[0]]
        _new_hl = {
            "entry": str(_sel.get("Entry", ""))[:19],
            "exit":  str(_sel.get("Exit",  ""))[:19],
            "inst":  str(_sel.get("Instrument", "")),
        }
        if st.session_state.get("_hl_trade") != _new_hl:
            st.session_state["_hl_trade"] = _new_hl
            st.rerun()


with tab1:
    _render_tab1_trades()


# ════════════════════════════════════════════════════════════════════════════
# Tab 2 — Stock Chart
# ════════════════════════════════════════════════════════════════════════════

# Fragment: instrument switch, signal toggle, chart clicks and row selects rerun
# only this block — the candlestick rebuild no longer drags Tab 1/3 along.
@st.fragment
def _render_tab2():
    instruments_with_trades = sorted({t["instrument"] for t in trades}) if trades else []
    chart_options = sorted(set(instruments_with_trades + bt_instruments))

    if not chart_options:
        st.info("Run a backtest first to populate the chart.")
        return

    # Fixed persistent selection index
    current_inst_stored = st.session_state.get("selected_inst_chart", chart_options[0])
    try:
        default_idx = chart_options.index(current_inst_stored)
    except ValueError:
        default_idx = 0

    selected_inst = st.selectbox(
        "Instrument",
        chart_options,
        index=default_idx,
        key="chart_inst_selector"
    )
    st.session_state["selected_inst_chart"] = selected_inst
    st.caption(f"Strategy timeframe: **{config.strategy_timeframe(selected_inst)}** "
               "(chart candles stay 15m)")

    show_signals = st.checkbox(
        "Show model signals",
        value=False,
        help=(
            "Overlay every candle where the model crossed a threshold:\n"
            "🟢 ENTRY — P(min)≥threshold, all filters passed\n"
            "🟠 BLOCKED — P(min)≥threshold, hard filter blocked\n"
            "🟡 VETOED — P(min)≥threshold but P(max)≥veto\n"
            "🟣 PATTERN TOP — P(max)≥sell_threshold (in position)"
        ),
    )

    df_candles = _read_candles_cached(selected_inst, config.candle_timeframe, from_dt, to_dt)

    if df_candles.empty:
        st.warning(f"No candles cached for **{selected_inst}** in this range. "
                   "Run a backtest with Kite connected to fetch and cache candles.")
        return

    # Display-only downsample: long ranges make the 15m candlestick payload huge
    # and the browser re-renders it on every interaction. Trades, signals and
    # tables keep full-resolution data — only the plotted OHLCV is coarsened.
    _span_days = (to_dt - from_dt).days
    if _span_days > 365:
        _ds_rule, _ds_label = "1D", "daily"
    elif _span_days > 90:
        _ds_rule, _ds_label = "60min", "hourly"
    else:
        _ds_rule, _ds_label = None, None
    if _ds_rule:
        df_plot = (
            df_candles.set_index("timestamp")
            .resample(_ds_rule, offset="15min" if _ds_rule == "60min" else None)
            .agg({"open": "first", "high": "max", "low": "min",
                  "close": "last", "volume": "sum"})
            .dropna(subset=["open"])
            .reset_index()
        )
        st.caption(f"Chart downsampled to {_ds_label} bars for display "
                   f"({_span_days}-day range) — trades, signals and tables use full 15m data.")
    else:
        df_plot = df_candles

    _signal_log: list[dict] = []
    if show_signals:
        import json
        # Config is the source of truth — per-stock merged params + timeframe,
        # matching what the backtest run itself used.
        _probe_params = config.get_strategy_params(selected_inst, "lr_extrema")
        _probe_tf = config.strategy_timeframe(selected_inst)
        with st.spinner("Computing model signals…"):
            _signal_log = _run_signal_probe(
                store, selected_inst, _probe_tf,
                json.dumps(_probe_params, sort_keys=True),
                from_dt.isoformat(), to_dt.isoformat(),
                config.warmup_days_for(selected_inst),
            )
        _sig_counts = {t: sum(1 for e in _signal_log if e["type"] == t)
                       for t in ("ENTRY", "BLOCKED", "VETOED", "PATTERN_TOP")}
        st.caption(f"Signals found: {len(_signal_log)} — "
                   + "  ".join(f"{t}:{n}" for t, n in _sig_counts.items() if n)
                   or "none")

    inst_trades = [t for t in trades if t["instrument"] == selected_inst]

    # Per-stock summary metrics
    if inst_trades:
        im = compute_metrics(inst_trades, config.total_capital)
        mc = st.columns(8)
        mc[0].metric("Trades",        im["total_trades"])
        mc[1].metric("Wt. Win%",      f"{im['money_weighted_win_rate']:.1f}%")
        mc[2].metric("Net P&L",       f"₹{im['total_pnl']:,.0f}")
        mc[3].metric("Return",        f"{im['return_pct']:.2f}%")
        mc[4].metric("Max DD",        f"₹{im['max_drawdown']:,.0f}", delta=f"{im['max_drawdown_pct']:.2f}%", delta_color="inverse")
        mc[5].metric("Avg Win",       f"₹{im['avg_win']:,.0f}")
        mc[6].metric("Avg Loss",      f"₹{im['avg_loss']:,.0f}")
        mc[7].metric("Sharpe*",       f"{im['sharpe_proxy']:.2f}")
        mc2 = st.columns(4)
        mc2[0].metric("Sortino",       f"{im['sortino_ratio']:.2f}")
        mc2[1].metric("Calmar",        f"{im['calmar_ratio']:.2f}")
        mc2[2].metric("Profit Factor", f"{im['profit_factor']:.2f}")
        mc2[3].metric("Win Rate",      f"{im['win_rate']:.1f}%")
        st.divider()

    # Build subplots: price | volume | (per-stock equity if trades exist)
    n_rows = 3 if inst_trades else 2
    row_heights = [0.55, 0.20, 0.25] if n_rows == 3 else [0.75, 0.25]
    subtitles   = ["Price", "Volume", "Cumulative P&L"] if n_rows == 3 else ["Price", "Volume"]

    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.04,
        subplot_titles=subtitles,
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df_plot["timestamp"],
        open=df_plot["open"],
        high=df_plot["high"],
        low=df_plot["low"],
        close=df_plot["close"],
        name="OHLC",
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
        increasing_fillcolor="#2ecc71",
        decreasing_fillcolor="#e74c3c",
    ), row=1, col=1)

    # Volume bars (colored by direction)
    vol_colors = [
        "#2ecc71" if c >= o else "#e74c3c"
        for o, c in zip(df_plot["open"], df_plot["close"])
    ]
    fig.add_trace(go.Bar(
        x=df_plot["timestamp"],
        y=df_plot["volume"],
        name="Volume",
        marker_color=vol_colors,
        showlegend=False,
    ), row=2, col=1)

    # Entry / exit markers
    if inst_trades:
        df_it = pd.DataFrame(inst_trades).sort_values("entry_date")

        fig.add_trace(go.Scatter(
            x=df_it["entry_date"],
            y=df_it["entry"],
            mode="markers",
            name="Entry",
            marker=dict(symbol="triangle-up", size=14, color="#27ae60",
                        line=dict(width=1, color="#1a5e33")),
            hovertemplate="<b>ENTRY</b><br>%{x|%Y-%m-%d %H:%M}<br>₹%{y:.2f}<extra></extra>",
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df_it["exit_date"],
            y=df_it["exit"],
            mode="markers",
            name="Exit",
            marker=dict(symbol="triangle-down", size=14, color="#e74c3c",
                        line=dict(width=1, color="#922b21")),
            customdata=list(zip(df_it["pnl"], df_it["reason"])),
            hovertemplate=(
                "<b>EXIT</b> (%{customdata[1]})<br>"
                "%{x|%Y-%m-%d %H:%M}<br>"
                "₹%{y:.2f}<br>"
                "P&L: ₹%{customdata[0]:,.0f}<extra></extra>"
            ),
        ), row=1, col=1)

        # Per-stock equity curve
        df_it["cum_pnl"] = df_it["pnl"].cumsum()
        
        # Fixed: delta-based coloring for stock-specific chart dots
        inst_pt_colors = []
        for j in range(len(df_it)):
            if j == 0:
                c = "#2ecc71" if df_it["cum_pnl"].iloc[j] >= 0 else "#e74c3c"
            else:
                # Red if the cumulative P&L decreased due to the current trade
                c = "#e74c3c" if df_it["cum_pnl"].iloc[j] < df_it["cum_pnl"].iloc[j-1] else "#2ecc71"
            inst_pt_colors.append(c)

        fig.add_trace(go.Scatter(
            x=df_it["entry_date"],
            y=df_it["cum_pnl"],
            mode="lines+markers",
            name="Stock P&L",
            line=dict(color="#3498db", width=2),
            marker=dict(size=7, color=inst_pt_colors),
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>₹%{y:,.0f}<extra></extra>",
        ), row=3, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)",
                      line_width=1, row=3, col=1)

        # Highlight selected trade entry/exit on chart (from table row selection)
        _hl = st.session_state.get("_hl_trade")
        if _hl and _hl.get("inst") == selected_inst:
            _hl_rows = df_it[df_it["entry_date"].astype(str).str[:19] == _hl.get("entry", "")]
            if not _hl_rows.empty:
                _hr = _hl_rows.iloc[0]
                fig.add_trace(go.Scatter(
                    x=[_hr["entry_date"], _hr["exit_date"]],
                    y=[_hr["entry"],      _hr["exit"]],
                    mode="markers",
                    marker=dict(symbol="circle-open", size=22, color="#f1c40f",
                                line=dict(width=3, color="#f1c40f")),
                    name="Selected",
                    showlegend=False,
                    hoverinfo="skip",
                ), row=1, col=1)

    # ── model signal overlay ──
    if _signal_log:
        _sig_style = {
            "ENTRY":       ("#27ae60", "circle",      "Model: Local Min (entry)"),
            "VETOED":      ("#f1c40f", "circle-open", "Model: Local Min (vetoed)"),
            "PATTERN_TOP": ("#9b59b6", "diamond",     "Model: Local Max (top)"),
        }
        for sig_type, (color, symbol, label) in _sig_style.items():
            pts = [e for e in _signal_log if e["type"] == sig_type]
            if not pts:
                continue
            fig.add_trace(go.Scatter(
                x=[e["timestamp"] for e in pts],
                y=[e["close"] for e in pts],
                mode="markers",
                name=label,
                marker=dict(symbol=symbol, size=9, color=color, opacity=0.85,
                            line=dict(width=1, color="rgba(0,0,0,0.4)")),
                customdata=[[e["p_min"], e["p_max"]] for e in pts],
                hovertemplate=(
                    f"<b>{label}</b><br>"
                    "%{x|%Y-%m-%d %H:%M}<br>₹%{y:.2f}<br>"
                    "P(min)=%{customdata[0]:.3f}  P(max)=%{customdata[1]:.3f}"
                    "<extra></extra>"
                ),
            ), row=1, col=1)

    # ── live trades overlay ──
    if st.session_state.get("load_live", False):
        with st.spinner("Fetching live trades from EC2…"):
            live_pairs, live_err = _fetch_live_trades()
        if live_err:
            st.warning(
                f"Could not load live trades from EC2:\n\n`{live_err}`\n\n"
                "Please confirm EC2 is reachable and the `trader` SSH alias is "
                "configured, then click **Refresh live data** in the sidebar."
            )
        else:
            inst_live = [
                p for p in live_pairs
                if p["instrument"] == selected_inst
                and from_dt <= p["entry_date"] <= to_dt
            ]
            if inst_live:
                df_lv = pd.DataFrame(inst_live)
                fig.add_trace(go.Scatter(
                    x=df_lv["entry_date"],
                    y=df_lv["entry"],
                    mode="markers",
                    name="Live Entry",
                    marker=dict(symbol="diamond", size=13, color="#f1c40f",
                                line=dict(width=1, color="#9a7d0a")),
                    hovertemplate="<b>LIVE ENTRY</b><br>%{x|%Y-%m-%d %H:%M}<br>₹%{y:.2f}<extra></extra>",
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=df_lv["exit_date"],
                    y=df_lv["exit"],
                    mode="markers",
                    name="Live Exit",
                    marker=dict(symbol="diamond-open", size=13, color="#e67e22",
                                line=dict(width=2, color="#e67e22")),
                    customdata=list(zip(df_lv["pnl"], df_lv["qty"])),
                    hovertemplate=(
                        "<b>LIVE EXIT</b><br>"
                        "%{x|%Y-%m-%d %H:%M}<br>"
                        "₹%{y:.2f}<br>P&L: ₹%{customdata[0]:,.0f}<extra></extra>"
                    ),
                ), row=1, col=1)

    fig.update_layout(
        height=700,
        margin=dict(l=10, r=10, t=60, b=10),
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
    )

    # Hide non-market hours and weekends so candles don't span 24 h.
    # Skip the hour break when bars were downsampled to daily — those are
    # stamped at midnight, which the hour break would hide entirely.
    _rangebreaks = [dict(bounds=["sat", "mon"])]
    if config.candle_timeframe != "day" and _ds_rule != "1D":
        _rangebreaks.append(dict(bounds=[15.5, 9.25], pattern="hour"))
    fig.update_xaxes(rangebreaks=_rangebreaks, rangeslider_visible=False)

    fig.update_yaxes(title_text="₹",   row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1)
    if inst_trades:
        fig.update_yaxes(title_text="P&L ₹", row=3, col=1)

    chart_event = st.plotly_chart(
        fig, on_select="rerun",
        selection_mode=["points", "box"],
        width="stretch",
    )

    # Process chart selection: point click on entry (curve 2) / exit (curve 3) markers
    # Box selection → date range filter for the table below.
    try:
        _ch_box = chart_event.selection.box or []
        _ch_pts = chart_event.selection.points or []
    except AttributeError:
        _ch_box, _ch_pts = [], []
    ch_date_start = ch_date_end = None
    ch_hl_entry = ch_hl_exit = None
    if _ch_box:
        _bx = _ch_box[0].get("x", [])
        if len(_bx) >= 2:
            try:
                ch_date_start = pd.Timestamp(min(_bx))
                ch_date_end = pd.Timestamp(max(_bx))
            except Exception:
                pass
    if _ch_pts:
        pt = _ch_pts[0]
        cn = pt.get("curve_number", -1)
        try:
            norm_x = str(pd.Timestamp(str(pt.get("x", ""))))[:19]
        except Exception:
            norm_x = None
        if norm_x:
            if cn == 2:    # Entry markers
                ch_hl_entry = norm_x
            elif cn == 3:  # Exit markers
                ch_hl_exit = norm_x

    # ── Filtered Trade Table for Selected Instrument ──
    if inst_trades:
        st.subheader(f"Trades: {selected_inst}")

        def _fmt_pnl_pct(row):
            invested = row["entry"] * row["qty"]
            return row["pnl"] / invested * 100 if invested else 0.0

        # Use df_t (which has portfolio-level Capital already computed) for this stock
        df_inst = df_t[df_t["instrument"] == selected_inst].sort_values("entry_date", ascending=False).copy()
        df_inst["P&L%"] = df_inst.apply(_fmt_pnl_pct, axis=1)
        df_inst["Entry"] = df_inst["entry_date"].astype(str).str[:19]
        df_inst["Exit"] = df_inst["exit_date"].astype(str).str[:19]

        df_inst_display = df_inst[[
            "Entry", "Exit", "entry", "exit", "qty", "pnl", "P&L%", "Capital", "reason"
        ]].rename(columns={
            "entry": "Entry ₹",
            "exit": "Exit ₹",
            "qty": "Qty",
            "pnl": "P&L",
            "reason": "Reason"
        })

        # Apply date filter from box selection
        df_inst_show = df_inst_display
        if ch_date_start and ch_date_end:
            df_inst_show = df_inst_display[
                (pd.to_datetime(df_inst_display["Entry"]) >= ch_date_start) &
                (pd.to_datetime(df_inst_display["Entry"]) <= ch_date_end)
            ]

        # Apply row highlight from marker click
        if ch_hl_entry or ch_hl_exit:
            def _ch_hl(row):
                if ch_hl_entry and row["Entry"] == ch_hl_entry:
                    return ["background-color: rgba(52,152,219,0.25)"] * len(row)
                if ch_hl_exit and row["Exit"] == ch_hl_exit:
                    return ["background-color: rgba(52,152,219,0.25)"] * len(row)
                return [""] * len(row)
            df_inst_show = df_inst_show.style.apply(_ch_hl, axis=1)

        _inst_col_cfg = {
            "Entry ₹": st.column_config.NumberColumn(format="₹%.2f"),
            "Exit ₹": st.column_config.NumberColumn(format="₹%.2f"),
            "P&L": st.column_config.NumberColumn(format="₹%.0f"),
            "P&L%": st.column_config.NumberColumn(format="%.2f%%"),
            "Capital": st.column_config.NumberColumn(format="₹%.0f"),
        }
        _t2_event = st.dataframe(df_inst_show, use_container_width=True,
                                 column_config=_inst_col_cfg, hide_index=True,
                                 on_select="rerun", selection_mode="single-row")
        _t2_rows = getattr(getattr(_t2_event, "selection", None), "rows", []) or []
        if _t2_rows:
            _actual = df_inst_show.data if hasattr(df_inst_show, "data") else df_inst_show
            _sel = _actual.iloc[_t2_rows[0]]
            _new_hl = {
                "entry": str(_sel.get("Entry", ""))[:19],
                "exit":  str(_sel.get("Exit",  ""))[:19],
                "inst":  selected_inst,
            }
            if st.session_state.get("_hl_trade") != _new_hl:
                st.session_state["_hl_trade"] = _new_hl
                st.rerun()


with tab2:
    _render_tab2()


# ════════════════════════════════════════════════════════════════════════════
# Tab 3 — Trade breakdown
# ════════════════════════════════════════════════════════════════════════════

with tab3:
    if not trades:
        st.info("Run a backtest first.")
        st.stop()

    cols = st.columns(8)
    cols[0].metric("Trades",   metrics["total_trades"])
    cols[1].metric("Wt. Win%", f"{metrics['money_weighted_win_rate']:.1f}%")
    cols[2].metric("Net P&L",  f"₹{metrics['total_pnl']:,.0f}")
    cols[3].metric("Return",   f"{metrics['return_pct']:.2f}%")
    cols[4].metric("Max DD",   f"₹{metrics['max_drawdown']:,.0f}", delta=f"{metrics['max_drawdown_pct']:.2f}%", delta_color="inverse")
    cols[5].metric("Avg Win",  f"₹{metrics['avg_win']:,.0f}")
    cols[6].metric("Avg Loss", f"₹{metrics['avg_loss']:,.0f}")
    cols[7].metric("Sharpe*",  f"{metrics['sharpe_proxy']:.2f}")

    cols2 = st.columns(4)
    cols2[0].metric("Sortino",        f"{metrics['sortino_ratio']:.2f}")
    cols2[1].metric("Calmar",         f"{metrics['calmar_ratio']:.2f}")
    cols2[2].metric("Profit Factor",  f"{metrics['profit_factor']:.2f}")
    cols2[3].metric("Win Rate",       f"{metrics['win_rate']:.1f}%")

    st.divider()

    df_all = pd.DataFrame(trades)

    row1_l, row1_r = st.columns(2)

    # P&L distribution histogram
    with row1_l:
        wins_pnl   = [t["pnl"] for t in trades if t["pnl"] >  0]
        losses_pnl = [t["pnl"] for t in trades if t["pnl"] <= 0]
        fig_hist = go.Figure()
        if wins_pnl:
            fig_hist.add_trace(go.Histogram(
                x=wins_pnl, name="Wins",
                marker_color="#2ecc71", opacity=0.80, nbinsx=20,
            ))
        if losses_pnl:
            fig_hist.add_trace(go.Histogram(
                x=losses_pnl, name="Losses",
                marker_color="#e74c3c", opacity=0.80, nbinsx=20,
            ))
        fig_hist.update_layout(
            title="P&L Distribution",
            xaxis_title="₹ P&L per trade",
            yaxis_title="Trades",
            barmode="overlay",
            height=320,
            margin=dict(l=10, r=10, t=45, b=10),
        )
        st.plotly_chart(fig_hist, width="stretch")

    # Exit reason breakdown
    with row1_r:
        reason_counts = df_all["reason"].value_counts()
        _reason_colors = {
            "SL":          "#e74c3c",
            "TARGET":      "#2ecc71",
            "TRAILING":    "#9b59b6",
            "STRATEGY":    "#3498db",
            "PATTERN_TOP": "#1abc9c",
            "OPEN@END":    "#f39c12",
        }
        bar_colors = [_reason_colors.get(r, "#95a5a6") for r in reason_counts.index]
        fig_reasons = go.Figure(go.Bar(
            x=reason_counts.index,
            y=reason_counts.values,
            marker_color=bar_colors,
            text=reason_counts.values,
            textposition="outside",
        ))
        fig_reasons.update_layout(
            title="Exit Reasons",
            yaxis_title="Count",
            yaxis_range=[0, reason_counts.max() * 1.2],
            height=320,
            margin=dict(l=10, r=10, t=45, b=10),
        )
        st.plotly_chart(fig_reasons, width="stretch")

    row2_l, row2_r = st.columns(2)

    # Hold duration vs P&L scatter
    with row2_l:
        df_all["hold_h"] = (
            pd.to_datetime(df_all["exit_date"]) - pd.to_datetime(df_all["entry_date"])
        ).dt.total_seconds() / 3600
        df_all["held_candles"] = df_all["held_candles"].fillna(0).astype(int) if "held_candles" in df_all.columns else 0
        scatter_colors = ["#2ecc71" if p > 0 else "#e74c3c" for p in df_all["pnl"]]

        fig_sc = go.Figure(go.Scatter(
            x=df_all["held_candles"],
            y=df_all["pnl"],
            mode="markers",
            marker=dict(size=9, color=scatter_colors, opacity=0.8,
                        line=dict(width=0.5, color="rgba(0,0,0,0.3)")),
            text=df_all["instrument"].str.replace("NSE:", "", regex=False),
            customdata=df_all["hold_h"],
            hovertemplate="<b>%{text}</b><br>Hold: %{x} bars (%{customdata:.1f}h)<br>P&L: ₹%{y:,.0f}<extra></extra>",
        ))
        fig_sc.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1)
        fig_sc.update_layout(
            title="Hold Duration vs P&L",
            xaxis_title="Hold (candles)",
            yaxis_title="₹ P&L",
            height=320,
            margin=dict(l=10, r=10, t=45, b=10),
        )
        st.plotly_chart(fig_sc, width="stretch")

    # Win rate by instrument (horizontal bars)
    with row2_r:
        inst_stats = []
        for inst in df_all["instrument"].unique():
            sub = df_all[df_all["instrument"] == inst]
            n  = len(sub)
            win_amt = sub[sub["pnl"] > 0]["pnl"].sum()
            loss_amt = abs(sub[sub["pnl"] <= 0]["pnl"].sum())
            denom = win_amt + loss_amt
            mwwr = win_amt / denom * 100 if denom > 0 else 0.0
            inst_stats.append({
                "label":    inst.replace("NSE:", ""),
                "win_rate": mwwr,
                "trades":   n,
            })
        df_wr = pd.DataFrame(inst_stats).sort_values("win_rate", ascending=True)
        wr_colors = ["#2ecc71" if v >= 50 else "#e74c3c" for v in df_wr["win_rate"]]

        fig_wr = go.Figure(go.Bar(
            x=df_wr["win_rate"],
            y=df_wr["label"],
            orientation="h",
            marker_color=wr_colors,
            text=[f"{wr:.0f}% ({n})" for wr, n in zip(df_wr["win_rate"], df_wr["trades"])],
            textposition="outside",
        ))
        fig_wr.add_vline(x=50, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1)
        fig_wr.update_layout(
            title="Money-Weighted Win Rate by Instrument",
            xaxis_title="Wt. Win Rate %",
            xaxis_range=[0, 115],
            height=320,
            margin=dict(l=10, r=10, t=45, b=10),
        )
        st.plotly_chart(fig_wr, width="stretch")
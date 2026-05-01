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

setup(log_dir=config.log_dir, level="WARNING")  # suppress engine noise in UI
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
    st.rerun()


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
    else:
        st.success("Kite connected")
        available = config.watchlist + config.interested

    col_reconnect, _ = st.columns([1, 2])
    if col_reconnect.button("Reconnect Kite", use_container_width=True):
        _reconnect_kite()

    selected_instruments = st.multiselect(
        "Instruments",
        options=available,
        default=available,
    )

    with st.expander("Strategy params", expanded=False):
        p = config.strategy_config("lr_extrema")
        warmup      = st.number_input("warmup_bars",    value=int(p.get("warmup_bars", 200)),   step=10)
        threshold   = st.slider(      "threshold",      0.50, 0.99, float(p.get("threshold", 0.70)), 0.01)
        profit_pct  = st.number_input("profit_pct",     value=float(p.get("profit_pct", 3.0)),  step=0.5)
        stop_pct    = st.number_input("stop_pct",       value=float(p.get("stop_pct", 3.0)),    step=0.5)
        hold_bars   = st.number_input("hold_bars",      value=int(p.get("hold_bars", 150)),      step=10)
        retrain     = st.number_input("retrain_every",  value=int(p.get("retrain_every", 50)),   step=5)
        extrema_ord = st.number_input("extrema_order",  value=int(p.get("extrema_order", 5)),    step=1)
        tc1, tc2 = st.columns(2)
        trading_start = tc1.text_input("trading_start", value=p.get("trading_start", "09:15"))
        trading_end   = tc2.text_input("trading_end",   value=p.get("trading_end",   "15:30"))

    _is_running = st.session_state.get("_bt_running", False)
    run_clicked = st.button(
        "Running…" if _is_running else "Run Backtest",
        type="primary",
        use_container_width=True,
        disabled=_is_running,
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

    params = {
        "enabled": True,
        "warmup_bars":    int(warmup),
        "threshold":      float(threshold),
        "profit_pct":     float(profit_pct),
        "stop_pct":       float(stop_pct),
        "hold_bars":      int(hold_bars),
        "retrain_every":  int(retrain),
        "extrema_order":  int(extrema_ord),
        "trading_start":  trading_start,
        "trading_end":    trading_end,
    }
    from_dt = datetime.combine(from_date, datetime.min.time())
    to_dt   = datetime.combine(to_date,   datetime.max.time().replace(microsecond=0))

    if kite:
        s2t = {s: sym2tok[s] for s in selected_instruments if s in sym2tok}
    else:
        # Dummy tokens — get_candles will serve from cache if candles exist
        s2t = {s: 0 for s in selected_instruments}

    st.session_state["_bt_running"] = True
    with st.spinner("Running backtest…"):
        try:
            trades = run_backtest(kite, store, selected_instruments, s2t, params, from_dt, to_dt)
            st.session_state["trades"]      = trades
            st.session_state["from_dt"]     = from_dt
            st.session_state["to_dt"]       = to_dt
            st.session_state["instruments"] = selected_instruments
        except Exception as exc:
            st.error(f"Backtest failed: {exc}")
        finally:
            st.session_state["_bt_running"] = False
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
    cols[1].metric("Win Rate", f"{metrics['win_rate']:.1f}%")
    cols[2].metric("Net P&L",  f"₹{metrics['total_pnl']:,.0f}")
    cols[3].metric("Return",   f"{metrics['return_pct']:.2f}%")
    cols[4].metric("Max DD",   f"₹{metrics['max_drawdown']:,.0f}", delta=f"{metrics['max_drawdown_pct']:.2f}%", delta_color="inverse")
    cols[5].metric("Avg Win",  f"₹{metrics['avg_win']:,.0f}")
    cols[6].metric("Avg Loss", f"₹{metrics['avg_loss']:,.0f}")
    cols[7].metric("Sharpe*",  f"{metrics['sharpe_proxy']:.2f}")

    st.divider()

    # ── equity curve ──
    df_t = pd.DataFrame(trades).sort_values("entry_date").reset_index(drop=True)
    df_t["cum_pnl"] = df_t["pnl"].cumsum()

    # Build a continuous step so the curve shows drawdown between trades too
    xs = df_t["entry_date"].tolist()
    ys = df_t["cum_pnl"].tolist()

    point_colors = ["#2ecc71" if y >= 0 else "#e74c3c" for y in ys]

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
    fig_eq.update_layout(
        title="Equity Curve — Cumulative P&L",
        xaxis_title="Date",
        yaxis_title="₹",
        height=340,
        margin=dict(l=10, r=10, t=45, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(fig_eq, use_container_width=True)

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
        "entry", "exit", "qty", "cost", "pnl", "P&L%", "product", "reason",
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

    st.dataframe(
        df_display,
        use_container_width=True,
        height=420,
        column_config={
            "Entry ₹": st.column_config.NumberColumn(format="₹%.2f"),
            "Exit ₹":  st.column_config.NumberColumn(format="₹%.2f"),
            "Cost":    st.column_config.NumberColumn(format="₹%.2f"),
            "P&L":     st.column_config.NumberColumn(format="₹%.0f"),
            "P&L%":    st.column_config.NumberColumn(format="%.2f%%"),
        },
        hide_index=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# Tab 2 — Stock Chart
# ════════════════════════════════════════════════════════════════════════════

with tab2:
    instruments_with_trades = sorted({t["instrument"] for t in trades}) if trades else []
    chart_options = sorted(set(instruments_with_trades + bt_instruments))

    if not chart_options:
        st.info("Run a backtest first to populate the chart.")
        st.stop()

    selected_inst = st.selectbox("Instrument", chart_options, key="chart_inst")

    df_candles = store.read_candles(selected_inst, config.candle_timeframe, from_dt, to_dt)

    if df_candles.empty:
        st.warning(f"No candles cached for **{selected_inst}** in this range. "
                   "Run a backtest with Kite connected to fetch and cache candles.")
        st.stop()

    inst_trades = [t for t in trades if t["instrument"] == selected_inst]

    # Per-stock summary metrics
    if inst_trades:
        im = compute_metrics(inst_trades, config.total_capital)
        mc = st.columns(6)
        mc[0].metric("Trades",   im["total_trades"])
        mc[1].metric("Win Rate", f"{im['win_rate']:.1f}%")
        mc[2].metric("Net P&L",  f"₹{im['total_pnl']:,.0f}")
        mc[3].metric("Return",   f"{im['return_pct']:.2f}%")
        mc[4].metric("Max DD",   f"₹{im['max_drawdown']:,.0f}", delta=f"{im['max_drawdown_pct']:.2f}%", delta_color="inverse")
        mc[5].metric("Sharpe*",  f"{im['sharpe_proxy']:.2f}")
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
        x=df_candles["timestamp"],
        open=df_candles["open"],
        high=df_candles["high"],
        low=df_candles["low"],
        close=df_candles["close"],
        name="OHLC",
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
        increasing_fillcolor="#2ecc71",
        decreasing_fillcolor="#e74c3c",
    ), row=1, col=1)

    # Volume bars (colored by direction)
    vol_colors = [
        "#2ecc71" if c >= o else "#e74c3c"
        for o, c in zip(df_candles["open"], df_candles["close"])
    ]
    fig.add_trace(go.Bar(
        x=df_candles["timestamp"],
        y=df_candles["volume"],
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
        pt_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in df_it["cum_pnl"]]

        fig.add_trace(go.Scatter(
            x=df_it["entry_date"],
            y=df_it["cum_pnl"],
            mode="lines+markers",
            name="Stock P&L",
            line=dict(color="#3498db", width=2),
            marker=dict(size=7, color=pt_colors),
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>₹%{y:,.0f}<extra></extra>",
        ), row=3, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)",
                      line_width=1, row=3, col=1)

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
                        "<b>LIVE EXIT</b><br>%{x|%Y-%m-%d %H:%M}<br>"
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

    # Hide non-market hours and weekends so candles don't span 24 h
    _rangebreaks = [dict(bounds=["sat", "mon"])]
    if config.candle_timeframe != "day":
        _rangebreaks.append(dict(bounds=[15.5, 9.25], pattern="hour"))
    fig.update_xaxes(rangebreaks=_rangebreaks, rangeslider_visible=False)

    fig.update_yaxes(title_text="₹",   row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1)
    if inst_trades:
        fig.update_yaxes(title_text="P&L ₹", row=3, col=1)

    st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# Tab 3 — Trade breakdown
# ════════════════════════════════════════════════════════════════════════════

with tab3:
    if not trades:
        st.info("Run a backtest first.")
        st.stop()

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
        st.plotly_chart(fig_hist, use_container_width=True)

    # Exit reason breakdown
    with row1_r:
        reason_counts = df_all["reason"].value_counts()
        _reason_colors = {
            "SL":       "#e74c3c",
            "TARGET":   "#2ecc71",
            "STRATEGY": "#3498db",
            "OPEN@END": "#f39c12",
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
        st.plotly_chart(fig_reasons, use_container_width=True)

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
        st.plotly_chart(fig_sc, use_container_width=True)

    # Win rate by instrument (horizontal bars)
    with row2_r:
        inst_stats = []
        for inst in df_all["instrument"].unique():
            sub = df_all[df_all["instrument"] == inst]
            w  = (sub["pnl"] > 0).sum()
            n  = len(sub)
            inst_stats.append({
                "label":    inst.replace("NSE:", ""),
                "win_rate": w / n * 100,
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
            title="Win Rate by Instrument",
            xaxis_title="Win Rate %",
            xaxis_range=[0, 115],
            height=320,
            margin=dict(l=10, r=10, t=45, b=10),
        )
        st.plotly_chart(fig_wr, use_container_width=True)

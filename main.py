"""
Trader entry point.

    python main.py                   # uses config/config.yaml
    python main.py --config <path>   # uses alternate config file
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path

_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default=None)
_pre_args, _ = _pre.parse_known_args()
if _pre_args.config:
    os.environ["TRADER_CONFIG"] = _pre_args.config

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / "config" / ".env")

from trader.auth.session import create_kite
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.aggregator import CandleAggregator
from trader.data.historical import warm_up
from trader.data.live import LiveFeed
from trader.data.store import Store
from trader.features.indicators import htf_trend_regime
from trader.notifications import telegram
from trader.orders.manager import OrderManager
from trader.portfolio.tracker import PortfolioTracker
from trader.risk.manager import RiskManager
from trader.scheduler.jobs import Scheduler
from trader.strategies.base import SignalType
from trader.strategies.registry import build_strategies
from trader.ui.state import BotState

setup(log_dir=config.log_dir, level=config.log_level)
logger = get_logger(__name__)

_MARKET_OPEN = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)
_INTRADAY_TIMEFRAMES = {"5minute", "15minute", "30minute", "60minute"}


def main():
    logger.info(
        "Starting trader | env=%s | timeframe=%s | capital=%.0f",
        config.env, config.candle_timeframe, config.total_capital,
    )

    kite = create_kite()

    store = Store(config.db_path)
    risk = RiskManager()

    _kite_cash: float | None = None
    if config.env == "live":
        try:
            margins = kite.margins(segment="equity")
            _kite_cash = float(margins.get("available", {}).get("cash", 0.0))
            persisted_pnl = store.get_state("cumulative_pnl", 0.0)
            # Seed lifetime realised P&L untouched. The buying-power cap is applied
            # separately, after position reconciliation, via set_effective_capital()
            # — so a config ceiling above available cash never corrupts cumulative P&L.
            risk.seed_cumulative_pnl(persisted_pnl)
            logger.info(
                "Cumulative P&L seeded | persisted_pnl=%.2f | kite_cash=%.0f",
                persisted_pnl, _kite_cash,
            )
        except Exception as e:
            logger.warning("Failed to fetch Kite margins — cumulative P&L not seeded: %s", e)
    orders = OrderManager(
        kite=kite, store=store, mode=config.env,
        position_lookup=lambda: list(risk._open_positions.keys()),
    )
    portfolio = PortfolioTracker(kite=kite, mode=config.env)
    bot_state = BotState()
    # create_kite() just validated the token via kite.profile()
    bot_state.token_status = {"valid": True, "user_id": "",
                              "checked_at": datetime.now(), "source": "startup"}

    # Resolve instrument tokens
    instruments = kite.instruments("NSE")
    symbol_to_token = {
        f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
    }
    token_to_symbol = {v: k for k, v in symbol_to_token.items()}
    valid_watchlist = [s for s in config.watchlist if s in symbol_to_token]
    missing = set(config.watchlist) - set(valid_watchlist)
    if missing:
        logger.warning("Instruments not found on NSE: %s", missing)

    # Restore per-stock pause flags (UI-toggled, persisted in the state table) so a
    # paused stock stays paused across restarts. Pause blocks new entries only.
    for symbol in valid_watchlist:
        if store.get_state(f"{symbol}.paused", 0.0) > 0.5:
            risk.pause(symbol)

    # Build strategies
    strategies = []
    for symbol in valid_watchlist:
        strategies.extend(build_strategies(symbol, config))
    logger.info("Strategies loaded: %d", len(strategies))

    # Per-stock aggregated timeframes (4hour/day built from 15m base candles).
    # None = passthrough (strategy runs directly on base candles). The same
    # instance serves warm-up replay AND the live feed, so a mid-day restart
    # rebuilds the in-progress bar from today's stored candles automatically.
    for _w in config.timeframe_warnings():
        logger.warning("Timeframe config | %s", _w)
    aggregator_map: dict[str, CandleAggregator | None] = {}
    for symbol in valid_watchlist:
        _tf = config.strategy_timeframe(symbol)
        aggregator_map[symbol] = (
            CandleAggregator(_tf) if _tf != config.candle_timeframe else None
        )
        if aggregator_map[symbol] is not None:
            logger.info("Aggregated timeframe | %s | %s (base %s)",
                        symbol, _tf, config.candle_timeframe)

    def count_strategy_bars(symbol: str, df) -> int:
        """Number of strategy-TF bars contained in a base-candle DataFrame —
        used to restore _held_bars after restart. Passthrough: row count."""
        if aggregator_map.get(symbol) is None:
            return len(df)
        _agg = CandleAggregator(config.strategy_timeframe(symbol))  # throwaway
        return sum(
            1 for _, row in df.iterrows() if _agg.add(row.to_dict()) is not None
        )

    # Refresh candle cache before warm-up so strategies train on current data.
    # Fetch depth is per-symbol: aggregated-TF stocks need far more calendar
    # history to accumulate warmup_bars + lookback_bars at their TF.
    logger.info("Refreshing candle cache before strategy warm-up")
    for symbol in valid_watchlist:
        token = symbol_to_token[symbol]
        warm_up(kite, store, token, symbol, config.candle_timeframe,
                config.warmup_days_for(symbol))
        if config.get_strategy_params(symbol, "lr_extrema").get("ht_trend_gate_enabled"):
            warm_up(kite, store, token, symbol, "4hour", config.historical_cache_days)

    # Warm up strategies from cached historical candles so they don't need
    # 200+ live candles (33+ trading days) before emitting any signal.
    # NOTE: reconciliation must come AFTER warm-up so warm-up candles don't
    # override the reconciled position state (R3-2).
    # Only the trailing window of warm-up scores is worth persisting — the
    # dashboard conviction sparkline shows the last _CONVICTION_BACKFILL bars.
    _CONVICTION_BACKFILL = 80
    for symbol in valid_watchlist:
        warmup_from = datetime.now() - timedelta(days=config.warmup_days_for(symbol))
        df = store.read_candles(symbol, config.candle_timeframe, warmup_from, datetime.now())
        strats_for_symbol = [s for s in strategies if s.instrument == symbol]
        # Route base candles through the symbol's aggregator (passthrough when
        # None). Strategies see strategy-TF bars; today's incomplete bucket is
        # left as partial state inside the aggregator — the live feed continues
        # filling it (mid-day restart rebuild).
        _sym_agg = aggregator_map.get(symbol)
        bars: list[dict] = []
        for _, row in df.iterrows():
            candle = row.to_dict()
            candle["_symbol"] = symbol
            candle["instrument_token"] = symbol_to_token.get(symbol)
            bar = candle if _sym_agg is None else _sym_agg.add(candle)
            if bar is not None:
                bars.append(bar)
        _n = len(bars)
        _persist_from = _n - _CONVICTION_BACKFILL
        for _i, bar in enumerate(bars):
            candle = bar
            for strat in strats_for_symbol:
                strat.on_candle(candle)  # warm-up only — signals discarded
                # Backfill the conviction trajectory (trailing window only) so the
                # dashboard sparkline is populated immediately on startup instead of
                # growing in over the first ~80 live candles. The model retrains
                # progressively through warm-up, so each candle's score mirrors what
                # live would have recorded at that point — no seam with the live
                # points that follow. Cosmetic only and guarded; never blocks warm-up.
                #
                # Must use score_current() (a direct model eval), NOT the cached
                # _last_p_min: a discarded phantom warm-up entry sets _pos.entry_price
                # with no fill, after which on_candle's pending-fill guard returns
                # early every candle and freezes _last_p_min — which would write the
                # same value 80 times (flat sparkline).
                if _i >= _persist_from and hasattr(strat, "score_current"):
                    try:
                        _sc = strat.score_current()
                        if _sc is not None:
                            store.write_model_score(
                                strat.instrument, candle.get("timestamp"), _sc[0], _sc[1]
                            )
                    except Exception as e:
                        logger.debug("warm-up model_score persist skipped | %s | %s",
                                     strat.instrument, e)
    logger.info("Strategy warm-up complete")
    for strat in strategies:
        candle_count = len(getattr(strat, "_candles", []))
        trained = getattr(strat, "_trained", None)
        status = "TRAINED" if trained else ("WARMING_UP" if trained is not None else "N/A")
        logger.info(
            "Warm-up status | %s | %s | candles=%d",
            strat.instrument, status, candle_count,
        )
        bot_state.warmup_status[strat.instrument] = {"status": status, "candles": candle_count}
    bot_state.warmup_done = True

    # Clear any phantom entry state left by warm-up signal triggers that never
    # received a fill callback (position=None but _entry_price set).
    for strat in strategies:
        if getattr(strat, "_entry_price", None) is not None and strat.position is None:
            logger.info("Clearing phantom warm-up entry state | %s", strat.instrument)
            strat._entry_price = None
            if hasattr(strat, "_held_bars"):
                strat._held_bars = 0
            if hasattr(strat, "_peak_close"):
                strat._peak_close = None
            if hasattr(strat, "_trailing_active"):
                strat._trailing_active = False

    # Restore paper positions from SQLite so exits fire correctly after restart.
    if config.env == "paper":
        open_paper = store.read_open_positions()
        restored = []
        for pos in open_paper:
            instrument = pos["instrument"]
            strats_for_instrument = [s for s in strategies if s.instrument == instrument]
            if not strats_for_instrument:
                logger.warning("Paper position in DB has no matching strategy | %s — skipping", instrument)
                continue

            # Compute held_bars from candle history and sweep for missed exits.
            # held_bars is inferred by counting candles since entry_time — no
            # per-candle DB write needed. All post-entry candles are checked:
            # if an exit condition was met while the system was live it would
            # have already fired and deleted the position from DB, so any
            # position still in DB means those candles were safe.
            lr_cfg = config.get_strategy_params(instrument, "lr_extrema")
            entry_time_dt = datetime.fromisoformat(pos["entry_time"])
            post_df = store.read_candles(instrument, config.candle_timeframe, entry_time_dt, datetime.now())
            stop_price   = round(pos["entry_price"] * (1 - lr_cfg.get("stop_pct",   3.0) / 100), 2)
            target_price = round(pos["entry_price"] * (1 + lr_cfg.get("profit_pct", 3.0) / 100), 2)
            hold_bars_limit = lr_cfg.get("hold_bars", 150)
            # SL/TARGET are swept per base candle (best granularity); held bars
            # count in STRATEGY-TF bars — hold_bars for a day-TF stock means
            # trading days, not 15m candles.
            _held_agg = (
                CandleAggregator(config.strategy_timeframe(instrument))
                if aggregator_map.get(instrument) is not None else None
            )
            held = 0
            missed_exit: tuple | None = None
            for _, row in post_df.iterrows():
                if _held_agg is None:
                    held += 1
                elif _held_agg.add(row.to_dict()) is not None:
                    held += 1
                if float(row["low"]) <= stop_price:
                    missed_exit = ("SL", stop_price)
                    break
                elif float(row["high"]) >= target_price:
                    missed_exit = ("TARGET", target_price)
                    break
                elif held >= hold_bars_limit:
                    missed_exit = ("HOLD_BARS", float(row["close"]))
                    break

            if missed_exit:
                reason, exit_price = missed_exit
                logger.warning(
                    "Catch-up exit | %s | reason=%s exit_price=%.2f | missed during downtime — removing position",
                    instrument, reason, exit_price,
                )
                store.delete_open_position(instrument)
                continue

            synthetic_fill = {
                "status": "COMPLETE",
                "signal_type": SignalType.ENTRY,
                "direction": "BUY",
                "price": pos["entry_price"],
                "instrument": instrument,
                "quantity": pos["quantity"],
                "_held_bars": held,  # includes any catch-up bars counted above
            }
            _peak_close   = store.get_state(f"{instrument}.peak_close", 0.0)
            _max_gain_pct = store.get_state(f"{instrument}.max_gain_pct", 0.0)
            for strat in strats_for_instrument:
                strat.on_order_update(synthetic_fill)
                strat.seed_position_state(_peak_close, _max_gain_pct)
            # Scale-in: DB quantity is blended (parent + add-ons). Seed risk with the
            # parent lot first, then layer the add-on lots so the pool/tier state and
            # blended qty are restored exactly.
            _addon_lots = pos.get("addon_lots") or []
            _parent_qty = pos["quantity"] - sum(int(l["qty"]) for l in _addon_lots)
            if _parent_qty < 0:  # inconsistent row (legacy partial exit) — defensive
                logger.warning(
                    "addon_lots inconsistent with quantity | %s | qty=%d lots=%s — seeding blended as parent",
                    instrument, pos["quantity"], _addon_lots,
                )
                _parent_qty, _addon_lots = pos["quantity"], []
            risk.on_order_filled(instrument, pos["entry_price"], _parent_qty,
                                 fill_ts=entry_time_dt)
            if _addon_lots:
                risk.seed_scale_in(instrument, _addon_lots)
            restored.append(pos)
            logger.info(
                "Paper position restored | %s | entry=%.2f qty=%d held_bars=%d peak=%.2f max_gain=%.2f%%",
                instrument, pos["entry_price"], pos["quantity"], held, _peak_close, _max_gain_pct,
            )
        if restored:
            telegram.notify_positions_restored(restored)

    # Reconcile state from broker after warm-up — overrides any position state
    # set during warm-up with the actual broker reality.
    # R6-1: seed from bot's own DB (open_positions table) not kite.positions() which
    #        only returns today's traded positions and misses multi-day CNC holds.
    # R6-2: seed today's realised P&L from kite.positions() so daily loss limit is
    #        correctly enforced even if GTT fired while the system was down.
    if config.env == "live":
        # R6-2: seed realised P&L for today from Kite (covers GTT exits while down)
        kite_pos = kite.positions()
        today_realised = sum(
            float(p.get("realised", 0.0)) for p in kite_pos.get("net", [])
        )
        risk.seed_realised_pnl(today_realised)

        # R6-1: seed open positions from DB (bot-placed only) verified against Kite.
        # CNC positions go through 3 states on Kite:
        #   T+0 (trade day)      : appear in kite.positions()["net"] with qty > 0
        #   T+1 (next day, pre-settlement) : kite.holdings() with t1_quantity > 0, quantity = 0
        #   T+1+ (after settlement): kite.holdings() with quantity > 0
        # We must check all three sources before concluding a position was closed externally.
        db_positions = store.read_open_positions()
        kite_holdings = {h["tradingsymbol"]: h for h in kite.holdings()}
        kite_net_positions = {
            p["tradingsymbol"]: p
            for p in kite_pos.get("net", [])
            if int(p.get("quantity", 0)) > 0
        }
        open_instruments = set()

        for pos in db_positions:
            instrument = pos["instrument"]
            symbol = instrument.split(":")[-1]
            holding = kite_holdings.get(symbol)
            net_pos = kite_net_positions.get(symbol)

            held_qty = int(holding.get("quantity", 0)) if holding else 0
            t1_qty = int(holding.get("t1_quantity", 0)) if holding else 0
            pos_qty = int(net_pos.get("quantity", 0)) if net_pos else 0

            if held_qty <= 0 and t1_qty <= 0 and pos_qty <= 0:
                # Position closed externally (GTT or manual) while bot was down
                logger.warning(
                    "Position %s in DB but not in holdings or positions — closed externally, removing from DB",
                    instrument,
                )
                store.delete_open_position(instrument)
                continue

            qty = pos["quantity"]
            avg = pos["entry_price"]
            # Scale-in: DB quantity is blended — seed the parent lot, then layer
            # add-on lots (rebuilds tier count, pool usage, spacing date).
            _addon_lots = pos.get("addon_lots") or []
            _parent_qty = qty - sum(int(l["qty"]) for l in _addon_lots)
            if _parent_qty < 0:  # inconsistent row (legacy partial exit) — defensive
                logger.warning(
                    "addon_lots inconsistent with quantity | %s | qty=%d lots=%s — seeding blended as parent",
                    instrument, qty, _addon_lots,
                )
                _parent_qty, _addon_lots = qty, []
            _entry_ts = (datetime.fromisoformat(pos["entry_time"])
                         if pos.get("entry_time") else None)
            risk.seed_position(instrument, _parent_qty, avg, entry_ts=_entry_ts)
            if _addon_lots:
                risk.seed_scale_in(instrument, _addon_lots)
            open_instruments.add(instrument)

            entry_time_str = pos.get("entry_time")
            if entry_time_str:
                entry_time_dt = datetime.fromisoformat(entry_time_str)
                post_df = store.read_candles(instrument, config.candle_timeframe, entry_time_dt, datetime.now())
                held_bars = count_strategy_bars(instrument, post_df)
            else:
                held_bars = 0

            synthetic_fill = {
                "status": "COMPLETE",
                "signal_type": SignalType.ENTRY,
                "direction": "BUY",
                "price": avg,
                "instrument": instrument,
                "_held_bars": held_bars,
            }
            _peak_close   = store.get_state(f"{instrument}.peak_close", 0.0)
            _max_gain_pct = store.get_state(f"{instrument}.max_gain_pct", 0.0)
            for strat in strategies:
                if strat.instrument == instrument:
                    strat.on_order_update(synthetic_fill)
                    strat.seed_position_state(_peak_close, _max_gain_pct)
            logger.info(
                "Live position restored | %s x%d @ %.2f | held_bars=%d peak=%.2f max_gain=%.2f%%",
                instrument, qty, avg, held_bars, _peak_close, _max_gain_pct,
            )

        # Clear residual phantom state for instruments not in DB positions
        for strat in strategies:
            if strat.instrument not in open_instruments:
                strat._entry_price = None
                strat.position = None

        # Restore capital lock for BUY orders that were pending when bot restarted.
        # Without this, capital_available is overstated and a duplicate order could
        # be approved for the same instrument before the fill arrives.
        for pending in store.read_pending_live_orders():
            instrument = pending["instrument"]
            if instrument in open_instruments:
                continue  # already filled and seeded above — skip
            qty = pending["quantity"]
            price = pending["price"] or 0.0  # None for MARKET orders
            estimated_cost = qty * price
            risk.seed_pending_order(instrument, estimated_cost)
            logger.info(
                "Pending order re-locked on restart | %s | qty=%d est_cost=%.0f",
                instrument, qty, estimated_cost,
            )

        # Cap buying power at real account equity (free cash + already-deployed
        # holdings), bounded by the config ceiling. Run here — after reconciliation —
        # so capital_deployed is known and not double-counted (capital_available
        # already subtracts it). Cumulative P&L is left intact.
        if _kite_cash is not None:
            config_ceiling = config.total_capital
            account_equity = _kite_cash + risk.capital_deployed
            effective = min(config_ceiling, account_equity)
            config.set_effective_capital(effective)
            logger.info(
                "Effective capital set | config_cap=%.0f account_equity=%.0f "
                "(cash=%.0f + deployed=%.0f) effective=%.0f",
                config_ceiling, account_equity, _kite_cash,
                risk.capital_deployed, effective,
            )
            # Scale-in budget sits ON TOP of base capital — warn if the account
            # can't actually cover base + budget (add-on orders would fail at Kite).
            if config.scale_in_enabled and account_equity < effective + config.scale_in_budget:
                logger.warning(
                    "Scale-in budget not fully covered by account equity | "
                    "equity=%.0f < base=%.0f + budget=%.0f — add-ons may be rejected by broker",
                    account_equity, effective, config.scale_in_budget,
                )

    # Dashboard (read-only UI)
    if config.ui_enabled:
        from trader.ui.server import start_dashboard
        start_dashboard(bot_state, risk, store, config)
        logger.info(
            "Dashboard started | port=%d | tunnel: ssh -fN -L %d:localhost:%d trader",
            config.ui_port, config.ui_port, config.ui_port,
        )

    # Order fill callback
    def handle_order_update(update: dict):
        status = update.get("status")
        instrument = update["instrument"]
        direction = update.get("direction", "")

        if status in ("REJECTED", "CANCELLED"):
            risk.on_order_cancelled(instrument)
            telegram.notify_order_rejected(
                instrument, direction,
                update.get("status_message", status), config.env,
            )
            for strat in strategies:
                if strat.instrument == instrument:
                    strat.on_order_update(update)
            return

        if status != "COMPLETE":
            return

        fill_price = update.get("fill_price") or update.get("price") or 0.0
        quantity = update["quantity"]
        strategy = update.get("strategy", "")
        if direction == "BUY":
            if update.get("addon"):
                # Scale-in add-on lot: grow the blended position in risk + DB.
                # Parent entry_price/entry_time stay untouched (exit anchors and
                # UI sparklines remain on the original entry).
                risk.on_order_filled(instrument, fill_price, quantity,
                                     addon=True, fill_ts=datetime.now())
                if config.env in ("paper", "live"):
                    store.add_position_lot(instrument, fill_price, quantity, datetime.now())
            else:
                risk.on_order_filled(instrument, fill_price, quantity,
                                     fill_ts=datetime.now())
                if config.env in ("paper", "live"):
                    store.upsert_open_position(instrument, fill_price, quantity, 0, datetime.now())
        elif update.get("partial"):
            # Scale-out: sell part, keep the remainder open. Reduce tracked qty
            # pro-rata (capital + realised P&L) and leave entry/trailing state
            # intact so the strategy keeps managing the rest. The strategy's own
            # on_order_update sees the partial flag and does NOT reset position.
            risk.reduce_position(instrument, quantity, fill_price)
            if config.env in ("paper", "live"):
                # Consumes lots FIFO (parent first, then add-ons) so addon_lots
                # stays consistent with quantity for restart seeding.
                store.consume_position_lots(instrument, quantity)
            if config.env == "live":
                store.set_state("cumulative_pnl", risk.cumulative_pnl)
        else:
            risk.close_position(instrument, fill_price)
            if config.env in ("paper", "live"):
                store.delete_open_position(instrument)
                store.set_state(f"{instrument}.peak_close", 0.0)
                store.set_state(f"{instrument}.max_gain_pct", 0.0)
            if config.env == "live":
                store.set_state("cumulative_pnl", risk.cumulative_pnl)
        portfolio.on_order_filled(instrument, direction, quantity, fill_price)
        telegram.notify_order_filled(instrument, direction, quantity, fill_price,
                                     strategy=strategy, mode=config.env,
                                     stop_loss=update.get("trigger_price") or None,
                                     target_price=update.get("target_price") or None)
        for strat in strategies:
            if strat.instrument == instrument:
                strat.on_order_update(update)

    orders.register_update_callback(handle_order_update)

    # --- Higher-timeframe (4h) trend regime for the ht_trend entry gate ---
    _htf_regime_cache: dict[str, tuple] = {}  # symbol -> (latest_closed_4h_ts, regime_dict | None)

    def _htf_close_time(open_ts):
        # NSE 4h bars open at 09:15 (closes 13:15) and 13:15 (closes at market
        # close 15:30, not 17:15) — fixed schedule, verified empirically.
        if open_ts.time() == dtime(9, 15):
            return open_ts + timedelta(hours=4)
        return open_ts + timedelta(hours=2, minutes=15)

    def _get_htf_regime(symbol: str, candle_ts) -> dict | None:
        """Return the latest CLOSED 4h regime dict for *symbol* as of *candle_ts*
        (no-lookahead), or None if the ht_trend gate is disabled or there isn't
        enough cached 4h history yet. Cached per-symbol on the latest usable 4h
        bar so it isn't recomputed on every 5-minute candle."""
        if candle_ts is None:
            return None
        lr_cfg = config.get_strategy_params(symbol, "lr_extrema")
        if not lr_cfg.get("ht_trend_gate_enabled"):
            return None
        htf_df = store.read_candles(symbol, "4hour", candle_ts - timedelta(days=30), candle_ts)
        if htf_df.empty:
            return None
        closes = [
            float(row["close"]) for _, row in htf_df.iterrows()
            if _htf_close_time(row["timestamp"]) <= candle_ts
        ]
        if not closes:
            return None
        latest_ts = max(
            row["timestamp"] for _, row in htf_df.iterrows()
            if _htf_close_time(row["timestamp"]) <= candle_ts
        )
        cached = _htf_regime_cache.get(symbol)
        if cached and cached[0] == latest_ts:
            return cached[1]
        regime = htf_trend_regime(
            closes,
            rsi_period=lr_cfg.get("ht_trend_rsi_period", 14),
            macd_fast=lr_cfg.get("ht_trend_macd_fast", 12),
            macd_slow=lr_cfg.get("ht_trend_macd_slow", 26),
            macd_signal_period=lr_cfg.get("ht_trend_macd_signal_period", 9),
            macd_slope_ma_period=lr_cfg.get("ht_trend_macd_slope_ma_period", 3),
            rsi_downtrend_max=lr_cfg.get("ht_trend_rsi_downtrend_max", 50.0),
            rsi_oversold=lr_cfg.get("ht_trend_rsi_oversold", 30.0),
            oversold_lookback=lr_cfg.get("ht_trend_oversold_lookback", 6),
        )
        _htf_regime_cache[symbol] = (latest_ts, regime)
        return regime

    def update_position_metrics(strategy, candle: dict):
        """Per-BASE-candle position bookkeeping (UI freshness): runs every 15m
        even for aggregated-TF stocks, using the base candle's close/low."""
        if strategy.is_flat() or strategy.instrument not in risk._open_positions:
            return
        held = getattr(strategy, "_held_bars", 0)
        _entry = getattr(strategy, "_entry_price", None) or 0.0
        _close = candle["close"]
        _qty = risk._open_positions[strategy.instrument]
        # pct_change stays parent-anchored (matches the strategy's own exit gates);
        # unrealised P&L uses the blended avg cost so add-on lots are priced right.
        _pct = (_close - _entry) / _entry * 100.0 if _entry else 0.0
        _avg_cost = (risk._position_values.get(strategy.instrument, 0.0) / _qty
                     if _qty else 0.0) or _entry
        _upnl = (_close - _avg_cost) * _qty if _avg_cost else 0.0
        _peak = getattr(strategy, "_peak_close", None) or _close
        _trail = getattr(strategy, "_trailing_active", False)
        store.update_position_metrics(
            strategy.instrument, held, _close, _pct, _upnl, _peak, _trail, candle["low"],
            pattern_top_trailing=getattr(strategy, "_pattern_top_trailing", False),
        )
        # Persist peak_close and max_gain_pct so they survive daily restarts.
        store.set_state(f"{strategy.instrument}.peak_close", _peak)
        store.set_state(
            f"{strategy.instrument}.max_gain_pct",
            getattr(strategy, "_max_gain_pct", 0.0),
        )

    def run_strategy_decision(strategy, bar: dict, decision_ts):
        """Strategy decision on a strategy-TF bar (base candle when passthrough).
        decision_ts = wall-clock decision time (the triggering base candle / the
        eod flush), NOT the bar's bucket-start timestamp — signals and model
        scores are logged at the moment the decision was actually possible."""
        symbol = strategy.instrument
        _was_trailing = getattr(strategy, "_trailing_active", False)
        signal = strategy.on_candle(bar)
        if not _was_trailing and getattr(strategy, "_trailing_active", False):
            _entry = getattr(strategy, "_entry_price", 0) or 0
            _peak = getattr(strategy, "_peak_close", 0) or 0
            _gain = (_peak - _entry) / _entry * 100 if _entry else 0
            telegram.notify_trailing_activated(
                symbol, _entry, _peak, _gain,
                getattr(strategy, "_trail_pct", 1.5),
                "PATTERN_TOP" if getattr(strategy, "_pattern_top_trailing", False) else "PROFIT_PCT",
                config.env,
            )
        _drivers = (
            strategy.last_feature_drivers()
            if hasattr(strategy, "last_feature_drivers") else []
        )
        _p_min = getattr(strategy, "_last_p_min", 0.0)
        _p_max = getattr(strategy, "_last_p_max", 0.0)
        bot_state.model_scores[symbol] = {
            "p_min": _p_min,
            "p_max": _p_max,
            "drivers": _drivers,
        }
        # Persist the conviction trajectory (UI sparkline). Only once the model
        # is trained — a 0/0 pre-warmup score isn't a real reading. Cosmetic
        # only: a persistence failure must never disturb the trading path.
        _strat_model = getattr(strategy, "_model", None)
        if _strat_model is not None and getattr(_strat_model, "is_trained", False):
            try:
                store.write_model_score(symbol, decision_ts, _p_min, _p_max)
            except Exception as e:
                logger.debug("model_score persist skipped | %s | %s", symbol, e)
        filter_block = getattr(strategy, "last_filter_block", None)
        if filter_block:
            store.log_signal(
                timestamp=decision_ts or datetime.now(),
                instrument=symbol,
                strategy=strategy.name,
                direction="BUY",
                signal_type="ENTRY",
                price_hint=bar["close"],
                accepted=False,
                reject_reason=f"FILTER: {filter_block}",
            )
        if signal is None:
            logger.debug(
                "No signal | %s | held_bars=%d entry=%.2f",
                symbol,
                getattr(strategy, "_held_bars", 0),
                getattr(strategy, "_entry_price", 0) or 0,
            )
            return
        order = risk.validate(signal)
        store.log_signal(
            timestamp=decision_ts or datetime.now(),
            instrument=signal.instrument,
            strategy=signal.strategy,
            direction=signal.direction.value,
            signal_type=signal.signal_type.value,
            price_hint=signal.price_hint,
            accepted=order is not None,
            reject_reason=None if order else risk._last_reject_reason,
            exit_reason=signal.exit_reason if order is not None else None,
        )
        if order is None:
            return
        orders.place(order)

    # Candle handler
    def handle_candle(candle: dict):
        symbol = token_to_symbol.get(candle.get("instrument_token"))
        candle["_symbol"] = symbol
        _htf = _get_htf_regime(symbol, candle.get("timestamp")) if symbol else None
        candle["_htf_rsi"]        = _htf["rsi"]        if _htf else None
        candle["_htf_macd_hist"]  = _htf["macd_hist"]  if _htf else None
        candle["_htf_macd_slope"] = _htf["macd_slope"] if _htf else None
        candle["_htf_downtrend"]  = _htf["downtrend"]  if _htf else None
        candle["_htf_inversion"]  = _htf["inversion"]  if _htf else None
        orders.on_candle(candle)
        bot_state.last_candle_at = datetime.now()
        bot_state.halted = risk.is_halted()

        if config.candle_timeframe in _INTRADAY_TIMEFRAMES:
            ts = candle.get("timestamp")
            candle_time = ts.time() if ts is not None else None
            if candle_time is None or not (_MARKET_OPEN <= candle_time <= _MARKET_CLOSE):
                return

        logger.info(
            "Candle | %s | O=%.2f H=%.2f L=%.2f C=%.2f V=%d | %s",
            symbol,
            candle["open"], candle["high"], candle["low"], candle["close"],
            candle.get("volume", 0), candle.get("timestamp"),
        )
        if symbol:
            store.write_candle(symbol, config.candle_timeframe, candle)

        # Position bookkeeping runs on every base candle (UI stays fresh at 15m
        # even for aggregated-TF stocks); strategy decisions run only when the
        # symbol's strategy-TF bar completes.
        for strategy in strategies:
            if strategy.instrument != symbol:
                continue
            update_position_metrics(strategy, candle)

        _sym_agg = aggregator_map.get(symbol)
        bar = candle if _sym_agg is None else _sym_agg.add(candle)
        if bar is None:
            return
        for strategy in strategies:
            if strategy.instrument != symbol:
                continue
            run_strategy_decision(strategy, bar, decision_ts=candle.get("timestamp"))

    # Scheduler
    scheduler = Scheduler()

    def _check_token(source: str) -> bool:
        """Validate the current token with a lightweight profile() call and
        publish the result to the dashboard's token card."""
        try:
            profile = kite.profile()
            bot_state.token_status = {"valid": True, "user_id": profile.get("user_id", ""),
                                      "checked_at": datetime.now(), "source": source}
            return True
        except Exception as e:
            bot_state.token_status = {"valid": False, "user_id": "",
                                      "checked_at": datetime.now(), "source": source}
            logger.error("Kite token validation failed (%s): %s", source, e)
            return False

    def _reload_kite_token(source: str = "hot-reload"):
        """Adopt a fresh access token written to config/.env by the TOTP cron
        (08:15 IST) without a process restart — the enabler for weekly-restart
        operation. Runs while the feed is disconnected overnight, and must run
        BEFORE warm_up: the old token expired at midnight, so every REST call
        this morning needs the new one. Also invoked from the dashboard's
        "Reload token" button (POST /token/reload)."""
        old = config.kite_access_token
        new = config.reload_env()
        if not new or new == old:
            _check_token(source)  # unchanged token — still refresh the validity card
            return
        kite.set_access_token(new)
        feed.update_access_token(config.kite_api_key, new)
        if _check_token(source):
            logger.info("Kite token hot-reloaded | user=%s",
                        bot_state.token_status.get("user_id"))
        else:
            telegram.notify_error("token_hot_reload", "Kite token hot-reload failed validation")

    bot_state.reload_token = _reload_kite_token

    def pre_market():
        _reload_kite_token()
        logger.info("Pre-market: warming up candle cache")
        for symbol in valid_watchlist:
            token = symbol_to_token[symbol]
            warm_up(kite, store, token, symbol, config.candle_timeframe,
                    config.warmup_days_for(symbol))
            if config.get_strategy_params(symbol, "lr_extrema").get("ht_trend_gate_enabled"):
                warm_up(kite, store, token, symbol, "4hour", config.historical_cache_days)
        feed.reconnect()  # no-op on first startup; resumes after market-close disconnect

    def eod_flush():
        # 15:16 IST. First: deliver the already-complete 15:00–15:15 base candle
        # out of LiveFeed so each aggregator completes its FULL day/4h bar via
        # handle_candle and the order is placed now (market still open), not at
        # the 15:30 flush. This runs the normal on_candle → validate → place path
        # with the exact bar shape the backtest sees. cutoff=15:15 leaves the
        # open 15:15–15:30 partial alone, so 15-minute stocks are unaffected.
        feed.flush_closed_partials(dtime(15, 15))
        # Fallback for aggregated-TF stocks whose last-member candle never formed
        # (no ticks in 15:00–15:15): emit the in-progress bar (through 14:45) so
        # the day/4h decision still fires before close. Normal days are a no-op
        # (the bar already emitted above on its last member).
        for symbol, _agg in aggregator_map.items():
            if _agg is None:
                continue
            bar = _agg.flush()
            if bar is None:
                continue
            logger.info("EOD flush emitted partial bar | %s | %s", symbol, bar.get("timestamp"))
            for strategy in strategies:
                if strategy.instrument == symbol:
                    run_strategy_decision(strategy, bar, decision_ts=datetime.now())

    def midday_refresh():
        # A 4h bar closes at 13:15 IST — refresh the 4h cache so the ht_trend gate
        # sees today's 09:15-13:15 bar for the rest of the session. Small lookback
        # keeps this a cache-hit for everything except the just-closed bar.
        logger.info("Midday: refreshing 4h candle cache")
        for symbol in valid_watchlist:
            if not config.get_strategy_params(symbol, "lr_extrema").get("ht_trend_gate_enabled"):
                continue
            token = symbol_to_token[symbol]
            warm_up(kite, store, token, symbol, "4hour", lookback_days=5)

    def post_market():
        portfolio.refresh()  # fetch live P&L from Kite before summarising
        # Evict phantom positions from risk tracker that were closed by GTT
        # but whose order updates were never received (known edge case).
        #
        # A position is only genuinely gone if it appears in NEITHER the intraday
        # day-book (kite.positions()["net"], qty>0) NOR holdings. This is a CNC /
        # delivery system: a stock bought and carried overnight LEAVES positions()
        # and lives in kite.holdings() (t1_quantity>0 pre-settlement, quantity>0
        # after). Checking only positions() classifies every overnight holding as
        # "stale" and evicts it with a phantom exit_price=0 close — which drops the
        # risk tracker's "already in position" guard and lets the strategy re-fire
        # ENTRY the next session (duplicate buys). Mirror the startup reconcile,
        # which reads all three states (see R6-1 above).
        if config.env == "live":
            try:
                kite_pos = kite.positions()
                live_instruments = {
                    f"NSE:{p['tradingsymbol']}" for p in kite_pos.get("net", [])
                    if int(p.get("quantity", 0)) > 0
                }
                live_instruments |= {
                    f"NSE:{h['tradingsymbol']}" for h in kite.holdings()
                    if int(h.get("quantity", 0)) > 0 or int(h.get("t1_quantity", 0)) > 0
                }
                stale = set(risk._open_positions.keys()) - live_instruments
                for inst in stale:
                    logger.warning("Removing stale position from risk tracker | %s", inst)
                    risk.close_position(inst, 0.0)
            except Exception as e:
                logger.error("Failed to reconcile positions in post_market: %s", e)
        portfolio.log_summary()
        positions = list(portfolio._positions.values())
        telegram.notify_daily_pnl(
            realised=sum(p.realised_pnl for p in positions),
            unrealised=sum(p.unrealised_pnl for p in positions),
            total_trades=len(positions),
            mode=config.env,
            capital=config.total_capital,
        )
        risk.reset_day()
        orders.clear_pending()
        feed.disconnect()

    def heartbeat():
        _check_token("heartbeat")  # keep the dashboard's token card current
        open_pos = list(risk._open_positions.keys())
        logger.info(
            "Heartbeat | mode=%s | open_positions=%d %s | capital_available=%.0f",
            config.env, len(open_pos), open_pos, risk.capital_available,
        )

    scheduler.on_pre_market(pre_market)
    scheduler.on_midday(midday_refresh)
    scheduler.on_eod_flush(eod_flush)
    scheduler.on_post_market(post_market)
    scheduler.on_heartbeat(heartbeat)

    # Live feed
    tokens = [symbol_to_token[s] for s in valid_watchlist]
    feed = LiveFeed(
        api_key=config.kite_api_key,
        access_token=config.kite_access_token,
        timeframe_minutes=config.candle_minutes,
    )
    scheduler.on_market_close(feed.flush_partials)
    def handle_tick(tick: dict):
        token = tick.get("instrument_token")
        symbol = token_to_symbol.get(token)
        if symbol is None:
            return
        for strat in strategies:
            if strat.instrument != symbol:
                continue
            _was_trailing = getattr(strat, "_trailing_active", False)
            signal = strat.on_tick(tick)
            if not _was_trailing and getattr(strat, "_trailing_active", False):
                _entry = getattr(strat, "_entry_price", 0) or 0
                _peak = getattr(strat, "_peak_close", 0) or 0
                _gain = (_peak - _entry) / _entry * 100 if _entry else 0
                telegram.notify_trailing_activated(
                    symbol, _entry, _peak, _gain,
                    getattr(strat, "_trail_pct", 1.5),
                    "PATTERN_TOP" if getattr(strat, "_pattern_top_trailing", False) else "PROFIT_PCT",
                    config.env,
                )
            if signal is None:
                continue
            order = risk.validate(signal)
            store.log_signal(
                timestamp=tick.get("timestamp") or datetime.now(),
                instrument=signal.instrument,
                strategy=signal.strategy,
                direction=signal.direction.value,
                signal_type=signal.signal_type.value,
                price_hint=signal.price_hint,
                accepted=order is not None,
                reject_reason=None if order else risk._last_reject_reason,
                exit_reason=signal.exit_reason if order is not None else None,
            )
            if order is None:
                continue
            orders.place(order)

    feed.subscribe(tokens)
    feed.register_candle_handler(handle_candle)
    feed.register_tick_handler(handle_tick)
    if config.env == "live":
        feed.register_order_update_handler(orders.on_kite_order_update)

    scheduler.start()
    pre_market()
    feed.start(threaded=True)

    logger.info(
        "System ready | mode=%s | instruments=%s | strategies=%d",
        config.env, valid_watchlist, len(strategies),
    )
    telegram.notify_startup(config.env, valid_watchlist, len(strategies))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        feed.stop()
        scheduler.stop()
        logger.info("Trader stopped")


if __name__ == "__main__":
    main()

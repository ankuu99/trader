"""
Risk Manager — validates signals before order placement.

Checks:
  1. Daily loss limit — halt if breached
  2. Max open positions
  3. Already in a position for this instrument

Sizing: fixed % stop-loss, quantity = max_risk_per_trade / sl_distance
"""

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from trader.core.config import config

_IST = ZoneInfo("Asia/Kolkata")


# TODO: move _signal_time_ist to a shared trader/core/time_utils.py utility and
#       replace all other raw .time() calls on candle/tick timestamps throughout
#       the codebase (lr_extrema.py, live.py, etc.) with it for consistency.
def _signal_time_ist(ts) -> time | None:
    """Extract the time component of a timestamp, normalised to IST.

    Kite returns naive IST datetimes, but handles tz-aware datetimes safely
    by converting to IST before extracting .time(), preventing stale UTC
    comparisons if the data source ever changes.
    """
    if ts is None or not hasattr(ts, "time"):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.astimezone(_IST)
    return ts.time()
from trader.core.logger import get_logger
from trader.notifications import telegram
from trader.strategies.base import Direction, Signal, SignalType

logger = get_logger(__name__)


@dataclass
class Order:
    instrument: str
    direction: Direction
    quantity: int
    price_hint: float
    stop_loss: float
    target_price: float
    strategy: str
    mode: str
    signal_type: SignalType = SignalType.ENTRY
    partial: bool = False  # EXIT only: True = scale-out (remainder stays open)
    addon: bool = False    # ENTRY only: True = scale-in add-on lot on an open position


class RiskManager:
    def __init__(self):
        self._open_positions: dict[str, int] = {}     # instrument → filled quantity
        self._position_values: dict[str, float] = {}  # instrument → entry_price * qty
        self._capital_deployed: float = 0.0
        self._pending_orders: dict[str, float] = {}   # instrument → expected cost (pre-fill lock)
        self._realised_pnl: float = 0.0
        self._cumulative_pnl: float = 0.0  # lifetime P&L — never resets; persisted to DB in live mode
        self._halted: bool = False
        self._last_reject_reason: str | None = None   # set whenever validate() returns None
        self._paused: set[str] = set()   # instruments paused from NEW entries (exits still allowed)
        # Same-day re-entry cooldown — instruments fully closed today. Armed in
        # close_position(), cleared in reset_day(); no timestamps, so live and
        # backtest share one clock (the day boundary that already calls reset_day).
        self._reentry_blocked: set[str] = set()
        # Same-day re-entry discount gate — instrument -> [exit_proceeds, exit_qty]
        # accumulated across every exit (partial scale-outs + the final close) SINCE
        # the last entry fill, so blended = proceeds/qty is the true average price we
        # got out at. Reset on the next entry fill and at reset_day().
        # Rationale (live sweep 2026-08-26, 14 same-day exit->re-entry events): only 3
        # re-entered >=1.5% below their blended exit; ~6 round-tripped flat (pure
        # cost/basis churn) and 4 bought back HIGHER in bigger size (QUESS 06-30 +3.5%,
        # 07-31 +3.4%). A symmetric "within X%" band misses that second group, so the
        # gate is ONE-SIDED: re-entry must be at least min_discount_pct BELOW the exit.
        self._exit_today: dict[str, list[float]] = {}
        # Loss re-entry block — instrument -> sessions remaining. Armed in
        # close_position() when the full close realises a LOSS; each reset_day()
        # decrements, so `sessions: N` means the earliest re-entry is the Nth
        # session after the losing exit. Rationale (2026-08-16 recovery-profile
        # study, 2025-01→2026-08): 105 re-entries within ~3 sessions of a losing
        # exit returned net -10.2k at a 52% win rate (vs 68% baseline) while
        # walking the -20% hard-stop floor 5.3% lower per rung.
        self._loss_reentry: dict[str, int] = {}
        # Scale-in (geometric add-ons) — per-instrument lot state + a separate budget pool.
        # The pool sits ON TOP of base capital: add-on deployments never touch
        # _capital_deployed, so capital_available for base entries is unaffected.
        # inst → {addon_count, last_invest_date (date), last_lot_notional, addon_value}
        self._scale_in: dict[str, dict] = {}
        self._scale_in_deployed: float = 0.0  # add-on cost basis currently open (pool usage)
        # Instruments whose entry in _pending_orders is an ADD-ON lot. Such pendings
        # draw from the scale-in pool, so they are excluded from capital_available
        # and from the max_open_positions count (the instrument is already open).
        self._pending_addons: set[str] = set()

    # --- Per-stock pause (UI-toggled; blocks new entries, never exits) ---
    def pause(self, instrument: str) -> None:
        self._paused.add(instrument)
        logger.info("Stock paused from new entries | %s", instrument)

    def unpause(self, instrument: str) -> None:
        self._paused.discard(instrument)
        logger.info("Stock unpaused | %s", instrument)

    def is_paused(self, instrument: str) -> bool:
        return instrument in self._paused

    def paused_instruments(self) -> list[str]:
        return sorted(self._paused)

    @property
    def capital_available(self) -> float:
        # Add-on pendings draw from the scale-in pool, not base capital.
        pending = sum(v for k, v in self._pending_orders.items() if k not in self._pending_addons)
        return max(0.0, config.total_capital + self._cumulative_pnl - self._capital_deployed - pending)

    @property
    def scale_in_deployed(self) -> float:
        """Add-on cost basis currently open (scale-in pool usage, ₹)."""
        return self._scale_in_deployed

    @property
    def cumulative_pnl(self) -> float:
        return self._cumulative_pnl

    @property
    def capital_deployed(self) -> float:
        """Capital currently tied up in open positions (cost basis)."""
        return self._capital_deployed

    def seed_cumulative_pnl(self, pnl: float) -> None:
        """Restore persisted cumulative P&L on startup (live mode only)."""
        self._cumulative_pnl = pnl
        logger.info("Seeded cumulative P&L | pnl=%.2f | effective_capital=%.0f",
                    pnl, config.total_capital + pnl)

    def reset_cumulative_pnl(self, value: float = 0.0) -> None:
        """Manually override lifetime P&L (operator action from the UI).

        Sets the in-memory value; the caller persists it via store.set_state so the
        next close doesn't clobber it. Used to recover from a corrupted cumulative_pnl.
        """
        old = self._cumulative_pnl
        self._cumulative_pnl = value
        logger.warning("Cumulative P&L manually reset | %.2f -> %.2f", old, value)

    def validate(self, signal: Signal) -> Order | None:
        self._last_reject_reason = None
        if self._halted:
            if signal.signal_type == SignalType.EXIT:
                return self._validate_exit(signal)  # exits always allowed, even when halted
            logger.warning("Signal rejected — daily halt | %s", signal.instrument)
            self._last_reject_reason = "daily_halt"
            return None

        if signal.signal_type == SignalType.EXIT:
            return self._validate_exit(signal)

        # Trading window — entry signals only (safety net; strategies should pre-filter too).
        candle_time = _signal_time_ist(signal.timestamp)
        if candle_time is not None and not (config.trading_start <= candle_time <= config.trading_end):
            logger.debug(
                "Signal rejected — outside trading window | %s | %s not in [%s, %s]",
                signal.instrument, candle_time, config.trading_start, config.trading_end,
            )
            self._last_reject_reason = "outside_trading_window"
            return None

        # Same-day re-entry cooldown — this instrument was fully closed earlier in the
        # session, so block re-opening it until the day boundary. EXIT signals returned
        # at line ~141, so an open position always closes normally.
        if config.reentry_cooldown_enabled and signal.instrument in self._reentry_blocked:
            logger.info("Signal rejected — re-entry cooldown | %s", signal.instrument)
            self._last_reject_reason = "reentry_cooldown"
            return None

        # Same-day re-entry discount gate — we exited this instrument earlier in the
        # session; re-establishing the risk only pays if we get back in materially
        # cheaper than we got out. See _exit_today in __init__ for the live evidence.
        if config.reentry_discount_enabled and signal.instrument in self._exit_today:
            _proceeds, _qty = self._exit_today[signal.instrument]
            if _qty > 0:
                _blended = _proceeds / _qty
                _limit = _blended * (1 - config.reentry_discount_pct / 100.0)
                # max_premium_pct turns the one-sided rule into a band: a re-entry
                # priced well ABOVE the exit is let through again (it is a momentum
                # re-entry, not churn). None keeps the rule one-sided.
                _prem = config.reentry_premium_pct
                _ceil = None if _prem is None else _blended * (1 + _prem / 100.0)
                if signal.price_hint > _limit and (_ceil is None or signal.price_hint <= _ceil):
                    logger.info(
                        "Signal rejected — re-entry discount | %s | price=%.2f > %.2f "
                        "(exit avg %.2f - %.2f%%)",
                        signal.instrument, signal.price_hint, _limit,
                        _blended, config.reentry_discount_pct,
                    )
                    self._last_reject_reason = "reentry_discount"
                    return None

        # Loss re-entry block — the last full exit in this instrument realised a loss
        # within the last N sessions; re-entering that soon is coin-flip edge that
        # compounds the hard-stop floor lower (see _loss_reentry note in __init__).
        if config.loss_reentry_block_enabled and signal.instrument in self._loss_reentry:
            logger.info(
                "Signal rejected — loss re-entry block | %s | %d session(s) left",
                signal.instrument, self._loss_reentry[signal.instrument],
            )
            self._last_reject_reason = "loss_reentry_block"
            return None

        # Scale-in: an ENTRY signal on an instrument we already hold is an add-on
        # candidate. It does not open a NEW position, so it is routed before the
        # max_open_positions check (which would otherwise block it spuriously).
        if signal.instrument in self._open_positions:
            if config.scale_in_enabled:
                return self._validate_addon(signal)
            logger.warning("Signal rejected — already in position | %s", signal.instrument)
            self._last_reject_reason = "already_in_position"
            return None

        _pending_new = sum(1 for k in self._pending_orders if k not in self._pending_addons)
        if len(self._open_positions) + _pending_new >= config.max_open_positions:
            logger.warning("Signal rejected — max open positions | %s", signal.instrument)
            self._last_reject_reason = "max_positions"
            return None

        # Slow-TF slot cap — aggregated-TF (4hour/day) round-trips tie up capital
        # 2–3.5× longer than 15m ones (measured live 2026-08-16), so uncapped they
        # accumulate until every funded slot is a slow position and the 15m signal
        # engine starves for cash. Base-TF entries are never blocked by this.
        _slow_cap = config.max_slow_tf_positions
        if _slow_cap is not None and config.is_aggregated_tf(signal.instrument):
            _slow_held = sum(1 for k in self._open_positions if config.is_aggregated_tf(k))
            _slow_pending = sum(
                1 for k in self._pending_orders
                if k not in self._pending_addons and config.is_aggregated_tf(k)
            )
            if _slow_held + _slow_pending >= _slow_cap:
                logger.info(
                    "Signal rejected — slow-TF position cap | %s | %d held + %d pending >= %d",
                    signal.instrument, _slow_held, _slow_pending, _slow_cap,
                )
                self._last_reject_reason = "slow_tf_limit"
                return None

        if signal.instrument in self._pending_orders:
            logger.warning("Signal rejected — pending order already exists | %s", signal.instrument)
            self._last_reject_reason = "pending_order_exists"
            return None

        # Per-stock pause — block NEW entries only (EXIT signals returned earlier, line ~92,
        # so an open position still closes normally).
        if signal.instrument in self._paused:
            logger.info("Signal rejected — stock paused | %s", signal.instrument)
            self._last_reject_reason = "stock_paused"
            return None

        price = signal.price_hint

        # Use signal-supplied levels if provided (e.g. strategy-driven GTT safety nets),
        # otherwise fall back to config defaults.
        if signal.stop_loss_hint is not None:
            sl_price = round(signal.stop_loss_hint, 2)
        else:
            sl_price = round(price * (1 - config.default_sl_pct / 100), 2)

        sl_distance = price - sl_price

        if sl_distance <= 0:
            logger.error("SL distance is zero for %s", signal.instrument)
            self._last_reject_reason = "sl_distance_zero"
            return None

        quantity = int(config.max_risk_per_trade // sl_distance)

        # Confidence sizing (meta-labeling Phase 2): scale the risk-based quantity by
        # the signal's size_weight (derived from meta P(win)). None => full size.
        if signal.size_weight is not None and signal.size_weight > 0:
            quantity = int(quantity * signal.size_weight)

        # Cap quantity so total capital deployed doesn't exceed max_capital_per_stock.
        # When compounding is enabled, the cap scales with the strategy's own cumulative P&L
        # (base_capital + cumulative_pnl), keeping Kite available cash out of the calculation.
        pct = float(config._data["risk"].get("max_capital_per_stock_pct", 100.0))
        if config.compounding:
            effective_max_capital = (config.base_capital + self._cumulative_pnl) * pct / 100
        else:
            effective_max_capital = config.max_capital_per_stock
        max_qty_by_capital = int(effective_max_capital // price)
        if quantity > max_qty_by_capital:
            logger.info(
                "Quantity capped by capital limit | %s | risk-based=%d capped=%d"
                " (max_capital=%.0f compounding=%s @ %.2f)",
                signal.instrument, quantity, max_qty_by_capital,
                effective_max_capital, config.compounding, price,
            )
            quantity = max_qty_by_capital

        # Cap quantity by available portfolio capital
        max_qty_by_available = int(self.capital_available // price)
        if quantity > max_qty_by_available:
            logger.info(
                "Quantity capped by available capital | %s | before=%d after=%d"
                " (available=%.0f)",
                signal.instrument, quantity, max_qty_by_available, self.capital_available,
            )
            quantity = max_qty_by_available

        if quantity <= 0:
            logger.warning(
                "Quantity is 0 for %s — price %.2f vs available capital %.0f",
                signal.instrument, price, self.capital_available,
            )
            self._last_reject_reason = "quantity_zero"
            return None

        if signal.target_price is not None:
            target_price = round(signal.target_price, 2)
        else:
            target_price = round(price + sl_distance * config.risk_reward, 2)

        expected_cost = price * quantity
        self._pending_orders[signal.instrument] = expected_cost
        logger.info(
            "Signal approved | %s x%d @ ~%.2f SL=%.2f target=%.2f (RR=%.1f) | pending_lock=%.0f",
            signal.instrument, quantity, price, sl_price, target_price, config.risk_reward,
            expected_cost,
        )
        return Order(
            instrument=signal.instrument,
            direction=signal.direction,
            quantity=quantity,
            price_hint=price,
            stop_loss=sl_price,
            target_price=target_price,
            strategy=signal.strategy,
            mode=config.env,
            signal_type=signal.signal_type,
        )

    def _validate_exit(self, signal: Signal) -> Order | None:
        """Return a SELL order to close an open position (or a fraction of it)."""
        quantity = self._open_positions.get(signal.instrument, 0)
        if quantity <= 0:
            logger.warning("Exit signal for instrument not in positions | %s", signal.instrument)
            return None
        # Scale-out: sell only a fraction, leaving the remainder open. Never round to 0
        # (min 1 share) and never to the full position (leave >=1 so it stays open).
        frac = signal.exit_fraction
        is_partial = False
        if frac is not None and 0 < frac < 1.0 and quantity > 1:
            quantity = max(1, min(quantity - 1, int(quantity * frac)))
            is_partial = True
            logger.info("Partial exit approved | %s x%d (frac=%.2f) @ ~%.2f",
                        signal.instrument, quantity, frac, signal.price_hint)
        else:
            logger.info("Exit approved | %s x%d @ ~%.2f", signal.instrument, quantity, signal.price_hint)
        return Order(
            instrument=signal.instrument,
            direction=Direction.SELL,
            quantity=quantity,
            price_hint=signal.price_hint,
            stop_loss=0.0,
            target_price=0.0,
            strategy=signal.strategy,
            mode=config.env,
            signal_type=signal.signal_type,
            partial=is_partial,
        )

    def _validate_addon(self, signal: Signal) -> Order | None:
        """Validate a scale-in add-on ENTRY on an already-open position.

        Geometric sizing: lot notional = previous lot's notional × fraction_pct.
        The lot draws from the separate scale-in budget pool (ON TOP of base
        capital) and never counts against max_open_positions or the per-stock cap.
        Staleness/trailing anchors are untouched — the strategy ignores add-on
        fills entirely (see lr_extrema.on_order_update).
        """
        inst = signal.instrument

        if inst in self._pending_orders:
            logger.debug("Add-on rejected — pending order exists | %s", inst)
            self._last_reject_reason = "pending_order_exists"
            return None

        if inst in self._paused:
            logger.info("Add-on rejected — stock paused | %s", inst)
            self._last_reject_reason = "stock_paused"
            return None

        state = self._scale_in.get(inst)
        if state is None:
            # Position predates scale-in tracking (e.g. seeded before feature enabled
            # or restart without lot state) — no reference lot to size from.
            logger.debug("Add-on rejected — no scale-in state | %s", inst)
            self._last_reject_reason = "addon_no_state"
            return None

        if state["addon_count"] >= config.scale_in_max_addons:
            logger.debug("Add-on rejected — tier limit | %s | count=%d", inst, state["addon_count"])
            self._last_reject_reason = "addon_limit_reached"
            return None

        sig_date = getattr(signal.timestamp, "date", lambda: None)()
        last_date = state.get("last_invest_date")
        if sig_date is None or last_date is None:
            self._last_reject_reason = "addon_spacing"
            return None
        if (sig_date - last_date).days < config.scale_in_min_spacing_days:
            logger.debug(
                "Add-on rejected — spacing | %s | last=%s signal=%s", inst, last_date, sig_date,
            )
            self._last_reject_reason = "addon_spacing"
            return None

        price = signal.price_hint
        lot_notional = state["last_lot_notional"] * config.scale_in_fraction_pct / 100
        quantity = int(lot_notional // price) if price > 0 else 0
        if quantity < 1:
            logger.debug(
                "Add-on rejected — lot too small | %s | lot=%.0f price=%.2f", inst, lot_notional, price,
            )
            self._last_reject_reason = "addon_qty_zero"
            return None

        expected_cost = price * quantity
        _addon_pending = sum(
            v for k, v in self._pending_orders.items() if k in self._pending_addons
        )
        if self._scale_in_deployed + _addon_pending + expected_cost > config.scale_in_budget:
            logger.info(
                "Add-on rejected — budget exhausted | %s | deployed=%.0f + pending=%.0f + %.0f > budget=%.0f",
                inst, self._scale_in_deployed, _addon_pending, expected_cost, config.scale_in_budget,
            )
            self._last_reject_reason = "addon_budget_exhausted"
            return None

        if signal.stop_loss_hint is not None:
            sl_price = round(signal.stop_loss_hint, 2)
        else:
            sl_price = round(price * (1 - config.default_sl_pct / 100), 2)

        self._pending_orders[inst] = expected_cost
        self._pending_addons.add(inst)
        logger.info(
            "Add-on approved | %s x%d @ ~%.2f (tier %d, lot=%.0f, pool=%.0f/%.0f)",
            inst, quantity, price, state["addon_count"] + 1,
            expected_cost, self._scale_in_deployed, config.scale_in_budget,
        )
        return Order(
            instrument=inst,
            direction=signal.direction,
            quantity=quantity,
            price_hint=price,
            stop_loss=sl_price,
            target_price=0.0,
            strategy=signal.strategy,
            mode=config.env,
            signal_type=signal.signal_type,
            addon=True,
        )

    def on_order_cancelled(self, instrument: str):
        """Release capital locked for a pending order that was cancelled or rejected."""
        released = self._pending_orders.pop(instrument, None)
        self._pending_addons.discard(instrument)
        if released is not None:
            logger.info(
                "Pending capital released | %s | ₹%.0f | available=%.0f",
                instrument, released, self.capital_available,
            )

    def on_order_filled(self, instrument: str, fill_price: float, quantity: int,
                        addon: bool = False, fill_ts=None):
        self._pending_orders.pop(instrument, None)  # release pending lock, fill takes over
        self._pending_addons.discard(instrument)
        if fill_price <= 0:
            logger.error(
                "BUY fill with price=0 for %s qty=%d — skipping capital tracking",
                instrument, quantity,
            )
            return
        fill_date = getattr(fill_ts, "date", lambda: None)() or datetime.now(_IST).date()
        lot_value = fill_price * quantity
        if not addon:
            # A fresh position starts a new round trip — exits recorded for the
            # PREVIOUS one no longer describe a price we could re-enter below.
            self._exit_today.pop(instrument, None)

        if addon and instrument in self._open_positions:
            # Scale-in add-on: grow the blended position; the lot's cost basis goes
            # to the scale-in pool, NOT _capital_deployed (budget is on top of base).
            # _position_values includes it so blended avg-entry P&L on close is right.
            self._open_positions[instrument] += quantity
            self._position_values[instrument] = (
                self._position_values.get(instrument, 0.0) + lot_value
            )
            self._scale_in_deployed += lot_value
            state = self._scale_in.setdefault(
                instrument,
                {"addon_count": 0, "last_invest_date": fill_date,
                 "last_lot_notional": lot_value, "addon_value": 0.0},
            )
            state["addon_count"] += 1
            state["last_invest_date"] = fill_date
            state["last_lot_notional"] = lot_value
            state["addon_value"] += lot_value
            logger.info(
                "Add-on filled | %s x%d @ %.2f | tier=%d total_qty=%d pool=%.0f/%.0f",
                instrument, quantity, fill_price, state["addon_count"],
                self._open_positions[instrument],
                self._scale_in_deployed, config.scale_in_budget,
            )
            return

        self._open_positions[instrument] = quantity
        self._position_values[instrument] = lot_value
        self._capital_deployed += lot_value
        # Seed scale-in lot state so future add-ons can size off this parent lot.
        self._scale_in[instrument] = {
            "addon_count": 0, "last_invest_date": fill_date,
            "last_lot_notional": lot_value, "addon_value": 0.0,
        }
        logger.info(
            "Position opened | %s x%d @ %.2f | deployed=%.0f available=%.0f",
            instrument, quantity, fill_price,
            self._capital_deployed, self.capital_available,
        )

    def seed_position(self, instrument: str, qty: int, avg_price: float, entry_ts=None):
        """Seed a single position into risk state (called from startup reconciliation).
        qty/avg_price describe the PARENT lot; add-on lots are layered on afterwards
        via seed_scale_in()."""
        self._open_positions[instrument] = qty
        self._position_values[instrument] = avg_price * qty
        self._capital_deployed += avg_price * qty
        entry_date = getattr(entry_ts, "date", lambda: None)() or datetime.now(_IST).date()
        self._scale_in[instrument] = {
            "addon_count": 0, "last_invest_date": entry_date,
            "last_lot_notional": avg_price * qty, "addon_value": 0.0,
        }
        logger.info(
            "Seeded position | %s x%d @ %.2f | deployed=%.0f",
            instrument, qty, avg_price, self._capital_deployed,
        )

    def seed_scale_in(self, instrument: str, addon_lots: list[dict]):
        """Restore scale-in lot state on startup from persisted addon lots.

        addon_lots: [{"price": float, "qty": int, "date": "YYYY-MM-DD..."}] — parent
        lot excluded. Must run AFTER seed_position (which seeds the PARENT lot only).
        Layers each add-on lot onto the blended quantity / cost basis, charges the
        scale-in pool, and rebuilds addon_count / last_lot_notional / last_invest_date.
        """
        state = self._scale_in.get(instrument)
        if state is None or not addon_lots:
            return
        addon_value = 0.0
        addon_qty = 0
        for lot in addon_lots:
            lot_qty = int(lot["qty"])
            lot_value = float(lot["price"]) * lot_qty
            addon_value += lot_value
            addon_qty += lot_qty
            state["addon_count"] += 1
            state["last_lot_notional"] = lot_value
            _d = str(lot.get("date") or "")[:10]
            if _d:
                state["last_invest_date"] = datetime.fromisoformat(_d).date()
        state["addon_value"] = addon_value
        self._open_positions[instrument] = self._open_positions.get(instrument, 0) + addon_qty
        self._position_values[instrument] = self._position_values.get(instrument, 0.0) + addon_value
        self._scale_in_deployed += addon_value
        logger.info(
            "Seeded scale-in state | %s | addons=%d addon_value=%.0f pool=%.0f",
            instrument, state["addon_count"], addon_value, self._scale_in_deployed,
        )

    def seed_pending_order(self, instrument: str, estimated_cost: float):
        """Re-lock capital for a BUY order that was pending when the bot restarted."""
        self._pending_orders[instrument] = estimated_cost
        logger.info(
            "Seeded pending order | %s | estimated_cost=%.0f | available=%.0f",
            instrument, estimated_cost, self.capital_available,
        )

    def seed_realised_pnl(self, pnl: float):
        """Seed today's already-realised P&L on startup (e.g. GTT fired while system was down)."""
        if pnl == 0.0:
            return
        self._realised_pnl = pnl
        logger.info("Seeded realised P&L from broker | pnl=%.2f", pnl)
        if not self._halted and self._realised_pnl <= -config.daily_loss_limit:
            self._halted = True
            logger.warning(
                "Halt triggered from seeded P&L on startup | pnl=%.2f limit=%.2f",
                self._realised_pnl, config.daily_loss_limit,
            )
            telegram.notify_halt(self._realised_pnl, config.daily_loss_limit, config.env)

    def is_halted(self) -> bool:
        return self._halted

    def realised_pnl(self) -> float:
        return self._realised_pnl

    def _record_exit_price(self, instrument: str, exit_price: float, qty: int) -> None:
        """Accumulate exit proceeds/qty for the same-day re-entry discount gate."""
        acc = self._exit_today.setdefault(instrument, [0.0, 0.0])
        acc[0] += exit_price * qty
        acc[1] += qty

    def close_position(self, instrument: str, exit_price: float = 0.0):
        """Remove a position from tracking and accumulate realised P&L."""
        qty = self._open_positions.pop(instrument, None)
        freed = self._position_values.pop(instrument, 0.0)
        # Split the freed cost basis: add-on portion returns to the scale-in pool,
        # the remainder (parent lot) to base capital.
        _si = self._scale_in.pop(instrument, None)
        _addon_freed = min(_si["addon_value"], freed) if _si else 0.0
        self._scale_in_deployed = max(0.0, self._scale_in_deployed - _addon_freed)
        freed_base = freed - _addon_freed
        self._capital_deployed = max(0.0, self._capital_deployed - freed_base)
        if qty and freed and not exit_price:
            logger.warning(
                "close_position called with exit_price=0 for %s — P&L and halt check skipped",
                instrument,
            )
        # Arm the same-day re-entry cooldown on a genuine exit only. post_market()
        # evicts stale positions with exit_price=0 as bookkeeping (main.py); arming on
        # those would depend on eviction running before reset_day() in the same job.
        if exit_price:
            self._reentry_blocked.add(instrument)
            if qty:
                self._record_exit_price(instrument, exit_price, qty)
        if qty and exit_price and freed:
            entry_price = freed / qty
            pnl = (exit_price - entry_price) * qty
            self._realised_pnl += pnl
            self._cumulative_pnl += pnl
            # Arm the loss re-entry block on a losing full close. Keyed off the final
            # lot's realised P&L (scale-out profits already realised via
            # reduce_position don't offset it — the block targets "the exit that just
            # lost", which is what precedes the toxic rebuy).
            if config.loss_reentry_block_enabled and pnl < 0:
                self._loss_reentry[instrument] = config.loss_reentry_block_sessions
            logger.info(
                "Position closed | %s x%d | entry=%.2f exit=%.2f | trade_pnl=%.2f | daily_pnl=%.2f",
                instrument, qty, entry_price, exit_price, pnl, self._realised_pnl,
            )
            if not self._halted and self._realised_pnl <= -config.daily_loss_limit:
                self._halted = True
                logger.warning(
                    "Daily loss limit breached | daily_pnl=%.2f limit=%.2f — halting",
                    self._realised_pnl, config.daily_loss_limit,
                )
                telegram.notify_halt(self._realised_pnl, config.daily_loss_limit, config.env)

    def reduce_position(self, instrument: str, qty: int, exit_price: float = 0.0):
        """Partially close a position (scale-out): reduce tracked quantity and
        deployed capital pro-rata, accumulate realised P&L on the sold portion, and
        keep the remainder open. No-op if the instrument isn't tracked or qty would
        close it fully (callers should use close_position for that)."""
        held = self._open_positions.get(instrument, 0)
        if held <= 0 or qty <= 0:
            return
        qty = min(qty, held)
        if qty >= held:
            self.close_position(instrument, exit_price)
            return
        deployed = self._position_values.get(instrument, 0.0)
        entry_price = deployed / held if held else 0.0
        freed = entry_price * qty
        self._open_positions[instrument] = held - qty
        self._position_values[instrument] = deployed - freed
        # Pro-rata split of the freed cost basis between the scale-in pool and base
        # capital (risk accounting is avg-entry; per-lot attribution lives in the
        # backtest engine / order history).
        _si = self._scale_in.get(instrument)
        _addon_freed = 0.0
        if _si and _si["addon_value"] > 0 and deployed > 0:
            _addon_freed = min(_si["addon_value"], freed * (_si["addon_value"] / deployed))
            _si["addon_value"] -= _addon_freed
            self._scale_in_deployed = max(0.0, self._scale_in_deployed - _addon_freed)
        self._capital_deployed = max(0.0, self._capital_deployed - (freed - _addon_freed))
        if exit_price:
            self._record_exit_price(instrument, exit_price, qty)
        if exit_price and entry_price:
            pnl = (exit_price - entry_price) * qty
            self._realised_pnl += pnl
            self._cumulative_pnl += pnl
            logger.info(
                "Partial close | %s x%d of %d | entry=%.2f exit=%.2f | trade_pnl=%.2f",
                instrument, qty, held, entry_price, exit_price, pnl,
            )
            if not self._halted and self._realised_pnl <= -config.daily_loss_limit:
                self._halted = True
                telegram.notify_halt(self._realised_pnl, config.daily_loss_limit, config.env)

    def reset_day(self):
        self._realised_pnl = 0.0
        self._halted = False
        self._reentry_blocked.clear()
        self._exit_today.clear()
        # Loss re-entry block: one session elapsed — decrement, expire at zero.
        self._loss_reentry = {
            inst: left - 1 for inst, left in self._loss_reentry.items() if left > 1
        }
        logger.info("Risk manager daily reset")

    @property
    def loss_reentry_state(self) -> dict[str, int]:
        """Instrument -> sessions remaining on the loss re-entry block (read-only copy)."""
        return dict(self._loss_reentry)

    def seed_loss_reentry(self, state: dict[str, int]):
        """Restore loss re-entry block state on startup (live-mode restart seeding)."""
        self._loss_reentry = {k: int(v) for k, v in (state or {}).items() if int(v) > 0}
